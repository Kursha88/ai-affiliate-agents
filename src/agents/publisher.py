from typing import Dict
from src.agents.base_publisher import BasePublisher
from src.integrations.telegram_client import send_message


class TelegramPublisher(BasePublisher):
    """
    Публикатор для Telegram канала.
    """
    platform = "telegram"
    max_length = 4096
    supports_markdown = True
    supports_images = True

    def format_content(self, editor_result: Dict) -> str:
        """Telegram поддерживает полный текст как есть."""
        return editor_result["final_text"]

    def publish(self, content: str, editor_result: Dict) -> Dict:
        """Отправляет сообщение в Telegram канал."""
        result = send_message(content)

        if result["success"]:
            return self._success_result(
                editor_result=editor_result,
                message_id=result["message_id"],
                channel=result["channel"],
                final_text=content,
            )
        else:
            return self._error_result(
                error=result["error"],
                editor_result=editor_result,
            )


def publish_post(editor_result: Dict) -> Dict:
    """
    Обратная совместимость — старый интерфейс.
    Используется в main.py и других местах.
    """
    publisher = TelegramPublisher()
    return publisher.publish_from_editor(editor_result)


if __name__ == "__main__":
    from src.agents.strategist import create_content_plan
    from src.agents.copywriter import write_post
    from src.agents.editor import edit_post

    print("=== TELEGRAM PUBLISHER TEST ===\n")

    print("1️⃣  Strategist: создаёт план...")
    plan = create_content_plan()
    print(f"   Тема: {plan['topic']}")
    print(f"   Продукт: {plan['product']['name']}\n")

    print("2️⃣  Copywriter: пишет пост...")
    copywriter_result = write_post(plan)
    print(f"   Длина черновика: {len(copywriter_result['draft_text'])} символов\n")

    print("3️⃣  Editor: редактирует...")
    editor_result = edit_post(copywriter_result)
    print(f"   Готов: {editor_result['ready']}\n")

    print("4️⃣  Publisher: публикует в Telegram...")
    result = publish_post(editor_result)

    print("\n" + "=" * 50)
    if result["success"]:
        print(f"✅ ПОСТ ОПУБЛИКОВАН!")
        print(f"📱 Платформа: {result['platform']}")
        print(f"📢 Канал: {result['channel']}")
        print(f"🆔 ID сообщения: {result['message_id']}")
        print(f"📝 Тема: {result['topic']}")
        print(f"🛍️  Продукт: {result['product']}")
        print(f"🔗 Ссылка: {result['affiliate_link']}")
        print(f"📏 Длина: {result['length']} символов")
        print(f"⏰ Время: {result['published_at']}")
    else:
        print(f"❌ ОШИБКА: {result['error']}")
    print("=" * 50)