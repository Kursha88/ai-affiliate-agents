import os
import asyncio
from typing import Dict, Optional

from src.agents.base_publisher import BasePublisher
from src.core.config import Config


class TelegramPublisher(BasePublisher):
    """
    Публикатор для Telegram канала.
    Поддерживает отправку текста и фото с подписью.
    """
    platform = "telegram"
    max_length = 4096
    supports_markdown = True
    supports_images = True

    def format_content(self, editor_result: Dict) -> str:
        """Telegram поддерживает полный текст как есть."""
        return editor_result["final_text"]

    def publish(
        self,
        content: str,
        editor_result: Dict,
        image_path: Optional[str] = None,
    ) -> Dict:
        """
        Отправляет сообщение в Telegram канал.
        Если есть картинка — отправляет фото с подписью.
        Если текст длиннее лимита — фото и текст отдельно.
        """
        channel_id = Config.TELEGRAM_CHANNEL_ID

        if image_path and os.path.exists(image_path):
            result = asyncio.run(
                self._send_with_image(content, image_path, channel_id)
            )
        else:
            from src.integrations.telegram_client import send_message
            result = send_message(content, channel_id)

        if result["success"]:
            return self._success_result(
                editor_result=editor_result,
                message_id=result["message_id"],
                channel=result["channel"],
                final_text=content,
                has_image=image_path is not None,
            )
        else:
            return self._error_result(
                error=result["error"],
                editor_result=editor_result,
            )

    async def _send_with_image(
        self,
        text: str,
        image_path: str,
        channel_id: str,
    ) -> dict:
        """
        Отправляет фото с подписью в Telegram.
        Если текст длиннее MAX_CAPTION — фото и текст отдельно.
        """
        try:
            from telegram import Bot
            from telegram.constants import ParseMode

            bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
            max_caption = Config.MAX_CAPTION_LENGTH

            if len(text) <= max_caption:
                with open(image_path, "rb") as photo:
                    message = await bot.send_photo(
                        chat_id=channel_id,
                        photo=photo,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    )
            else:
                with open(image_path, "rb") as photo:
                    await bot.send_photo(
                        chat_id=channel_id,
                        photo=photo,
                    )
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

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "channel": channel_id,
            }


def publish_post(
    editor_result: Dict,
    image_path: Optional[str] = None,
) -> Dict:
    """
    Публичный интерфейс для main.py и других модулей.
    Создаёт TelegramPublisher и публикует.
    """
    publisher = TelegramPublisher()
    return publisher.publish_from_editor(editor_result, image_path)