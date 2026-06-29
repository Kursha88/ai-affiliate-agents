import os
import json
import asyncio
import random
import urllib.parse
from datetime import datetime
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()

DRAFTS_DIR = "data/drafts"
DRAFTS_FILE = "data/x_drafts.json"


def _ensure_dirs() -> None:
    os.makedirs(DRAFTS_DIR, exist_ok=True)


def _load_drafts() -> list:
    if not os.path.exists(DRAFTS_FILE):
        return []
    try:
        with open(DRAFTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_drafts(drafts: list) -> None:
    with open(DRAFTS_FILE, "w", encoding="utf-8") as f:
        json.dump(drafts, f, ensure_ascii=False, indent=2)


def _get_channel_link() -> str:
    username = os.getenv("TELEGRAM_CHANNEL_USERNAME", "@nejroavtomatizacia")
    username = username.replace("@", "").strip()
    return f"https://t.me/{username}"


def _get_product_benefit(product: Dict, topic: str) -> str:
    """
    Возвращает короткую выгоду продукта для твита.
    """
    category = product.get("category", "").lower()
    description = product.get("description", "")

    if "voice" in category or "голос" in topic.lower() or "озвуч" in topic.lower():
        return "быстро делать озвучку без студии и микрофона"

    if "video" in category or "видео" in topic.lower():
        return "превращать идеи и текст в видео быстрее"

    if "writing" in category or "текст" in topic.lower():
        return "быстрее писать тексты, посты и идеи для контента"

    if "sales" in category or "продаж" in topic.lower():
        return "автоматизировать продажи, письма и работу с лидами"

    if "automation" in category or "автоматизац" in topic.lower():
        return "собирать AI-автоматизации без сложного кода"

    if "content" in category or "контент" in topic.lower():
        return "делать больше контента из одной идеи"

    if description:
        short = description[:95].strip()
        return short + "..." if len(description) > 95 else short

    return "экономить время на рутинных задачах"


def _is_affiliate_active(plan: Dict) -> bool:
    """
    Проверяет, активна ли партнёрская ссылка.
    Пока status не active — в Twitter ведём на Telegram-канал.
    """
    product = plan.get("product", {})
    status = product.get("status", "pending")
    affiliate_link = product.get("affiliate_link", "")

    return (
        status == "active"
        and affiliate_link.startswith("https://")
        and "t.me/" not in affiliate_link
    )


def _build_promotional_tweet(plan: Dict) -> str:
    """
    Создаёт более интересный и продающий твит.
    Пока партнёрка не активна — основной CTA ведёт в Telegram.
    """
    product = plan.get("product", {})
    product_name = product.get("name", "AI-инструмент")
    topic = plan.get("topic", "AI-инструменты")
    affiliate_link = product.get("affiliate_link", "")
    channel_link = _get_channel_link()

    benefit = _get_product_benefit(product, topic)
    affiliate_active = _is_affiliate_active(plan)

    hooks = [
        f"Нашёл AI-инструмент, который помогает {benefit} 👇",
        f"Если работаешь с контентом, этот AI-сервис стоит посмотреть 👀",
        f"Каждый день разбираю AI-инструменты, которые экономят время ⚡",
        f"{product_name} — один из сервисов, который стоит добавить в AI-арсенал 🤖",
        f"Хочешь быстрее разбираться в AI-инструментах? Лови находку 👇",
    ]

    hook = random.choice(hooks)

    if affiliate_active:
        footer = (
            f"🔗 Попробовать: {affiliate_link}\n"
            f"📢 Больше AI-находок: {channel_link}"
        )
    else:
        footer = (
            f"Больше таких AI-находок публикую в Telegram:\n"
            f"👉 {channel_link}"
        )

    hashtags = "#AI #нейросети #AItools"

    tweet = (
        f"{hook}\n\n"
        f"Сегодня разбираю {product_name}: {benefit}.\n\n"
        f"{footer}\n\n"
        f"{hashtags}"
    )

    # Twitter/X лимит 280 символов
    if len(tweet) > 280:
        shorter = (
            f"{hook}\n\n"
            f"{product_name}: {benefit}.\n\n"
            f"{footer}\n\n"
            f"{hashtags}"
        )
        tweet = shorter

    if len(tweet) > 280:
        # Финальная короткая версия
        tweet = (
            f"{product_name}: {benefit}.\n\n"
            f"Больше AI-инструментов в Telegram:\n"
            f"👉 {channel_link}\n\n"
            f"{hashtags}"
        )

    if len(tweet) > 280:
        tweet = tweet[:277] + "..."

    return tweet


async def _send_notification_async(
    tweet_text: str,
    image_path: Optional[str],
    topic: str,
    product: str,
) -> bool:
    """
    Отправляет владельцу в Telegram:
    1. картинку для Twitter/X;
    2. готовый текст твита;
    3. кнопку открыть X с уже вставленным текстом.
    """
    owner_id = os.getenv("TELEGRAM_OWNER_ID", "").strip()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    if not owner_id or not bot_token:
        print("   ⚠️  TELEGRAM_OWNER_ID не задан — уведомление не отправлено")
        return False

    try:
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

        bot = Bot(token=bot_token)

        # 1. Отправляем картинку, если она есть
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as photo:
                await bot.send_photo(
                    chat_id=owner_id,
                    photo=photo,
                    caption=(
                        "🖼 Картинка для Twitter/X\n\n"
                        "Сохрани её на телефон и прикрепи к твиту."
                    ),
                )

        # 2. Кнопка открыть X с готовым текстом
        encoded_text = urllib.parse.quote(tweet_text)
        twitter_intent_url = f"https://twitter.com/intent/tweet?text={encoded_text}"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🐦 Открыть X с текстом",
                    url=twitter_intent_url
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 Открыть Telegram-канал",
                    url=_get_channel_link()
                )
            ]
        ])

        # 3. Отправляем чистый текст твита отдельным сообщением
        message = (
            f"🐦 Новый твит готов к публикации!\n\n"
            f"Тема: {topic}\n"
            f"Продукт: {product}\n\n"
            f"Скопируй текст ниже или нажми кнопку:\n\n"
            f"────────────────────\n\n"
            f"{tweet_text}\n\n"
            f"────────────────────"
        )

        await bot.send_message(
            chat_id=owner_id,
            text=message,
            reply_markup=keyboard,
        )

        return True

    except Exception as e:
        print(f"   ⚠️  Ошибка отправки уведомления: {e}")
        return False


