import sys
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.agents.strategist import create_content_plan
from src.agents.copywriter import write_post
from src.agents.editor import edit_post
from src.agents.designer import create_image_for_post
from src.agents.analyst import log_publication, print_report
from src.integrations.telegram_client import send_message
from src.integrations.x_client import create_x_draft, print_drafts_report


async def _send_with_image(text: str, image_path: str, channel_id: str) -> dict:
    """Отправляет фото с подписью в Telegram"""
    try:
        from telegram import Bot
        from telegram.constants import ParseMode

        bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
        MAX_CAPTION = 1024

        if len(text) <= MAX_CAPTION:
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


def run_pipeline() -> dict:
    """
    Запускает полный цикл:
    Strategist → Copywriter → Editor → Designer → Publisher → X Draft → Analyst
    """
    print("\n" + "=" * 55)
    print("🤖 AI AFFILIATE AGENTS — ЗАПУСК ПАЙПЛАЙНА")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    # ─── Шаг 1: Strategist ───────────────────────────────
    print("\n1️⃣  STRATEGIST: выбираю тему и продукт...")
    try:
        plan = create_content_plan()
        print(f"   ✅ Тема:    {plan['topic']}")
        print(f"   ✅ Формат:  {plan['format']}")
        print(f"   ✅ Продукт: {plan['product']['name']}")
    except Exception as e:
        print(f"   ❌ Ошибка Strategist: {e}")
        return {"success": False, "step": "strategist", "error": str(e)}

    # ─── Шаг 2: Copywriter ───────────────────────────────
    print("\n2️⃣  COPYWRITER: пишу пост...")
    try:
        copywriter_result = write_post(plan)
        print(f"   ✅ Черновик готов ({len(copywriter_result['draft_text'])} символов)")
        print(f"   ✅ AI провайдер: {copywriter_result['ai_source']}")
    except Exception as e:
        print(f"   ❌ Ошибка Copywriter: {e}")
        return {"success": False, "step": "copywriter", "error": str(e)}

    # ─── Шаг 3: Editor ───────────────────────────────────
    print("\n3️⃣  EDITOR: редактирую и проверяю...")
    try:
        editor_result = edit_post(copywriter_result)
        print(f"   ✅ Готов к публикации: {editor_result['ready']}")
        print(f"   ✅ Длина финального текста: {editor_result['length']} символов")
        if editor_result["issues"]:
            print(f"   ⚠️  Замечания: {editor_result['issues']}")
    except Exception as e:
        print(f"   ❌ Ошибка Editor: {e}")
        return {"success": False, "step": "editor", "error": str(e)}

    # ─── Шаг 4: Designer ─────────────────────────────────
    print("\n4️⃣  DESIGNER: создаю картинку...")
    image_path = None
    try:
        image_path = create_image_for_post(plan)
        if image_path:
            print(f"   ✅ Картинка создана: {image_path}")
        else:
            print(f"   ⚠️  Картинка не создана — публикуем без фото")
    except Exception as e:
        print(f"   ⚠️  Ошибка Designer (не критично): {e}")

    # ─── Шаг 5: Publisher Telegram ───────────────────────
    print("\n5️⃣  PUBLISHER: публикую в Telegram...")
    try:
        channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "")
        text = editor_result["final_text"]

        if image_path and os.path.exists(image_path):
            result = asyncio.run(
                _send_with_image(text, image_path, channel_id)
            )
        else:
            result = send_message(text, channel_id)

        if result["success"]:
            print(f"   ✅ Опубликовано! Message ID: {result['message_id']}")
            print(f"   ✅ Канал: {result['channel']}")

            publish_result = {
                "success": True,
                "platform": "telegram",
                "message_id": result["message_id"],
                "channel": result["channel"],
                "plan": plan,
                "final_text": text,
                "length": editor_result["length"],
                "ai_source": copywriter_result["ai_source"],
                "has_image": image_path is not None,
            }
        else:
            print(f"   ❌ Ошибка публикации: {result['error']}")
            return {
                "success": False,
                "step": "publisher",
                "error": result["error"],
            }

    except Exception as e:
        print(f"   ❌ Ошибка Publisher: {e}")
        return {"success": False, "step": "publisher", "error": str(e)}

    # ─── Шаг 6: X Draft ──────────────────────────────────
    print("\n6️⃣  X DRAFT: создаю пост для Twitter/X...")
    try:
        x_result = create_x_draft(editor_result)
        if x_result["success"]:
            print(f"   ✅ Draft создан! ({x_result['tweet_length']} символов)")
            print(f"   📁 Файл: {x_result['draft_file']}")
        else:
            print(f"   ⚠️  Ошибка создания draft")
    except Exception as e:
        print(f"   ⚠️  Ошибка X Draft (не критично): {e}")

    # ─── Шаг 7: Analyst ──────────────────────────────────
    print("\n7️⃣  ANALYST: записываю в лог...")
    try:
        log_row = log_publication(publish_result)
        print(f"   ✅ Лог сохранён: {log_row['date']} {log_row['time']}")
    except Exception as e:
        print(f"   ⚠️  Ошибка логирования (не критично): {e}")

    # ─── Итог ────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("🎉 ПАЙПЛАЙН ЗАВЕРШЁН УСПЕШНО!")
    print(f"   Тема:      {plan['topic']}")
    print(f"   Продукт:   {plan['product']['name']}")
    print(f"   Ссылка:    {plan['product']['affiliate_link']}")
    print(f"   Telegram:  ✅ Опубликовано")
    print(f"   Twitter/X: 📝 Draft готов")
    print(f"   С фото:    {'Да ✅' if image_path else 'Нет ⚠️'}")
    print("=" * 55 + "\n")

    return {
        "success": True,
        "plan": plan,
        "message_id": publish_result["message_id"],
        "length": editor_result["length"],
        "ai_source": copywriter_result["ai_source"],
        "has_image": image_path is not None,
    }


def run_report() -> None:
    """Показывает отчёт по всем публикациям"""
    print_report()
    print_drafts_report()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        run_report()
    else:
        run_pipeline()