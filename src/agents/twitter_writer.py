from typing import Dict
from src.integrations.gemini_client import generate_ai_text


# ─── Форматы твитов ───────────────────────────────────────────────────────────

TWITTER_PROMPTS = {
    "Hook": """
Ты вирусный копирайтер для Twitter/X, специализируешься на AI-инструментах.

Напиши один твит (НЕ тред) для Twitter/X.

Продукт: {product_name}
Описание: {product_description}
Тема: {topic}
CTA ссылка: {cta_link}

Структура твита:
1. Строка 1 — цепляющий hook или смелое утверждение (заставляет остановить скролл)
2. Строка 2 — curiosity gap (намекни на что-то неожиданное, не раскрывай всё)
3. Строка 3 — одна конкретная польза или результат
4. Строка 4 — CTA + ссылка

Правила:
- Пиши ТОЛЬКО на русском языке
- Максимум 260 символов ВКЛЮЧАЯ ссылку
- Никаких хэштегов
- Максимум 2-3 эмодзи
- Никаких клише: революционный, невероятный, топовый
- Hook должен создавать FOMO или любопытство
- Тон: умный друг делится секретом, не реклама
- Выведи ТОЛЬКО текст твита, ничего лишнего
""",

    "Problem": """
Ты вирусный копирайтер для Twitter/X, специализируешься на AI-инструментах.

Напиши один твит (НЕ тред) для Twitter/X.

Продукт: {product_name}
Описание: {product_description}
Тема: {topic}
CTA ссылка: {cta_link}

Структура твита:
1. Строка 1 — узнаваемая проблема (то с чем все сталкиваются)
2. Строка 2 — усиление проблемы (почему это реально раздражает)
3. Строка 3 — решение через {product_name}
4. Строка 4 — CTA + ссылка

Правила:
- Пиши ТОЛЬКО на русском языке
- Максимум 260 символов ВКЛЮЧАЯ ссылку
- Никаких хэштегов
- Максимум 2-3 эмодзи
- Проблема должна быть реальной и личной
- Тон: с пониманием, прямо
- Выведи ТОЛЬКО текст твита, ничего лишнего
""",

    "Stat": """
Ты вирусный копирайтер для Twitter/X, специализируешься на AI-инструментах.

Напиши один твит (НЕ тред) для Twitter/X.

Продукт: {product_name}
Описание: {product_description}
Тема: {topic}
CTA ссылка: {cta_link}

Структура твита:
1. Строка 1 — удивительный факт или цифра (реальная или реалистичная, про AI/продуктивность)
2. Строка 2 — почему это важно для читателя
3. Строка 3 — как {product_name} помогает с этим
4. Строка 4 — CTA + ссылка

Правила:
- Пиши ТОЛЬКО на русском языке
- Максимум 260 символов ВКЛЮЧАЯ ссылку
- Никаких хэштегов
- Максимум 2 эмодзи
- Факт должен быть правдоподобным и удивительным
- Тон: информативно, но ёмко
- Выведи ТОЛЬКО текст твита, ничего лишнего
""",

    "Curiosity": """
Ты вирусный копирайтер для Twitter/X, специализируешься на AI-инструментах.

Напиши один твит (НЕ тред) для Twitter/X.

Продукт: {product_name}
Описание: {product_description}
Тема: {topic}
CTA ссылка: {cta_link}

Структура твита:
1. Строка 1 — открытый вопрос или незаконченное утверждение (читатель ДОЛЖЕН кликнуть)
2. Строка 2 — дразни ответом не раскрывая его
3. Строка 3 — что получит читатель если перейдёт
4. Строка 4 — CTA + ссылка

Правила:
- Пиши ТОЛЬКО на русском языке
- Максимум 260 символов ВКЛЮЧАЯ ссылку
- Никаких хэштегов
- Максимум 2-3 эмодзи
- Должно создавать настоящее любопытство, не кликбейт
- Тон: интригующий, умный
- Выведи ТОЛЬКО текст твита, ничего лишнего
""",

    "Social Proof": """
Ты вирусный копирайтер для Twitter/X, специализируешься на AI-инструментах.

Напиши один твит (НЕ тред) для Twitter/X.

Продукт: {product_name}
Описание: {product_description}
Тема: {topic}
CTA ссылка: {cta_link}

Структура твита:
1. Строка 1 — "X людей используют [продукт] чтобы..." или утверждение с результатом
2. Строка 2 — конкретный кейс или результат (не абстрактный)
3. Строка 3 — почему ты тоже должен попробовать
4. Строка 4 — CTA + ссылка

Правила:
- Пиши ТОЛЬКО на русском языке
- Максимум 260 символов ВКЛЮЧАЯ ссылку
- Никаких хэштегов
- Максимум 2 эмодзи
- Социальное доказательство должно звучать аутентично
- Тон: уверенный, прямой
- Выведи ТОЛЬКО текст твита, ничего лишнего
""",
}

