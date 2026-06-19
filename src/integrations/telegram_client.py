import os
import asyncio
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _get_bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не найден в .env файле")
    return token


def _get_channel_id() -> str:
    channel = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel:
        raise ValueError("TELEGRAM_CHANNEL_ID не найден в .env файле")
    return channel


async def _send_message_async(text: str, channel_id: str) -> dict:
    try:
        from telegram import Bot
        from telegram.constants import ParseMode

        bot = Bot(token=_get_bot_token())

        message = await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

        return {
            "success": True,
            "message_id": message.message_id,
            "channel": channel_id,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "channel": channel_id,
        }


def send_message(text: str, channel_id: Optional[str] = None) -> dict:
    """
    Отправляет текстовое сообщение в Telegram канал.
    Если channel_id не указан — берёт из .env
    """
    if not channel_id:
        channel_id = _get_channel_id()

    result = asyncio.run(_send_message_async(text, channel_id))
    return result


def send_test_message() -> dict:
    """
    Отправляет тестовое сообщение в канал.
    """
    test_text = (
        "🤖 <b>Тест системы AI Affiliate Agents</b>\n\n"
        "✅ Система успешно подключена к каналу!\n"
        "✅ Бот работает корректно.\n"
        "✅ Готов к публикации контента.\n\n"
        "<i>Это тестовое сообщение. Скоро здесь появится полезный контент про AI-инструменты!</i>"
    )
    return send_message(test_text)


if __name__ == "__main__":
    print("=== TELEGRAM TEST ===")
    print(f"Канал: {os.getenv('TELEGRAM_CHANNEL_ID', 'не задан')}")
    print("Отправляем тестовое сообщение...")

    result = send_test_message()

    if result["success"]:
        print(f"✅ Сообщение отправлено! ID: {result['message_id']}")
    else:
        print(f"❌ Ошибка: {result['error']}")