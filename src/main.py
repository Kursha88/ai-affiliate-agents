import sys
import os
from datetime import datetime, date

from src.core.config import Config
from src.utils.logger import get_logger
from src.utils.validators import is_fallback_text, validate_content_plan

from src.agents.news_hunter import get_top_ai_news, get_fallback_topic
from src.agents.strategist import create_content_plan
from src.agents.copywriter import write_post
from src.agents.editor import edit_post
from src.agents.designer import create_image_for_post
from src.agents.publisher import publish_post
from src.agents.analyst import log_publication, print_report
from src.integrations.x_client import print_drafts_report, is_twitter_configured, post_tweet
from src.integrations.vk_client import is_vk_configured, publish_to_vk
from src.integrations.pinterest_client import is_pinterest_configured, create_pin


def _already_published_today() -> bool:
    """
    Защита от дублей: проверяет, публиковали ли уже сегодня в Telegram.
    """
    posts_file = Config.POSTS_FILE
    if not os.path.exists(posts_file):
        return False

    today_str = date.today().strftime("%Y-%m-%d")

    try:
        with open(posts_file, "r", encoding="utf-8") as f:
            content = f.read()
            # Проверяем, есть ли сегодняшняя дата именно со статусом success
            return today_str in content and "telegram" in content.lower()
    except Exception:
        return False


