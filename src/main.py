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
from src.integrations.x_client import print_drafts_report, is_twitter_configured


def _already_published_today() -> bool:
    """
    Защита от дублей: проверяет публиковали ли уже сегодня.
    Читает data/published_posts.csv.
    """
    posts_file = Config.POSTS_FILE
    if not os.path.exists(posts_file):
        return False

    today_str = date.today().strftime("%Y-%m-%d")

    try:
        with open(posts_file, "r", encoding="utf-8") as f:
            content = f.read()
            # Проверяем есть ли сегодняшняя дата в файле
            return today_str in content
    except Exception:
        return False


def run_pipeline() -> dict:
    """
    Запускает полный цикл:
    NewsHunter → Strategist → Copywriter → Editor → Designer
    → Publisher → Twitter Writer → Admin Notify → Analyst
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

    # ─── Защита от дублей ─────────────────────────────────
    if _already_published_today():
        log.warning("Сегодня уже была публикация — пропускаю (защита от дублей)")
        log.warning("Чтобы принудительно запустить — удали сегодняшнюю строку из data/published_posts.csv")
        return {"success": False, "step": "dedup", "error": "Already published today"}

    # ─── Шаг 0: NewsHunter ───────────────────────────────
    log.step(0, "NEWS HUNTER: ищу свежие AI-новости")
    news_item = None
    try:
        news_list = get_top_ai_news(count=3)
        if news_list:
            news_item = news_list[0]  # Берём самую горячую новость
            log.success(f"Новость: {news_item['title'][:60]}...")
            log.success(f"Источник: {news_item['source']} | Возраст: {news_item['age_hours']}ч")
        else:
            log.warning("Новости не найдены — используем fallback тему")
            news_item = get_fallback_topic()
    except Exception as e:
        log.warning(f"Ошибка NewsHunter (не критично): {e}")
        news_item = get_fallback_topic()

    # ─── Шаг 1: Strategist ───────────────────────────────
    log.step(1, "STRATEGIST: формирую план")
    try:
        plan = create_content_plan(news_item=news_item)

        plan_validation = validate_content_plan(plan)
        if not plan_validation["valid"]:
            log.error(f"Невалидный план: {plan_validation['issues']}")
            return {"success": False, "step": "strategist", "error": str(plan_validation["issues"])}

        log.success(f"Режим:   {plan.get('mode', 'growth')}")
        log.success(f"Тема:    {plan['topic'][:60]}")
        log.success(f"Формат:  {plan['format']}")
        log.success(f"CTA:     {plan['cta_link']}")
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
        # 30% постов публикуем без картинки — выглядит человечнее
        import random
        if random.random() > 0.3:
            image_path = create_image_for_post(plan)
            if image_path:
                log.success(f"Картинка создана: {image_path}")
            else:
                log.skip("Картинка не создана — публикуем без фото")
        else:
            log.skip("Публикуем без фото (нативный вид)")
    except Exception as e:
        log.warning(f"Ошибка Designer (не критично): {e}")

    # ─── Шаг 5: Publisher Telegram ───────────────────────
    log.step(5, "PUBLISHER: публикую в Telegram")
    try:
        publish_result = publish_post(editor_result, image_path=image_path)

        if publish_result["success"]:
            log.success(f"Опубликовано! Message ID: {publish_result['message_id']}")
            log.success(f"Канал: {publish_result['channel']}")
        else:
            log.error(f"Ошибка публикации: {publish_result['error']}")
            return {
                "success": False,
                "step": "publisher",
                "error": publish_result["error"],
            }

    except Exception as e:
        log.error(f"Ошибка Publisher: {e}")
        return {"success": False, "step": "publisher", "error": str(e)}

    # ─── Шаг 6: Twitter Writer + Автопубликация ───────────
    log.step(6, "TWITTER: создаю и публикую твит")
    twitter_result = {"success": False, "tweet_text": "", "auto_published": False}
    try:
        from src.agents.twitter_writer import write_twitter_post
        from src.integrations.x_client import post_tweet

        twitter_draft = write_twitter_post(
            content_plan=plan,
            telegram_text=editor_result["final_text"],
        )

        if twitter_draft["success"]:
            tweet_text = twitter_draft["tweet_text"]
            log.success(f"Твит готов ({twitter_draft['tweet_length']} символов)")

            # Автопубликация если ключи настроены
            if is_twitter_configured():
                log.step(6, "TWITTER: автопубликация...")
                pub_result = post_tweet(tweet_text)
                if pub_result["success"]:
                    log.success(f"Твит опубликован! ID: {pub_result.get('tweet_id', '')}")
                    twitter_result = {**twitter_draft, "auto_published": True, **pub_result}
                else:
                    log.warning(f"Ошибка автопубликации: {pub_result['error']}")
                    twitter_result = {**twitter_draft, "auto_published": False}
            else:
                log.skip("Twitter ключи не настроены — твит только в черновике")
                twitter_result = {**twitter_draft, "auto_published": False}
        else:
            log.skip("Twitter Writer не сработал")

    except Exception as e:
        log.warning(f"Ошибка Twitter (не критично): {e}")

    # ─── Шаг 7: Admin Notify ─────────────────────────────
    log.step(7, "ADMIN NOTIFY: отправляю уведомление")
    admin_result = {"success": False}
    try:
        from src.integrations.telegram_admin import send_admin_notification
        admin_result = send_admin_notification(
            telegram_text=editor_result["final_text"],
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
    auto_pub_status = "✅ Авто-опубликован" if twitter_result.get("auto_published") else (
        "📝 Черновик готов" if twitter_result.get("success") else "⚠️ Пропущено"
    )

    log.summary({
        "Режим":     plan.get("mode", "growth"),
        "Тема":      plan["topic"][:50],
        "Источник":  plan.get("news", {}).get("source", "editorial"),
        "CTA":       plan.get("cta_link", ""),
        "Telegram":  "✅ Опубликовано",
        "Twitter/X": auto_pub_status,
        "Admin":     "✅ Уведомлён" if admin_result.get("success") else "⚠️ Пропущено",
        "С фото":    "Да ✅" if image_path else "Нет (нативный вид)",
        "Время":     log.elapsed(),
    })

    return {
        "success": True,
        "plan": plan,
        "message_id": publish_result["message_id"],
        "length": editor_result["length"],
        "ai_source": copywriter_result["ai_source"],
        "has_image": image_path is not None,
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
        run_pipeline()