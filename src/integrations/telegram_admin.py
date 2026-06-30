import os
import asyncio
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def _get_bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не найден в .env")
    return token


def _get_admin_chat_id() -> str:
    chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()
    if not chat_id:
        raise ValueError("TELEGRAM_ADMIN_CHAT_ID не найден в .env")
    return chat_id


def _build_x_url(tweet_text: str) -> str:
    import urllib.parse
    encoded = urllib.parse.quote(tweet_text, safe="")
    return f"https://twitter.com/intent/tweet?text={encoded}"


async def _send_admin_notification_async(
    telegram_text: str,
    tweet_text: str,
    product_name: str,
    tweet_length: int,
    twitter_format: str,
    using_affiliate: bool,
    cta_link: str,
    has_image: bool,
) -> dict:
    try:
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode

        bot = Bot(token=_get_bot_token())
        admin_id = _get_admin_chat_id()

        # ─── Сообщение 1: Карточка публикации ────────────────
        cta_label = "✅ Affiliate Link" if using_affiliate else "📢 Telegram канал"
        image_label = "✅ Да" if has_image else "❌ Нет"

        card_text = (
            f"🚀 <b>НОВАЯ ПУБЛИКАЦИЯ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🛍 <b>Продукт:</b> {product_name}\n"
            f"🖼 <b>Изображение:</b> {image_label}\n"
            f"🔗 <b>CTA:</b> {cta_label}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>ТЕКСТ ПОСТА:</b>\n\n"
            f"{telegram_text[:1000]}"
            f"{'...' if len(telegram_text) > 1000 else ''}"
        )

        await bot.send_message(
            chat_id=admin_id,
            text=card_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

        # ─── Сообщение 2: Твит с кнопками ────────────────────
        x_url = _build_x_url(tweet_text)

        # Индикатор длины
        length_bar = _build_length_bar(tweet_length)

        tweet_card = (
            f"🐦 <b>ТВИТ ДЛЯ X ГОТОВ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 Формат: <b>{twitter_format}</b>\n"
            f"📏 Длина: <b>{tweet_length}/280</b> {length_bar}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{tweet_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👆 Нажми кнопку чтобы опубликовать"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="🐦 Открыть в X и опубликовать",
                    url=x_url,
                ),
            ],
        ])

        await bot.send_message(
            chat_id=admin_id,
            text=tweet_card,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )

        return {
            "success": True,
            "admin_id": admin_id,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def _build_length_bar(length: int) -> str:
    """
    Визуальный индикатор длины твита.
    """
    MAX = 280
    percent = length / MAX
    filled = int(percent * 10)
    empty = 10 - filled

    if percent < 0.7:
        color = "🟢"
    elif percent < 0.9:
        color = "🟡"
    else:
        color = "🔴"

    bar = "█" * filled + "░" * empty
    return f"{color} [{bar}]"


def send_admin_notification(
    telegram_text: str,
    tweet_result: dict,
    publish_result: dict,
) -> dict:
    """
    Отправляет уведомление администратору после публикации.
    """
    product_name = publish_result.get("plan", {}).get(
        "product", {}
    ).get("name", "Unknown")

    tweet_text = tweet_result.get("tweet_text", "")
    tweet_length = tweet_result.get("tweet_length", 0)
    twitter_format = tweet_result.get("twitter_format", "Hook")
    using_affiliate = tweet_result.get("using_affiliate_link", False)
    cta_link = tweet_result.get("cta_link", "")
    has_image = publish_result.get("has_image", False)

    if not tweet_text:
        return {
            "success": False,
            "error": "Нет текста твита для отправки",
        }

    result = asyncio.run(
        _send_admin_notification_async(
            telegram_text=telegram_text,
            tweet_text=tweet_text,
            product_name=product_name,
            tweet_length=tweet_length,
            twitter_format=twitter_format,
            using_affiliate=using_affiliate,
            cta_link=cta_link,
            has_image=has_image,
        )
    )

    return result


if __name__ == "__main__":
    print("=== TELEGRAM ADMIN TEST ===")

    test_telegram_text = (
        "🤖 Тестируем Writesonic — AI-копирайтер который пишет за тебя.\n\n"
        "Что умеет:\n"
        "• Создаёт посты для соцсетей\n"
        "• Пишет SEO-статьи\n"
        "• Генерирует рекламные тексты\n\n"
        "Попробуй бесплатно 👉 https://t.me/nejroavtomatizacia"
    )

    test_tweet_result = {
        "success": True,
        "tweet_text": (
            "Тратишь часы на написание постов? 😤\n"
            "А мог бы за 30 секунд.\n"
            "Writesonic пишет вместо тебя — посты, статьи, рекламу.\n"
            "Попробуй: https://t.me/nejroavtomatizacia"
        ),
        "tweet_length": 187,
        "twitter_format": "Problem",
        "using_affiliate_link": False,
        "cta_link": "https://t.me/nejroavtomatizacia",
    }

    test_publish_result = {
        "success": True,
        "plan": {
            "product": {"name": "Writesonic"},
        },
        "has_image": True,
    }

    result = send_admin_notification(
        telegram_text=test_telegram_text,
        tweet_result=test_tweet_result,
        publish_result=test_publish_result,
    )

    if result["success"]:
        print(f"✅ Уведомление отправлено!")
    else:
        print(f"❌ Ошибка: {result['error']}")