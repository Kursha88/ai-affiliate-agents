import os
import json
from datetime import datetime
from typing import Dict, List


POSTS_FILE = "data/published_posts.csv"
ANALYTICS_FILE = "data/analytics.csv"

HEADERS = [
    "date", "time", "platform", "topic", "format",
    "product", "ai_source", "post_length", "message_id", "status"
]


def _ensure_file(filepath: str, headers: List[str]) -> None:
    """Создаёт файл с заголовками если не существует или пустой"""
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            f.write(",".join(headers) + "\n")


def _read_posts() -> List[Dict]:
    """Читает все посты из CSV"""
    if not os.path.exists(POSTS_FILE):
        return []

    with open(POSTS_FILE, "r", encoding="utf-8", newline="") as f:
        lines = f.readlines()

    if len(lines) < 2:
        return []

    headers = [h.strip() for h in lines[0].strip().split(",")]
    posts = []

    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        values = line.split(",")
        while len(values) < len(headers):
            values.append("")
        post = dict(zip(headers, values))
        posts.append(post)

    return posts


def log_publication(publish_result: Dict) -> Dict:
    """
    Записывает успешную публикацию в CSV лог.
    """
    _ensure_file(POSTS_FILE, HEADERS)

    now = datetime.now()
    plan = publish_result.get("plan", {})
    product = plan.get("product", {})

    row = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "platform": publish_result.get("platform", "telegram"),
        "topic": plan.get("topic", "").replace(",", ";"),
        "format": plan.get("format", "").replace(",", ";"),
        "product": product.get("name", "").replace(",", ";"),
        "ai_source": publish_result.get("ai_source", ""),
        "post_length": str(publish_result.get("length", 0)),
        "message_id": str(publish_result.get("message_id", "")),
        "status": "published" if publish_result.get("success") else "failed",
    }

    # Проверяем что файл заканчивается на новую строку
    with open(POSTS_FILE, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size > 0:
            f.seek(-1, 2)
            last_char = f.read(1)
        else:
            last_char = b"\n"

    with open(POSTS_FILE, "a", encoding="utf-8", newline="") as f:
        if last_char != b"\n":
            f.write("\n")
        line = ",".join([row[h] for h in HEADERS])
        f.write(line + "\n")

    return row


def get_stats() -> Dict:
    """
    Читает лог и возвращает статистику.
    """
    posts = _read_posts()

    if not posts:
        return {"total": 0, "message": "Нет данных о публикациях"}

    total = len(posts)
    published = len([p for p in posts if p.get("status", "").strip() == "published"])
    failed = len([p for p in posts if p.get("status", "").strip() == "failed"])

    products = {}
    for post in posts:
        product = post.get("product", "unknown").strip()
        if product:
            products[product] = products.get(product, 0) + 1

    topics = {}
    for post in posts:
        topic = post.get("topic", "unknown").strip()
        if topic:
            topics[topic] = topics.get(topic, 0) + 1

    dates = {}
    for post in posts:
        date = post.get("date", "unknown").strip()
        if date:
            dates[date] = dates.get(date, 0) + 1

    ai_sources = {}
    for post in posts:
        source = post.get("ai_source", "unknown").strip()
        if source:
            ai_sources[source] = ai_sources.get(source, 0) + 1

    return {
        "total": total,
        "published": published,
        "failed": failed,
        "products": products,
        "topics": topics,
        "dates": dates,
        "ai_sources": ai_sources,
        "last_post": posts[-1] if posts else None,
    }


def print_report() -> None:
    """
    Выводит красивый отчёт в терминал.
    """
    stats = get_stats()

    print("\n" + "=" * 50)
    print("📊 ОТЧЁТ AI AFFILIATE AGENTS")
    print("=" * 50)

    if stats["total"] == 0:
        print("📭 Публикаций ещё нет")
        return

    print(f"📬 Всего публикаций:  {stats['total']}")
    print(f"✅ Успешных:          {stats['published']}")
    print(f"❌ Неудачных:         {stats['failed']}")

    print(f"\n🛍️  Продукты:")
    for product, count in sorted(
        stats["products"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"   {product}: {count} постов")

    print(f"\n💡 Темы:")
    for topic, count in sorted(
        stats["topics"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"   {topic}: {count} постов")

    print(f"\n🤖 AI провайдеры:")
    for source, count in stats["ai_sources"].items():
        print(f"   {source}: {count} постов")

    print(f"\n📅 По датам:")
    for date, count in sorted(stats["dates"].items()):
        print(f"   {date}: {count} постов")

    if stats.get("last_post"):
        last = stats["last_post"]
        print(f"\n🕐 Последняя публикация:")
        print(f"   {last.get('date', '')} {last.get('time', '')} — {last.get('topic', '')}")

    print("=" * 50)


if __name__ == "__main__":
    print("=== ANALYST TEST ===")
    print_report()