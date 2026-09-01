import os
import json
import requests
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()

# Полный список моделей Gemini в порядке приоритета
GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-2.5-flash",
]

# Список моделей Groq
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]


def _generate_with_gemini_sdk(prompt: str, api_key: str) -> Optional[str]:
    """Генерация через официальный google-genai SDK."""
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        print(f"[Gemini SDK] Ошибка инициализации клиента: {exc}")
        return None

    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            text = response.text
            if text and text.strip():
                print(f"[Gemini SDK] ✅ Успешно: {model_name}")
                return text.strip()
        except Exception as exc:
            err = str(exc)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                print(f"[Gemini SDK] {model_name} — лимит (429), пробую следующую...")
            elif "503" in err or "UNAVAILABLE" in err:
                print(f"[Gemini SDK] {model_name} — перегружен (503), пробую следующую...")
            elif "404" in err or "NOT_FOUND" in err:
                print(f"[Gemini SDK] {model_name} — 404, пробую следующую...")
            else:
                print(f"[Gemini SDK] {model_name} — ошибка: {exc}")
            continue

    return None


def _generate_with_gemini_rest(prompt: str, api_key: str) -> Optional[str]:
    """Прямой REST API запрос к Gemini (сверхнадежный fallback без конфликта библиотек)."""
    for model_name in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1200},
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and parts[0].get("text"):
                        print(f"[Gemini REST] ✅ Успешно: {model_name}")
                        return parts[0]["text"].strip()
            else:
                print(f"[Gemini REST] {model_name} HTTP {resp.status_code}")
        except Exception as e:
            print(f"[Gemini REST] {model_name} ошибка сети: {e}")
            continue

    return None


def _generate_with_groq_rest(prompt: str, api_key: str) -> Optional[str]:
    """
    Прямой REST API запрос к Groq (OpenAI-compatible).
    Избегает конфликтов версий httpx / groq SDK ('proxies' error).
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for model_name in GROQ_MODELS:
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты полезный русскоязычный автор контента про нейросети и AI.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 1200,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    text = choices[0].get("message", {}).get("content", "")
                    if text and text.strip():
                        print(f"[Groq REST] ✅ Успешно: {model_name}")
                        return text.strip()
            else:
                print(f"[Groq REST] {model_name} HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"[Groq REST] {model_name} ошибка сети: {e}")
            continue

    return None


def generate_ai_text(prompt: str) -> Dict[str, str]:
    """
    Основной: Gemini (SDK -> REST)
    Резервный: Groq (REST LLaMA 3.3 70B / 3.1 8B)
    """
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()

    # 1. Пробуем Gemini через SDK
    if gemini_key:
        text = _generate_with_gemini_sdk(prompt, gemini_key)
        if text:
            return {"source": "gemini-sdk", "text": text}

        # 2. Пробуем Gemini через прямой REST
        text = _generate_with_gemini_rest(prompt, gemini_key)
        if text:
            return {"source": "gemini-rest", "text": text}

    # 3. Резервный провайдер — Groq через REST
    if groq_key:
        print("[AI] Переключаюсь на Groq REST...")
        text = _generate_with_groq_rest(prompt, groq_key)
        if text:
            return {"source": "groq", "text": text}

    print("[AI] ❌ Все AI провайдеры вернули ошибку")
    return {
        "source": "fallback",
        "text": "Не удалось сгенерировать текст. Проверь API ключи.",
    }


if __name__ == "__main__":
    test_prompt = "Напиши короткий цепляющий факт о нейросетях на русском языке (2-3 предложения)."
    result = generate_ai_text(test_prompt)

    print("\n=== AI TEST RESULT ===")
    print("Source:", result["source"])
    print("Text:")
    print(result["text"])