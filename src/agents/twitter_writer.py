from typing import Dict
from src.integrations.gemini_client import generate_ai_text
from src.core.config import Config


TWITTER_PROMPT = """
Ты автор вирусного Twitter/X аккаунта про нейросети и AI.
Напиши один цепляющий твит (НЕ тред) на русском языке.

Тема поста: {topic}
Ссылка для перехода: {cta_link}

СТРОГАЯ СТРУКТУРА ТВИТА:
1. Строка 1: 🔥 Интригующий или провокационный Hook (останавливает скролл).
2. Строка 2-3: 1-2 предложения с конкретной пользой/инсайдом (без воды).
3. Финальная строка: Призыв перейти в Telegram + ссылка:
   Разбор и секреты в TG 👉 {cta_link}

ПРАВИЛА:
- Язык: русский.
- ОБЩАЯ длина твита со ссылкой: от 180 до 260 символов (НЕ БОЛЕЕ 270 СИМВОЛОВ!).
- Ссылка {cta_link} ОБЯЗАТЕЛЬНО должна быть в конце твита!
- 2-3 тематических эмодзи.
- Выведи ТОЛЬКО готовый текст твита, без кавычек и комментариев.
"""


def _get_cta_link(content_plan: Dict) -> str:
    """Возвращает ссылку на Telegram-канал для Twitter."""
    return Config.get_channel_link()


def _clean_tweet(text: str, cta_link: str) -> str:
    """
    Очищает твит и гарантирует наличие ссылки на Telegram в конце.
    """
    text = text.strip()

    # Убираем кавычки
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()

    # Убираем системные префиксы
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines and lines[0].lower().startswith(("твит:", "вот твит:", "tweet:")):
        lines = lines[1:]

    cleaned = "\n".join(lines).strip()

    # Проверяем наличие ссылки в тексте
    if cta_link not in cleaned:
        # Проверяем поместится ли ссылка в лимит 280
        max_text_len = 275 - len(cta_link) - 25
        if len(cleaned) > max_text_len:
            cleaned = cleaned[:max_text_len] + "..."
        cleaned += f"\n\nВсе фишки в TG 👉 {cta_link}"
    elif len(cleaned) > 280:
        # Если ссылка есть, но твит длиннее 280 — урезаем текст перед ссылкой
        parts = cleaned.rsplit(cta_link, 1)
        body = parts[0][:270 - len(cta_link)].strip()
        cleaned = f"{body}\n👉 {cta_link}"

    return cleaned


def write_twitter_post(
    content_plan: Dict,
    telegram_text: str = "",
) -> Dict:
    """
    Генерирует вирусный твит со ссылкой на Telegram-канал.
    """
    cta_link = _get_cta_link(content_plan)
    topic = content_plan.get("topic", "Секреты нейросетей")

    prompt = TWITTER_PROMPT.format(
        topic=topic,
        cta_link=cta_link,
    )

    ai_result = generate_ai_text(prompt)
    raw_tweet = ai_result.get("text", "").strip()

    tweet_text = _clean_tweet(raw_tweet, cta_link)

    return {
        "success": True,
        "tweet_text": tweet_text,
        "tweet_length": len(tweet_text),
        "twitter_format": "Viral Hook + CTA",
        "cta_link": cta_link,
        "using_affiliate_link": False,
        "ai_source": ai_result.get("source", "gemini"),
        "product_name": content_plan.get("product", {}).get("name", "AI Channel"),
    }