from typing import Dict
from src.integrations.gemini_client import generate_ai_text


SYSTEM_PROMPT_TEMPLATE = """
Ты копирайтер для русскоязычного Telegram-канала про AI-инструменты.
Пиши простым живым языком, без зауми и кликбейта.

Напиши пост в Telegram по следующему плану:

- Тема поста: {topic}
- Формат поста: {format}
- Рекомендуемый сервис: {product_name}
- Описание сервиса: {product_description}
- Ссылка на сервис: {affiliate_link}
- Призыв к действию: {cta}

Структура поста:
1. Начало с эмодзи и хука — какая проблема решает инструмент.
2. 2-3 предложения по теме, полезно, без воды.
3. 3-4 буллита с функциями/преимуществами сервиса.
4. Кому этот инструмент будет полезен.
5. Призыв к действию с ссылкой.

Важные правила:
- Только русский язык, не вставляй английские слова где можно заменить на русские.
- Пост должен быть длинной 200-400 символов.
- Не используй слово "лучший", "топ-1", "гарантированно".
- Не делай ложных обещаний заработка.
- Тон дружелюбный, как будто делишься полезной находкой с другом.
- В конце поста ставь прямую ссылку: {affiliate_link}
- Не добавляй пометку про партнёрские ссылки — это добавит редактор.
- Не добавляй картинки/хэштеги в текст.
"""


def write_post(content_plan: Dict) -> Dict:
    """
    Пишет черновик поста по плану от Strategist.
    """
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        topic=content_plan["topic"],
        format=content_plan["format"],
        product_name=content_plan["product"]["name"],
        product_description=content_plan["product"]["description"],
        affiliate_link=content_plan["product"]["affiliate_link"],
        cta=content_plan["cta"],
    )

    ai_result = generate_ai_text(prompt)

    draft_text = ai_result["text"].strip()

    # Удаляем кавычки которые иногда добавляет AI
    if draft_text.startswith('"') and draft_text.endswith('"'):
        draft_text = draft_text[1:-1].strip()

    return {
        "plan": content_plan,
        "draft_text": draft_text,
        "ai_source": ai_result["source"],
    }


if __name__ == "__main__":
    # Для теста сначала создаём план через Strategist
    from src.agents.strategist import create_content_plan

    print("=== COPYWRITER TEST ===\n")

    plan = create_content_plan()
    print(f"План: {plan['topic']} / {plan['product']['name']}")
    print(f"AI провайдер: ждём ответ...\n")

    result = write_post(plan)

    print(f"✅ Пост сгенерирован! (AI: {result['ai_source']})")
    print("-" * 50)
    print(result["draft_text"])
    print("-" * 50)
    print(f"Длина текста: {len(result['draft_text'])} символов")