DEFAULT_TWITTER_PROMPT = """
Ты вирусный копирайтер для Twitter/X, специализируешься на AI-инструментах.

Напиши один цепляющий твит для Twitter/X.

Продукт: {product_name}
Описание: {product_description}
Тема: {topic}
CTA ссылка: {cta_link}

Правила:
- Пиши ТОЛЬКО на русском языке
- Максимум 260 символов ВКЛЮЧАЯ ссылку
- Никаких хэштегов
- Максимум 2-3 эмодзи
- Hook в первой строке
- CTA + ссылка в последней строке
- Выведи ТОЛЬКО текст твита, ничего лишнего
"""

# Форматы которые циклически чередуются
TWITTER_FORMAT_ROTATION = [
    "Hook",
    "Problem",
    "Curiosity",
    "Stat",
    "Social Proof",
]


def _get_cta_link(content_plan: Dict) -> str:
    """
    Определяет CTA ссылку:
    - Если есть affiliate link → используем его
    - Если нет → используем Telegram канал
    """
    affiliate_link = content_plan.get("product", {}).get("affiliate_link", "")

    placeholder_keywords = [
        "your_link",
        "affiliate_link",
        "example.com",
        "placeholder",
        "",
    ]

    is_real_link = affiliate_link and not any(
        kw in affiliate_link.lower() for kw in placeholder_keywords
    )

    if is_real_link:
        return affiliate_link

    # Fallback → Telegram канал
    return "https://t.me/nejroavtomatizacia"


def _select_twitter_format(content_plan: Dict) -> str:
    """
    Выбирает формат твита на основе формата Telegram-поста.
    """
    telegram_format = content_plan.get("format", "")

    mapping = {
        "Обзор инструмента": "Hook",
        "Топ-5 инструментов": "Social Proof",
        "Пошаговая инструкция": "Problem",
        "Сравнение сервисов": "Curiosity",
        "Проблема и решение": "Problem",
        "Лайфхак дня": "Hook",
        "Новость AI": "Stat",
        "Личная рекомендация": "Social Proof",
        "Кейс использования": "Stat",
        "Вопрос и ответ": "Curiosity",
    }

    return mapping.get(telegram_format, "Hook")


def _clean_tweet(text: str) -> str:
    """
    Очищает твит от лишнего что может добавить AI.
    """
    text = text.strip()

    # Убираем кавычки
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()

    # Убираем markdown заголовки
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.lstrip("#").strip()
        if line:
            cleaned.append(line)

    # Убираем двойные пустые строки
    result = []
    prev_empty = False
    for line in cleaned:
        if line == "":
            if not prev_empty:
                result.append(line)
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False

    return "\n".join(result).strip()


