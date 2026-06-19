import os
from typing import Optional, Dict

from dotenv import load_dotenv

load_dotenv()


def _generate_with_gemini(prompt: str) -> Optional[str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("[Gemini] GEMINI_API_KEY не найден")
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)

        text = getattr(response, "text", None)
        if text and text.strip():
            return text.strip()

        print("[Gemini] Пустой ответ от модели")
        return None

    except Exception as exc:
        print(f"[Gemini] Ошибка: {exc}")
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
            model="llama-3.1-8b-instant",
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
    Основной: Groq (быстрый, бесплатный, работает с Python 3.14)
    Резервный: Gemini (когда починят совместимость с Python 3.14)
    """
    # Сначала пробуем Groq
    text = _generate_with_groq(prompt)
    if text:
        return {"source": "groq", "text": text}

    # Резервный — Gemini
    text = _generate_with_gemini(prompt)
    if text:
        return {"source": "gemini", "text": text}

    return {
        "source": "fallback",
        "text": "Не удалось сгенерировать текст. Проверь API ключи.",
    }


if __name__ == "__main__":
    test_prompt = "Сгенерируй короткий дружелюбный пост в Telegram (3-5 предложений) о том, как AI экономит время."
    result = generate_ai_text(test_prompt)

    print("\n=== AI TEST RESULT ===")
    print("Source:", result["source"])
    print("Text:")
    print(result["text"])