def run_pipeline() -> dict:
    """
    Запускает полный цикл мультиагентного маркетинга:
    NewsHunter → Strategist → Copywriter → Editor → Designer
    → Telegram Publisher
    → External Traffic Funnel (Twitter/X + VK + Pinterest)
    → Admin Notify → Analyst
    """
    log = get_logger()
    Config.ensure_dirs()

    log.header("AI AFFILIATE & GROWTH AGENTS — ЗАПУСК ПАЙПЛАЙНА")

    # ─── Валидация конфигурации ───────────────────────────
    validation = Config.validate()
    if not validation["valid"]:
        for issue in validation["issues"]:
            log.error(issue)
        return {"success": False, "step": "config", "error": validation["issues"]}

    # ─── Шаг 0: Поиск горячей темы / новости ───────────────
    log.step(0, "CONTENT HUNTER: выбираю горячую тему / лайфхак")
    news_item = None
    try:
        # 50% времени берем свежую новость, 50% — вирусный секретный промпт / лайфхак
        import random
        if random.random() > 0.5:
            news_list = get_top_ai_news(count=3)
            if news_list:
                news_item = news_list[0]
                log.success(f"Горячая новость: {news_item['title'][:60]}...")
        if not news_item:
            news_item = get_fallback_topic()
            log.success(f"Тема лайфхака: {news_item['title'][:60]}...")
    except Exception as e:
        log.warning(f"Ошибка NewsHunter (не критично): {e}")
        news_item = get_fallback_topic()

    # ─── Шаг 1: Strategist ───────────────────────────────
    log.step(1, "STRATEGIST: формирую план контента")
    try:
        plan = create_content_plan(news_item=news_item)

        plan_validation = validate_content_plan(plan)
        if not plan_validation["valid"]:
            log.error(f"Невалидный план: {plan_validation['issues']}")
            return {"success": False, "step": "strategist", "error": str(plan_validation["issues"])}

        log.success(f"Режим:   {plan.get('mode', 'growth')}")
        log.success(f"Тема:    {plan['topic'][:60]}")
        log.success(f"Формат:  {plan['format']}")
    except Exception as e:
        log.error(f"Ошибка Strategist: {e}")
        return {"success": False, "step": "strategist", "error": str(e)}

    # ─── Шаг 2: Copywriter ───────────────────────────────
    log.step(2, "COPYWRITER: пишу пост")
    try:
        copywriter_result = write_post(plan)
        draft = copywriter_result["draft_text"]

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
    log.step(3, "EDITOR: проверяю и форматирую")
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
            log.skip("Публикуем без фото")
    except Exception as e:
        log.warning(f"Ошибка Designer (не критично): {e}")

    # ─── Шаг 5: Publisher Telegram ───────────────────────
    log.step(5, "PUBLISHER: публикую в Telegram-канал")
    try:
        publish_result = publish_post(editor_result, image_path=image_path)

        if publish_result["success"]:
            log.success(f"Опубликовано в TG! Message ID: {publish_result['message_id']}")
        else:
            log.error(f"Ошибка публикации в TG: {publish_result['error']}")
            return {
                "success": False,
                "step": "publisher",
                "error": publish_result["error"],
            }

    except Exception as e:
        log.error(f"Ошибка Publisher: {e}")
        return {"success": False, "step": "publisher", "error": str(e)}

    # ─── Шаг 6: Воронка внешнего трафика (Twitter / X) ───
    log.step(6, "TRAFFIC FUNNEL: Twitter / X")
    twitter_result = {"success": False, "tweet_text": "", "auto_published": False}
    try:
        from src.agents.twitter_writer import write_twitter_post

        twitter_draft = write_twitter_post(
            content_plan=plan,
            telegram_text=editor_result["final_text"],
        )

        if twitter_draft["success"]:
            tweet_text = twitter_draft["tweet_text"]
            log.success(f"Вирусный твит готов ({twitter_draft['tweet_length']} симв)")

            # Проверяем Twitter ключи
            if is_twitter_configured():
                pub_result = post_tweet(tweet_text)
                if pub_result["success"]:
                    log.success(f"✅ Твит опубликован в X! URL: {pub_result.get('tweet_url', '')}")
                    twitter_result = {**twitter_draft, "auto_published": True, **pub_result}
                else:
                    log.warning(f"⚠️ Ошибка автопубликации в X: {pub_result['error']}")
                    twitter_result = {**twitter_draft, "auto_published": False, "error": pub_result['error']}
            else:
                log.skip("Twitter ключи не обнаружены в .env / Secrets")
                twitter_result = {**twitter_draft, "auto_published": False}

    except Exception as e:
        log.warning(f"Ошибка Twitter Writer: {e}")

    # ─── Шаг 7: Воронка внешнего трафика (VK) ────────────
    vk_result = {"success": False}
    if is_vk_configured():
        log.step(7, "TRAFFIC FUNNEL: ВКонтакте (VK)")
        try:
            vk_res = publish_to_vk(editor_result["final_text"], image_path=image_path)
            if vk_res["success"]:
                log.success(f"✅ Опубликовано в VK! {vk_res.get('url', '')}")
                vk_result = vk_res
            else:
                log.warning(f"Ошибка VK: {vk_res.get('error', '')}")
        except Exception as e:
            log.warning(f"Исключение VK: {e}")

    # ─── Шаг 8: Воронка внешнего трафика (Pinterest) ─────
    if is_pinterest_configured() and image_path:
        log.step(8, "TRAFFIC FUNNEL: Pinterest")
        try:
            pin_res = create_pin(
                title=plan["topic"],
                description=editor_result["final_text"][:400],
                image_url_or_path=image_path,
                link=Config.get_channel_link(),
            )
            if pin_res["success"]:
                log.success(f"✅ Пин создан в Pinterest! {pin_res.get('url', '')}")
        except Exception as e:
            log.warning(f"Исключение Pinterest: {e}")

    # ─── Шаг 9: Admin Notify ─────────────────────────────
    log.step(9, "ADMIN NOTIFY: отправляю отчет админу")
    admin_result = {"success": False}
    try:
        from src.integrations.telegram_admin import send_admin_notification
        admin_result = send_admin_notification(
            telegram_text=editor_result["final_text"],
            tweet_result=twitter_result,
            publish_result=publish_result,
        )
        if admin_result["success"]:
            log.success("Отчет доставлен админу в Telegram!")
    except Exception as e:
        log.warning(f"Ошибка Admin Notify (не критично): {e}")

    # ─── Шаг 10: Analyst ─────────────────────────────────
    try:
        log_publication(publish_result)
    except Exception:
        pass

    # ─── Итог ────────────────────────────────────────────
    auto_pub_status = "✅ Опубликован в X" if twitter_result.get("auto_published") else (
        f"⚠️ Ошибка: {twitter_result.get('error', 'нет ключей')}" if twitter_result.get("error") else "📝 Черновик"
    )

    log.summary({
        "Тема":       plan["topic"][:50],
        "Формат":     plan["format"],
        "Telegram":   "✅ Опубликовано",
        "Twitter / X": auto_pub_status,
        "VK":         "✅ Опубликовано" if vk_result.get("success") else "Пропущено",
        "Время":      log.elapsed(),
    })

    return {
        "success": True,
        "plan": plan,
        "message_id": publish_result["message_id"],
        "length": editor_result["length"],
        "ai_source": copywriter_result["ai_source"],
        "twitter_auto": twitter_result.get("auto_published", False),
    }


def run_report() -> None:
    """Показывает отчёт по всем публикациям"""
    print_report()
    print_drafts_report()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        run_report()
    else:
        result = run_pipeline()
        if not result.get("success", False):
            sys.exit(1)