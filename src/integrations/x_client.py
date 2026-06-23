import os
import json
from datetime import datetime
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# Папка для draft постов
DRAFTS_DIR = "data/drafts"
DRAFTS_FILE = "data/x_drafts.json"


def _ensure_dirs() -> None:
    """Создаёт нужные папки"""
    os.makedirs(DRAFTS_DIR, exist_ok=True)


def _load_drafts() -> list:
    """Загружает список драфтов"""
    if not os.path.exists(DRAFTS_FILE):
        return []
    try:
        with open(DRAFTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_drafts(drafts: list) -> None:
    """Сохраняет список драфтов"""
    with open(DRAFTS_FILE, "w", encoding="utf-8") as f:
        json.dump(drafts, f, ensure_ascii=False, indent=2)


def _adapt_for_twitter(telegram_text: str, affiliate_link: str) -> str:
    """
    Адаптирует Telegram пост для Twitter/X:
    - Убирает HTML теги
    - Сокращает до 280 символов
    - Добавляет хэштеги
    - Оставляет ссылку
    """
    import re

    # Убираем HTML теги
    text = re.sub(r'<[^>]+>', '', telegram_text)

    # Убираем пометку о партнёрской ссылке
    disclosure_patterns = [
        r'⚠️.*?для вас\.',
        r'Ссылка может быть партнёрской.*?для вас\.',
    ]
    for pattern in disclosure_patterns:
        text = re.sub(pattern, '', text, flags=re.DOTALL)

    # Убираем лишние переносы
    text = re.sub(r'\n{2,}', '\n', text)
    text = text.strip()

    # Добавляем хэштеги
    hashtags = "\n\n#AI #AItools #искусственныйинтеллект #нейросети"

    # Максимальная длина твита с учётом ссылки и хэштегов
    # Twitter считает ссылки как 23 символа
    link_length = 23
    hashtags_length = len(hashtags)
    max_text_length = 280 - link_length - hashtags_length - 2  # 2 для переносов

    # Обрезаем текст если нужно
    if len(text) > max_text_length:
        text = text[:max_text_length - 3] + "..."

    # Собираем финальный твит
    tweet = f"{text}\n\n{affiliate_link}{hashtags}"

    return tweet


def create_x_draft(editor_result: Dict) -> Dict:
    """
    Создаёт draft пост для Twitter/X на основе результата Editor.
    Сохраняет в файл для ручной публикации.
    """
    _ensure_dirs()

    plan = editor_result.get("plan", {})
    telegram_text = editor_result.get("final_text", "")
    affiliate_link = plan.get("product", {}).get("affiliate_link", "")

    # Адаптируем текст для Twitter
    tweet_text = _adapt_for_twitter(telegram_text, affiliate_link)

    draft = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "created_at": datetime.now().isoformat(),
        "platform": "twitter/x",
        "topic": plan.get("topic", ""),
        "product": plan.get("product", {}).get("name", ""),
        "affiliate_link": affiliate_link,
        "tweet_text": tweet_text,
        "tweet_length": len(tweet_text),
        "status": "draft",
        "telegram_text": telegram_text[:200] + "..." if len(telegram_text) > 200 else telegram_text,
    }

    # Сохраняем в список драфтов
    drafts = _load_drafts()
    drafts.append(draft)

    # Храним только последние 50 драфтов
    if len(drafts) > 50:
        drafts = drafts[-50:]

    _save_drafts(drafts)

    # Также сохраняем как отдельный текстовый файл для удобства
    draft_filename = f"{DRAFTS_DIR}/tweet_{draft['id']}.txt"
    with open(draft_filename, "w", encoding="utf-8") as f:
        f.write(f"=== TWEET DRAFT ===\n")
        f.write(f"Date: {draft['created_at'][:10]}\n")
        f.write(f"Topic: {draft['topic']}\n")
        f.write(f"Product: {draft['product']}\n")
        f.write(f"Length: {draft['tweet_length']} chars\n")
        f.write(f"{'='*40}\n\n")
        f.write(draft['tweet_text'])
        f.write(f"\n\n{'='*40}\n")
        f.write(f"Copy the text above and post to Twitter/X\n")

    return {
        "success": True,
        "draft_id": draft["id"],
        "tweet_text": tweet_text,
        "tweet_length": len(tweet_text),
        "draft_file": draft_filename,
    }


def get_pending_drafts() -> list:
    """Возвращает список неопубликованных драфтов"""
    drafts = _load_drafts()
    return [d for d in drafts if d.get("status") == "draft"]


def mark_as_published(draft_id: str) -> bool:
    """Помечает драфт как опубликованный"""
    drafts = _load_drafts()
    for draft in drafts:
        if draft.get("id") == draft_id:
            draft["status"] = "published"
            draft["published_at"] = datetime.now().isoformat()
            _save_drafts(drafts)
            return True
    return False


def print_drafts_report() -> None:
    """Выводит отчёт по драфтам"""
    drafts = _load_drafts()
    pending = [d for d in drafts if d.get("status") == "draft"]
    published = [d for d in drafts if d.get("status") == "published"]

    print("\n" + "=" * 50)
    print("🐦 TWITTER/X DRAFTS REPORT")
    print("=" * 50)
    print(f"📝 Всего драфтов:      {len(drafts)}")
    print(f"⏳ Ожидают публикации: {len(pending)}")
    print(f"✅ Опубликовано:       {len(published)}")

    if pending:
        print(f"\n📋 Последние драфты для публикации:")
        for draft in pending[-3:]:
            print(f"\n  ID: {draft['id']}")
            print(f"  Тема: {draft['topic']}")
            print(f"  Продукт: {draft['product']}")
            print(f"  Длина: {draft['tweet_length']} символов")
            print(f"  Файл: data/drafts/tweet_{draft['id']}.txt")

    print("=" * 50)


if __name__ == "__main__":
    from src.agents.strategist import create_content_plan
    from src.agents.copywriter import write_post
    from src.agents.editor import edit_post

    print("=== X/TWITTER DRAFT TEST ===\n")

    plan = create_content_plan()
    copywriter_result = write_post(plan)
    editor_result = edit_post(copywriter_result)

    print(f"Тема: {plan['topic']}")
    print(f"Продукт: {plan['product']['name']}")
    print("\nСоздаём Twitter draft...")

    result = create_x_draft(editor_result)

    print(f"\n✅ Draft создан!")
    print(f"📁 Файл: {result['draft_file']}")
    print(f"📏 Длина: {result['tweet_length']} символов")
    print(f"\n{'='*50}")
    print("ТЕКСТ ТВИТА:")
    print("=" * 50)
    print(result["tweet_text"])
    print("=" * 50)

    print_drafts_report()