def create_x_draft(editor_result: Dict, image_path: Optional[str] = None) -> Dict:
    """
    Создаёт draft пост для Twitter/X и отправляет уведомление владельцу.
    """
    _ensure_dirs()

    plan = editor_result.get("plan", {})
    product = plan.get("product", {})
    topic = plan.get("topic", "")
    product_name = product.get("name", "")

    tweet_text = _build_promotional_tweet(plan)

    draft = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "created_at": datetime.now().isoformat(),
        "platform": "twitter/x",
        "topic": topic,
        "product": product_name,
        "tweet_text": tweet_text,
        "tweet_length": len(tweet_text),
        "status": "draft",
        "image_path": image_path,
    }

    drafts = _load_drafts()
    drafts.append(draft)

    if len(drafts) > 50:
        drafts = drafts[-50:]

    _save_drafts(drafts)

    draft_filename = f"{DRAFTS_DIR}/tweet_{draft['id']}.txt"
    with open(draft_filename, "w", encoding="utf-8") as f:
        f.write("=== TWEET DRAFT ===\n")
        f.write(f"Date: {draft['created_at'][:10]}\n")
        f.write(f"Topic: {draft['topic']}\n")
        f.write(f"Product: {draft['product']}\n")
        f.write(f"Length: {draft['tweet_length']} chars\n")
        f.write("=" * 40 + "\n\n")
        f.write(draft["tweet_text"])
        f.write("\n\n" + "=" * 40 + "\n")

    try:
        sent = asyncio.run(
            _send_notification_async(
                tweet_text=tweet_text,
                image_path=image_path,
                topic=topic,
                product=product_name,
            )
        )
        if sent:
            print("   📱 Уведомление с твитом отправлено в Telegram!")
    except Exception as e:
        print(f"   ⚠️  Уведомление не отправлено: {e}")

    return {
        "success": True,
        "draft_id": draft["id"],
        "tweet_text": tweet_text,
        "tweet_length": len(tweet_text),
        "draft_file": draft_filename,
        "image_path": image_path,
    }


def get_pending_drafts() -> list:
    drafts = _load_drafts()
    return [d for d in drafts if d.get("status") == "draft"]


def mark_as_published(draft_id: str) -> bool:
    drafts = _load_drafts()

    for draft in drafts:
        if draft.get("id") == draft_id:
            draft["status"] = "published"
            draft["published_at"] = datetime.now().isoformat()
            _save_drafts(drafts)
            return True

    return False


def print_drafts_report() -> None:
    drafts = _load_drafts()
    pending = [d for d in drafts if d.get("status") == "draft"]
    published = [d for d in drafts if d.get("status") == "published"]

    print("\n" + "=" * 50)
    print("🐦 TWITTER/X DRAFTS REPORT")
    print("=" * 50)
    print(f"📝 Всего драфтов:      {len(drafts)}")
    print(f"⏳ Ожидают публикации: {len(pending)}")
    print(f"✅ Опубликовано:       {len(published)}")
    print("=" * 50)


if __name__ == "__main__":
    from src.agents.strategist import create_content_plan
    from src.agents.copywriter import write_post
    from src.agents.editor import edit_post
    from src.agents.designer import create_image_for_post

    print("=== X/TWITTER DRAFT TEST ===\n")

    plan = create_content_plan()
    copywriter_result = write_post(plan)
    editor_result = edit_post(copywriter_result)
    image_path = create_image_for_post(plan)

    print(f"Тема: {plan['topic']}")
    print(f"Продукт: {plan['product']['name']}")
    print("\nСоздаём Twitter draft и отправляем уведомление...")

    result = create_x_draft(editor_result, image_path=image_path)

    print(f"\n✅ Draft создан! ({result['tweet_length']} символов)")
    print(f"📁 Файл: {result['draft_file']}")
    print(f"🖼 Картинка: {result['image_path']}")

    print("\nТЕКСТ ТВИТА:")
    print("=" * 50)
    print(result["tweet_text"])
    print("=" * 50)

    print_drafts_report()