def _validate_tweet(text: str) -> Dict:
    """
    Проверяет твит на соответствие требованиям X.
    """
    MAX_LENGTH = 280
    issues = []
    length = len(text)

    if length > MAX_LENGTH:
        issues.append(f"Слишком длинный: {length} символов (макс {MAX_LENGTH})")

    if length < 50:
        issues.append(f"Слишком короткий: {length} символов")

    if text.count("#") > 2:
        issues.append("Слишком много хэштегов")

    return {
        "valid": len(issues) == 0,
        "length": length,
        "issues": issues,
    }


def write_twitter_post(
    content_plan: Dict,
    telegram_text: str = "",
) -> Dict:
    """
    Создаёт вирусный твит специально для Twitter/X.

    НЕ сокращает Telegram-текст.
    Пишет с нуля с фокусом на Hook, интригу и CTA.

    Args:
        content_plan: план от Strategist
        telegram_text: текст Telegram-поста (для контекста, не копирования)

    Returns:
        Dict с твитом и метаданными
    """
    twitter_format = _select_twitter_format(content_plan)
    cta_link = _get_cta_link(content_plan)
    prompt_template = TWITTER_PROMPTS.get(twitter_format, DEFAULT_TWITTER_PROMPT)

    prompt = prompt_template.format(
        product_name=content_plan["product"]["name"],
        product_description=content_plan["product"]["description"],
        topic=content_plan["topic"],
        cta_link=cta_link,
    )

    # Telegram текст добавляем только как контекст — не для копирования
    if telegram_text:
        prompt += f"""

Только для контекста (НЕ копируй, напиши совершенно другое):
---
{telegram_text[:300]}
---
"""

    ai_result = generate_ai_text(prompt)
    raw_tweet = ai_result["text"]
    tweet_text = _clean_tweet(raw_tweet)
    validation = _validate_tweet(tweet_text)

    # Если твит слишком длинный — просим AI сократить
    if not validation["valid"] and validation["length"] > 280:
        retry_prompt = f"""
Этот твит слишком длинный ({validation['length']} символов).
Перепиши его чтобы уложиться в 260 символов. Сохрани hook и CTA ссылку.
Пиши ТОЛЬКО на русском языке.

Оригинальный твит:
{tweet_text}

Выведи ТОЛЬКО сокращённый твит, ничего лишнего.
"""
        retry_result = generate_ai_text(retry_prompt)
        tweet_text = _clean_tweet(retry_result["text"])
        validation = _validate_tweet(tweet_text)

    # Определяем используется ли affiliate link или fallback
    affiliate_link = content_plan.get("product", {}).get("affiliate_link", "")
    using_affiliate = bool(affiliate_link and cta_link == affiliate_link)

    return {
        "success": True,
        "tweet_text": tweet_text,
        "tweet_length": validation["length"],
        "twitter_format": twitter_format,
        "cta_link": cta_link,
        "using_affiliate_link": using_affiliate,
        "ai_source": ai_result["source"],
        "valid": validation["valid"],
        "issues": validation["issues"],
        "product_name": content_plan["product"]["name"],
    }


if __name__ == "__main__":
    from src.agents.strategist import create_content_plan

    print("=== TWITTER WRITER TEST ===\n")

    formats_to_test = [
        "Обзор инструмента",
        "Проблема и решение",
        "Лайфхак дня",
        "Новость AI",
        "Кейс использования",
    ]

    for telegram_format in formats_to_test:
        plan = create_content_plan()
        plan["format"] = telegram_format

        print(f"📝 Telegram формат: {telegram_format}")
        print(f"🛍️  Продукт: {plan['product']['name']}")

        result = write_twitter_post(plan)

        print(f"🐦 Twitter формат: {result['twitter_format']}")
        print(f"🔗 CTA: {'Affiliate ✅' if result['using_affiliate_link'] else 'Telegram 📢'}")
        print(f"✅ AI: {result['ai_source']}")
        print(f"📏 Длина: {result['tweet_length']} символов")
        if result["issues"]:
            print(f"⚠️  Проблемы: {result['issues']}")
        print("-" * 50)
        print(result["tweet_text"])
        print("-" * 50 + "\n")