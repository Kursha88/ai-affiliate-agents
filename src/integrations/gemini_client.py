import os
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
]


def _generate_with_gemini(prompt: str) -> Optional[str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("[Gemini] GEMINI_API_KEY не найден")
        return None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        print(f"[Gemini] Ошибка инициализации клиента: {exc}")
        return None

    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            text = response.text
            if text and text.strip():
                print(f"[Gemini] Использую модель: {model_name}")
                return text.strip()
            else:
                print(f"[Gemini] {model_name} — пустой ответ")

        except Exception as exc:
            err = str(exc)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                print(f"[Gemini] {model_name} — лимит исчерпан, пробую следующую...")
                continue
            elif "404" in err or "NOT_FOUND" in err:
                print(f"[Gemini] {model_name} — модель не найдена, пробую следующую...")
                continue
            else:
                print(f"[Gemini] {model_name} — ошибка: {exc}")
                continue

    print("[Gemini] Все модели недоступны")
    return None


def _generate_with_groq(prompt: str) -> Optional[str]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        print("[Groq] GROQ_API_KEY не найден")
        return None

    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "Ты полезный русскоязычный ассистент для Telegram-канала про AI-инструменты.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )

        text = completion.choices[0].message.content
        if text and text.strip():
            return text.strip()

        print("[Groq] Пустой ответ от модели")
        return None

    except Exception as exc:
        print(f"[Groq] Ошибка: {exc}")
        return None


def generate_ai_text(prompt: str) -> Dict[str, str]:
    """
    Основной: Gemini (пробует 3 модели по очереди)
    Резервный: Groq llama-3.3-70b
    """
    # Сначала пробуем Gemini
    text = _generate_with_gemini(prompt)
    if text:
        return {"source": "gemini", "text": text}

    # Резервный — Groq
    print("[AI] Gemini недоступен, переключаюсь на Groq...")
    text = _generate_with_groq(prompt)
    if text:
        return {"source": "groq", "text": text}

    return {
        "source": "fallback",
        "text": "Не удалось сгенерировать текст. Проверь API ключи.",
    }


if __name__ == "__main__":
    test_prompt = "Сгенерируй короткий дружелюбный пост для Telegram (3-5 предложений) о том, как AI экономит время."
    result = generate_ai_text(test_prompt)

    print("\n=== AI TEST RESULT ===")
    print("Source:", result["source"])
    print("Text:")
    print(result["text"])