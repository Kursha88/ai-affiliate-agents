import sys
import os
import asyncio
from datetime import datetime

from src.core.config import Config
from src.utils.logger import get_logger
from src.utils.validators import is_fallback_text, validate_content_plan

from src.agents.strategist import create_content_plan
from src.agents.copywriter import write_post
from src.agents.editor import edit_post
from src.agents.designer import create_image_for_post
from src.agents.analyst import log_publication, print_report
from src.integrations.telegram_client import send_message
from src.integrations.x_client import print_drafts_report


async def _send_with_image(text: str, image_path: str, channel_id: str) -> dict:
    """Отправляет фото с подписью в Telegram"""
    try:
        from telegram import Bot
        from telegram.constants import ParseMode

        bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        MAX_CAPTION = Config.MAX_CAPTION_LENGTH

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
    Strategist → Copywriter → Editor → Designer → Publisher
    → Twitter Writer → Admin Notify → Analyst
    """
    log = get_logger()
    Config.ensure_dirs()

    log.header("AI AFFILIATE AGENTS — ЗАПУСК ПАЙПЛАЙНА")

    # ─── Валидация конфигурации ───────────────────────────
    validation = Config.validate()
    if not validation["valid"]:
        for issue in validation["issues"]:
            log.error(issue)
        return {"success": False, "step": "config", "error": validation["issues"]}

    # ─── Шаг 1: Strategist ───────────────────────────────
    log.step(1, "STRATEGIST: выбираю тему и продукт")
    try:
        plan = create_content_plan()

        # Валидируем план
        plan_validation = validate_content_plan(plan)
        if not plan_validation["valid"]:
            log.error(f"Невалидный план: {plan_validation['issues']}")
            return {"success": False, "step": "strategist", "error": str(plan_validation["issues"])}

        log.success(f"Тема:    {plan['topic']}")
        log.success(f"Формат:  {plan['format']}")
        log.success(f"Продукт: {plan['product']['name']}")
    except Exception as e:
        log.error(f"Ошибка Strategist: {e}")
        return {"success": False, "step": "strategist", "error": str(e)}

    # ─── Шаг 2: Copywriter ───────────────────────────────
    log.step(2, "COPYWRITER: пишу пост")
    try:
        copywriter_result = write_post(plan)
        draft = copywriter_result["draft_text"]

        # Защита от fallback текста
        if is_fallback_text(draft):
            log.error("AI вернул fallback текст — останавливаем пайплайн")
            return {
                "success": False,
                "step": "copywriter",
                "error": "AI вернул fallback. Проверь API ключи.",
            }

        log.success(f"Черновик готов ({len(draft)} символов)")
        log.success(f"AI провайдер: {copywriter_result['ai_source']}")
    except Exception as e:
        log.error(f"Ошибка Copywriter: {e}")
        return {"success": False, "step": "copywriter", "error": str(e)}

    # ─── Шаг 3: Editor ───────────────────────────────────
    log.step(3, "EDITOR: редактирую и проверяю")
    try:
        editor_result = edit_post(copywriter_result)
        log.success(f"Готов к публикации: {editor_result['ready']}")
        log.success(f"Длина финального текста: {editor_result['length']} символов")
        if editor_result["issues"]:
            log.warning(f"Замечания: {editor_result['issues']}")
    except Exception as e:
        log.error(f"Ошибка Editor: {e}")
        return {"success": False, "step": "editor", "error": str(e)}

    # ─── Шаг 4: Designer ─────────────────────────────────
    log.step(4, "DESIGNER: создаю картинку")
    image_path = None
    try:
        image_path = create_image_for_post(plan)
        if image_path:
            log.success(f"Картинка создана: {image_path}")
        else:
            log.skip("Картинка не создана — публикуем без фото")
    except Exception as e:
        log.warning(f"Ошибка Designer (не критично): {e}")

    # ─── Шаг 5: Publisher Telegram ───────────────────────
    log.step(5, "PUBLISHER: публикую в Telegram")
    try:
        channel_id = Config.TELEGRAM_CHANNEL_ID
        text = editor_result["final_text"]

        if image_path and os.path.exists(image_path):
            result = asyncio.run(
                _send_with_image(text, image_path, channel_id)
            )
        else:
            result = send_message(text, channel_id)

        if result["success"]:
            log.success(f"Опубликовано! Message ID: {result['message_id']}")
            log.success(f"Канал: {result['channel']}")

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
            log.error(f"Ошибка публикации: {result['error']}")
            return {
                "success": False,
                "step": "publisher",
                "error": result["error"],
            }

    except Exception as e:
        log.error(f"Ошибка Publisher: {e}")
        return {"success": False, "step": "publisher", "error": str(e)}

    # ─── Шаг 6: Twitter Writer ───────────────────────────
    log.step(6, "TWITTER WRITER: создаю вирусный твит для X")
    twitter_result = {"success": False, "tweet_text": ""}
    try:
        from src.agents.twitter_writer import write_twitter_post
        twitter_result = write_twitter_post(
            content_plan=plan,
            telegram_text=editor_result["final_text"],
        )
        if twitter_result["success"]:
            log.success(f"Твит готов! ({twitter_result['tweet_length']} символов)")
            log.success(f"Формат: {twitter_result['twitter_format']}")
            log.success(
                f"CTA: {'Affiliate ✅' if twitter_result['using_affiliate_link'] else 'Telegram канал 📢'}"
            )
            if twitter_result.get("issues"):
                log.warning(f"Замечания: {twitter_result['issues']}")
        else:
            log.skip("Twitter Writer не сработал")
    except Exception as e:
        log.warning(f"Ошибка Twitter Writer (не критично): {e}")

    # ─── Шаг 7: Admin Notify ─────────────────────────────
    log.step(7, "ADMIN NOTIFY: отправляю уведомление")
    admin_result = {"success": False}
    try:
        from src.integrations.telegram_admin import send_admin_notification
        admin_result = send_admin_notification(
            telegram_text=text,
            tweet_result=twitter_result,
            publish_result=publish_result,
        )
        if admin_result["success"]:
            log.success("Уведомление отправлено администратору!")
        else:
            log.warning(f"Ошибка уведомления: {admin_result.get('error', '')}")
    except Exception as e:
        log.warning(f"Ошибка Admin Notify (не критично): {e}")

    # ─── Шаг 8: Analyst ──────────────────────────────────
    log.step(8, "ANALYST: записываю в лог")
    try:
        log_row = log_publication(publish_result)
        log.success(f"Лог сохранён: {log_row['date']} {log_row['time']}")
    except Exception as e:
        log.warning(f"Ошибка логирования (не критично): {e}")

    # ─── Итог ────────────────────────────────────────────
    log.summary({
        "Тема":      plan["topic"],
        "Продукт":   plan["product"]["name"],
        "Ссылка":    plan["product"]["affiliate_link"],
        "Telegram":  "✅ Опубликовано",
        "Twitter/X": "✅ Твит готов" if twitter_result.get("success") else "⚠️ Пропущено",
        "Admin":     "✅ Уведомлён" if admin_result.get("success") else "⚠️ Пропущено",
        "С фото":    "Да ✅" if image_path else "Нет ⚠️",
        "Время":     log.elapsed(),
    })

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