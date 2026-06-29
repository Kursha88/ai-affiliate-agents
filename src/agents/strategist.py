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
    """Возвращает список активных партнёрок"""
    return [p for p in partners_config.get("partners", []) if p.get("active")]


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


def _get_partner_for_topic(topic: str, partners: list) -> dict:
    """
    Подбирает подходящего партнёра под тему.
    Если нет точного совпадения — выбирает случайного.
    """
    topic_lower = topic.lower()

    # Пробуем найти совпадение по категории
    matched = []
    for p in partners:
        category = p.get("category", "").lower()
        description = p.get("description", "").lower()
        if any(word in topic_lower for word in category.split()) or \
           any(word in description for word in topic_lower.split()):
            matched.append(p)

    if matched:
        return random.choice(matched)

    # Если нет совпадения — случайный партнёр
    return random.choice(partners)


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
        raise ValueError("Нет активных партнёрок в config/partners.yaml")

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
    "status": partner.get("status", "pending"),
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


if __name__ == "__main__":
    print("=== STRATEGIST TEST ===\n")

    plan = create_content_plan()

    print(f"📅 Дата:     {plan['created_at'][:10]}")
    print(f"📱 Платформа: {plan['platform']}")
    print(f"💡 Тема:     {plan['topic']}")
    print(f"📝 Формат:   {plan['format']}")
    print(f"🛍️  Продукт:  {plan['product']['name']}")
    print(f"🔗 Ссылка:   {plan['product']['affiliate_link']}")
    print(f"📣 CTA:      {plan['cta']}")
    print(f"\nПолный план:")
    print(json.dumps(plan, ensure_ascii=False, indent=2))