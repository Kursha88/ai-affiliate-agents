from typing import Dict
from src.integrations.telegram_client import send_message


def publish_post(editor_result: Dict) -> Dict:
    """
    Публикует готовый пост в Telegram.
    Принимает результат от Editor.
    """
    if not editor_result.get("ready"):
        return {
            "success": False,
            "error": f"Пост не готов: {editor_result.get('issues')}",
            "plan": editor_result["plan"],
        }

    text = editor_result["final_text"]
    plan = editor_result["plan"]

    # Публикуем в Telegram
    result = send_message(text)

    if result["success"]:
        return {
            "success": True,
            "platform": "telegram",
            "message_id": result["message_id"],
            "channel": result["channel"],
            "plan": plan,
            "final_text": text,
            "length": editor_result["length"],
            "ai_source": editor_result["ai_source"],
        }
    else:
        return {
            "success": False,
            "error": result["error"],
            "plan": plan,
            "final_text": text,
        }


if __name__ == "__main__":
    from src.agents.strategist import create_content_plan
    from src.agents.copywriter import write_post
    from src.agents.editor import edit_post

    print("=== PUBLISHER TEST ===\n")
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
        print(f"📱 Канал: {result['channel']}")
        print(f"🆔 ID сообщения: {result['message_id']}")
        print(f"📝 Тема: {result['plan']['topic']}")
        print(f"🛍️  Продукт: {result['plan']['product']['name']}")
        print(f"📏 Длина: {result['length']} символов")
    else:
        print(f"❌ ОШИБКА ПУБЛИКАЦИИ")
        print(f"Причина: {result['error']}")
    print("=" * 50)