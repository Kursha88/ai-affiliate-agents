import os
import json
import random
import yaml
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_json(path: str, data: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_active_partners(partners_config: dict) -> list:
    """Возвращает только активные партнёрки со статусом active."""
    return [
        p for p in partners_config.get("partners", [])
        if p.get("active") is True and p.get("status") == "active"
    ]


def _get_unused_topic(topics: list, history: list) -> str:
    """
    Выбирает тему которая не использовалась недавно.
    Если все темы использованы — сбрасывает историю.
    """
    used_topics = [h.get("topic") for h in history[-len(topics):]]
    unused = [t for t in topics if t not in used_topics]

    if not unused:
        unused = topics

    return random.choice(unused)


def _get_unused_format(formats: list, history: list) -> str:
    """
    Выбирает формат который не использовался недавно.
    """
    used_formats = [h.get("format") for h in history[-5:]]
    unused = [f for f in formats if f not in used_formats]

    if not unused:
        unused = formats

    return random.choice(unused)


def _stem(word: str) -> str:
    """
    Простая псевдо-стемминг функция для русского языка.
    Берёт корневую часть слова по длине чтобы обойти падежи.

    Примеры:
        текстов → текст
        тексты  → текст
        дизайна → дизай
        видео   → видео
    """
    if len(word) >= 6:
        return word[:5]
    elif len(word) >= 4:
        return word[:4]
    return word


def _get_partner_for_topic(topic: str, partners: list) -> dict:
    """
    Подбирает партнёра под тему используя систему скоринга.

    Скоринг:
    - Точное вхождение тега в тему              → +3 очка
    - Корень тега совпадает с корнем темы       → +3 очка
    - Частичное вхождение корней                → +1 очко
    - Корень категории совпадает с темой        → +2 очка
    - Частичное совпадение категории            → +1 очко
    - Нет совпадений                            → случайный партнёр
    """
    topic_lower = topic.lower()
    topic_words = [w for w in topic_lower.split() if len(w) >= 4]
    topic_stems = [_stem(w) for w in topic_words]

    scored = []

    for partner in partners:
        score = 0

        tags = partner.get("tags", [])
        category = partner.get("category", "").lower()
        category_words = [w for w in category.split() if len(w) >= 4]
        category_stems = [_stem(w) for w in category_words]

        # Скоринг по тегам
        for tag in tags:
            tag_lower = tag.lower()
            tag_stem = _stem(tag_lower)

            # Точное вхождение тега в тему
            if tag_lower in topic_lower:
                score += 3
                continue

            # Совпадение по псевдо-корню
            for topic_stem in topic_stems:
                if topic_stem == tag_stem:
                    score += 3
                    break
                # Один содержит другой как подстроку
                elif topic_stem in tag_stem or tag_stem in topic_stem:
                    score += 1
                    break

        # Скоринг по категории
        for cat_stem in category_stems:
            for topic_stem in topic_stems:
                if topic_stem == cat_stem:
                    score += 2
                    break
                elif topic_stem in cat_stem or cat_stem in topic_stem:
                    score += 1
                    break

        scored.append((score, partner))

    # Сортируем по убыванию
    scored.sort(key=lambda x: x[0], reverse=True)

    # Показываем все результаты для отладки
    print(f"\n🔍 Скоринг партнёров для темы: '{topic}'")
    print(f"   Слова темы: {topic_words}")
    print(f"   Корни темы: {topic_stems}")
    for score, p in scored:
        print(f"   {score:.0f} pts → {p['name']} ({p['category']})")

    # Берём топ-3 с ненулевым score
    top_candidates = [p for score, p in scored[:3] if score > 0]

    if top_candidates:
        chosen = random.choice(top_candidates)
        print(f"   ✅ Выбран: {chosen['name']} (из топ-{len(top_candidates)} кандидатов)")
        return chosen

    # Fallback — случайный партнёр
    chosen = random.choice(partners)
    print(f"   ⚠️  Нет совпадений → случайный: {chosen['name']}")
    return chosen


def create_content_plan() -> dict:
    """
    Основная функция агента Strategist.
    Создаёт план для одного поста.
    """
    # Загружаем конфиги
    settings = _load_yaml("config/settings.yaml")
    partners_config = _load_yaml("config/partners.yaml")
    history = _load_json("data/topic_history.json")

    topics = settings["content"]["topics"]
    formats = settings["content"]["formats"]
    partners = _get_active_partners(partners_config)

    if not partners:
        raise ValueError(
            "Нет активных партнёрок в config/partners.yaml\n"
            "Проверь что у партнёрок active: true и status: active"
        )

    # Выбираем тему и формат
    topic = _get_unused_topic(topics, history)
    format_ = _get_unused_format(formats, history)
    partner = _get_partner_for_topic(topic, partners)

    # Формируем план
    plan = {
        "created_at": datetime.now().isoformat(),
        "platform": "telegram",
        "topic": topic,
        "format": format_,
        "product": {
            "id": partner["id"],
            "name": partner["name"],
            "description": partner["description"],
            "category": partner["category"],
            "affiliate_link": partner["affiliate_link"],
            "free_trial": partner.get("free_trial", False),
            "status": partner.get("status", "active"),
        },
        "language": "ru",
        "cta": "Попробовать бесплатно" if partner.get("free_trial") else "Узнать подробнее",
    }

    # Сохраняем в историю
    history.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "topic": topic,
        "format": format_,
        "product": partner["id"],
    })

    # Храним только последние 30 записей
    if len(history) > 30:
        history = history[-30:]

    _save_json("data/topic_history.json", history)

    return plan


# ============================================================
# ТЕСТ — запускаем несколько тем для проверки скоринга
# ============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("STRATEGIST TEST")
    print("=" * 55)

    # Загружаем партнёров для тестирования скоринга
    partners_config = _load_yaml("config/partners.yaml")
    partners = _get_active_partners(partners_config)

    print(f"\n✅ Активных партнёрок: {len(partners)}")
    for p in partners:
        print(f"   - {p['name']} ({p['category']})")

    # Тестируем скоринг на конкретных темах
    test_topics = [
        "AI для написания текстов",
        "AI для создания видео",
        "AI для дизайна",
        "AI для озвучки и голоса",
        "AI для продаж и маркетинга",
        "No-code AI автоматизация",
        "Сравнение AI-сервисов",
    ]

    print("\n" + "=" * 55)
    print("ТЕСТ СКОРИНГА ПО ТЕМАМ")
    print("=" * 55)

    for test_topic in test_topics:
        _get_partner_for_topic(test_topic, partners)

    # Запускаем полный pipeline
    print("\n" + "=" * 55)
    print("ПОЛНЫЙ ЗАПУСК")
    print("=" * 55)

    plan = create_content_plan()

    print(f"\n📅 Дата:      {plan['created_at'][:10]}")
    print(f"💡 Тема:      {plan['topic']}")
    print(f"📝 Формат:    {plan['format']}")
    print(f"🛍️  Продукт:   {plan['product']['name']}")
    print(f"📂 Категория: {plan['product']['category']}")
    print(f"🔗 Ссылка:    {plan['product']['affiliate_link']}")
    print(f"📣 CTA:       {plan['cta']}")
    print(f"⚡ Статус:    {plan['product']['status']}")

    print("\n" + "=" * 55)
    print("Полный план (JSON):")
    print("=" * 55)
    print(json.dumps(plan, ensure_ascii=False, indent=2))