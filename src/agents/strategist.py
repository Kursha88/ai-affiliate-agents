import os
import json
import random
import yaml
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Режим работы: "growth" — набор аудитории (без партнёрок)
#               "affiliate" — монетизация через партнёрки
MODE = os.getenv("PIPELINE_MODE", "growth")


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


def _get_unused_format(formats: list, history: list) -> str:
    """Выбирает формат который не использовался недавно."""
    used_formats = [h.get("format") for h in history[-5:]]
    unused = [f for f in formats if f not in used_formats]

    if not unused:
        unused = formats

    return random.choice(unused)


def _get_channel_link() -> str:
    """Возвращает ссылку на Telegram-канал из env."""
    username = os.getenv("TELEGRAM_CHANNEL_USERNAME", "@nejroavtomatizacia")
    username = username.replace("@", "").strip()
    return f"https://t.me/{username}"


def create_content_plan(news_item: Optional[dict] = None) -> dict:
    """
    Основная функция агента Strategist.
    Создаёт план для одного поста.

    В режиме growth (по умолчанию):
      - Использует реальную новость из NewsHunter
      - CTA ведёт на Telegram-канал (не партнёрка)

    В режиме affiliate:
      - Выбирает партнёрку и тему
      - CTA ведёт на партнёрскую ссылку
    """
    settings = _load_yaml("config/settings.yaml")
    history = _load_json("data/topic_history.json")
    formats = settings["content"]["formats"]

    # ─── Режим набора аудитории (growth) ──────────────────────────
    if MODE == "growth":
        channel_link = _get_channel_link()

        # Если есть свежая новость от NewsHunter — используем её
        if news_item and news_item.get("title"):
            topic = news_item["title"]
            news_source = news_item.get("source", "")
            news_url = news_item.get("url", "")
            news_age = news_item.get("age_hours", 0)
            print(f"[Strategist] 📰 Новость: {topic[:60]}...")
        else:
            # Fallback — берём из списка тем
            topics = settings["content"]["topics"]
            used_topics = [h.get("topic") for h in history[-len(topics):]]
            unused = [t for t in topics if t not in used_topics]
            if not unused:
                unused = topics
            topic = random.choice(unused)
            news_source = "editorial"
            news_url = ""
            news_age = 0
            print(f"[Strategist] 📝 Fallback тема: {topic}")

        # Выбираем формат (избегаем повторений)
        format_ = _get_unused_format(formats, history)

        plan = {
            "created_at": datetime.now().isoformat(),
            "mode": "growth",
            "platform": "telegram",
            "topic": topic,
            "format": format_,
            "news": {
                "source": news_source,
                "url": news_url,
                "age_hours": news_age,
            },
            "product": {
                "id": "channel",
                "name": "AI Нейросети | Канал",
                "description": "Telegram-канал про нейросети и AI — свежие новости, инструменты и лайфхаки",
                "category": "Telegram Channel",
                "affiliate_link": channel_link,
                "free_trial": False,
                "status": "active",
            },
            "language": "ru",
            "cta": "Подписаться на канал",
            "cta_link": channel_link,
            "is_affiliate": False,
        }

    # ─── Режим монетизации (affiliate) ─────────────────────────────
    else:
        partners_config = _load_yaml("config/partners.yaml")
        partners = _get_active_partners(partners_config)

        if not partners:
            # Нет активных партнёрок — работаем в growth режиме
            print("[Strategist] Нет активных партнёрок — переключаюсь в growth режим")
            return create_content_plan(news_item=news_item)

        topics = settings["content"]["topics"]
        used_topics = [h.get("topic") for h in history[-len(topics):]]
        unused_topics = [t for t in topics if t not in used_topics]
        if not unused_topics:
            unused_topics = topics
        topic = random.choice(unused_topics)

        format_ = _get_unused_format(formats, history)

        # Подбираем партнёра под тему (упрощённая версия)
        partner = random.choice(partners)

        plan = {
            "created_at": datetime.now().isoformat(),
            "mode": "affiliate",
            "platform": "telegram",
            "topic": topic,
            "format": format_,
            "news": {"source": "", "url": "", "age_hours": 0},
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
            "cta_link": partner["affiliate_link"],
            "is_affiliate": True,
        }

    # ─── Сохраняем в историю ───────────────────────────────────────
    history.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "topic": topic,
        "format": format_,
        "product": plan["product"]["id"],
        "mode": plan["mode"],
    })

    # Храним только последние 30 записей
    if len(history) > 30:
        history = history[-30:]

    _save_json("data/topic_history.json", history)

    return plan


# ─── Тест ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json as json_module

    print("=" * 55)
    print("STRATEGIST TEST — Growth Mode")
    print("=" * 55)

    # Тест с новостью
    test_news = {
        "title": "OpenAI выпустила GPT-5 с поддержкой реального времени",
        "url": "https://example.com/gpt5",
        "source": "Hacker News",
        "age_hours": 2.5,
        "summary": "Новая модель умеет работать в реальном времени",
    }

    plan = create_content_plan(news_item=test_news)

    print(f"\n📅 Дата:    {plan['created_at'][:10]}")
    print(f"🔧 Режим:   {plan['mode']}")
    print(f"💡 Тема:    {plan['topic'][:60]}")
    print(f"📝 Формат:  {plan['format']}")
    print(f"🔗 CTA:     {plan['cta']}")
    print(f"📣 Ссылка:  {plan['cta_link']}")
    print(f"📰 Источник: {plan['news']['source']}")

    print("\n" + "=" * 55)
    print("Полный план (JSON):")
    print("=" * 55)
    print(json_module.dumps(plan, ensure_ascii=False, indent=2))