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

from src.factory.state_service import StateService
from src.domain.models import RunStatus


def _get_trigger_info() -> tuple[str, str | None]:
    """
    Возвращает trigger и внешний ID запуска.

    Для GitHub Actions используем GITHUB_RUN_ID + GITHUB_RUN_ATTEMPT,
    чтобы защитить от повторного выполнения того же самого внешнего запуска.
    """
    if os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true":
        run_id = os.getenv("GITHUB_RUN_ID", "").strip()
        attempt = os.getenv("GITHUB_RUN_ATTEMPT", "").strip()
        external_id = f"{run_id}:{attempt}" if run_id else None
        return "github_actions", external_id

    return "manual", None


def run_pipeline() -> dict:
    """
    Запускает полный цикл пайплайна с минимальным state layer:

    PipelineRun
    → ContentItem
    → Telegram Publication idempotency
    → existing content generation/publication logic
    """
    log = get_logger()
    Config.ensure_dirs()
    log.header("AI AFFILIATE & GROWTH AGENTS — ЗАПУСК ПАЙПЛАЙНА")

    try:
        state = StateService()
    except Exception as e:
        log.error(f"Не удалось инициализировать state layer: {e}")
        return {
            "success": False,
            "step": "state",
            "error": str(e),
        }

    trigger, trigger_external_id = _get_trigger_info()

    try:
        run, created = state.start_pipeline_run(
            mode=Config.PIPELINE_MODE,
            trigger=trigger,
            trigger_external_id=trigger_external_id,
        )
    except Exception as e:
        log.error(f"Не удалось создать PipelineRun: {e}")
        return {
            "success": False,
            "step": "pipeline_run",
            "error": str(e),
        }

    if not created:
        if run.status == RunStatus.COMPLETED:
            log.skip("Pipeline run уже завершён ранее. Повторный запуск пропущен.")
            return {
                "success": True,
                "duplicate_run": True,
                "run_id": run.run_id,
            }

        if run.status == RunStatus.RUNNING:
            state.fail_run(
                run_id=run.run_id,
                error_code="RUNNING_CONFLICT",
                error_message="Previous pipeline run is still marked as RUNNING",
            )
            log.error("Обнаружен конфликт: предыдущий запуск всё ещё в состоянии RUNNING.")
            return {
                "success": False,
                "step": "pipeline_run",
                "error": "running_conflict",
            }

        if run.status == RunStatus.FAILED:
            log.info("Возобновляем ранее упавший запуск пайплайна.")
            state.resume_run(run.run_id)

    try:
        validation = Config.validate()
        if not validation["valid"]:
            for issue in validation["issues"]:
                log.error(issue)

            state.fail_run(
                run_id=run.run_id,
                error_code="CONFIG_VALIDATION",
                error_message="; ".join(validation["issues"]),
            )

            return {
                "success": False,
                "step": "config",
                "error": validation["issues"],
            }

        result = _run_pipeline_inner(state, run.run_id, log)

        if result.get("success"):
            state.complete_run(run.run_id)
        else:
            state.fail_run(
                run_id=run.run_id,
                error_code=str(result.get("step", "pipeline")),
                error_message=str(result.get("error", "unknown_error")),
            )

        return result

    except Exception as e:
        state.fail_run(
            run_id=run.run_id,
            error_code="UNEXPECTED",
            error_message=str(e),
        )
        log.error(f"Неожиданная ошибка пайплайна: {e}")
        return {
            "success": False,
            "step": "pipeline",
            "error": str(e),
        }


def _run_pipeline_inner(state: StateService, run_id: str, log) -> dict:
    """
    Внутренний pipeline с сохранением существующей бизнес-логики.

    Добавлены только:
    - ContentItem;
    - Publication;
    - idempotency guard для Telegram.
    """
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
            return {
                "success": False,
                "step": "strategist",
                "error": str(plan_validation["issues"]),
            }

        content_item, content_created = state.get_or_create_content_from_plan(plan)

        log.success(f"Режим:   {plan.get('mode', 'growth')}")
        log.success(f"Тема:    {plan['topic'][:60]}")
        log.success(f"Формат:  {plan['format']}")
        log.success(f"Content ID: {content_item.content_id}")
        log.success(f"Content создан: {content_created}")

        # Ранняя защита от повторной Telegram-публикации.
        # Если для этого ContentItem уже есть успешная публикация —
        # не генерируем контент повторно и не публикуем повторно.
        publication, _ = state.get_or_create_publication(
            content_id=content_item.content_id,
            platform="telegram",
            business_date=content_item.business_date,
        )

        allowed, reason = state.guard_publication(publication)

        if not allowed:
            if reason == "already_published":
                log.skip("Telegram уже опубликован для этого ContentItem. Повторная публикация пропущена.")
                return {
                    "success": True,
                    "already_published": True,
                    "run_id": run_id,
                    "content_id": content_item.content_id,
                    "plan": plan,
                    "message_id": publication.external_post_id,
                }

            log.error(f"Telegram публикация заблокирована: {reason}")
            return {
                "success": False,
                "step": "publisher",
                "error": reason,
            }

    except Exception as e:
        log.error(f"Ошибка Strategist: {e}")
        return {
            "success": False,
            "step": "strategist",
            "error": str(e),
        }

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
        return {
            "success": False,
            "step": "copywriter",
            "error": str(e),
        }

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
        return {
            "success": False,
            "step": "editor",
            "error": str(e),
        }

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
        state.begin_publication(publication.publication_id)

        publish_result = publish_post(editor_result, image_path=image_path)

        if publish_result["success"]:
            external_post_id = str(publish_result.get("message_id", "")) or None
            post_url = state.build_telegram_post_url(external_post_id)

            state.mark_publication_published(
                publication_id=publication.publication_id,
                external_post_id=external_post_id,
                post_url=post_url,
            )

            state.mark_content_published(content_item.content_id)

            log.success(f"Опубликовано в TG! Message ID: {publish_result['message_id']}")
        else:
            error_text = str(publish_result.get("error", "unknown"))

            state.handle_publication_error(
                publication_id=publication.publication_id,
                error_message=error_text,
            )

            log.error(f"Ошибка публикации в TG: {error_text}")

            return {
                "success": False,
                "step": "publisher",
                "error": error_text,
            }
    except Exception as e:
        # Если исключение произошло во время внешней отправки,
        # мы не можем быть уверены, был ли пост реально опубликован.
        state.mark_publication_manual_review(
            publication_id=publication.publication_id,
            error_code="UNKNOWN_EXTERNAL_RESULT",
            error_message=str(e),
        )

        log.error(f"Ошибка Publisher: {e}")

        return {
            "success": False,
            "step": "publisher",
            "error": str(e),
        }

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
                    twitter_result = {
                        **twitter_draft,
                        "auto_published": False,
                        "error": pub_result["error"],
                    }
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
    pin_result = {"success": False}

    if is_pinterest_configured() and image_path:
        log.step(8, "TRAFFIC FUNNEL: Pinterest")

        try:
            pin_result = create_pin(
                title=plan["topic"],
                description=editor_result["final_text"][:400],
                image_url_or_path=image_path,
                link=Config.get_channel_link(),
            )

            if pin_result["success"]:
                log.success(f"✅ Пин создан в Pinterest! {pin_result.get('url', '')}")
            else:
                log.warning(f"Pinterest: {pin_result.get('error', '')}")
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
            pin_result=pin_result,
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
        f"⚠️ Ошибка: {twitter_result.get('error', 'нет ключей')}"
        if twitter_result.get("error")
        else "📝 Черновик"
    )

    log.summary({
        "Тема":       plan["topic"][:50],
        "Формат":     plan["format"],
        "Content ID": content_item.content_id,
        "Telegram":   "✅ Опубликовано",
        "Twitter / X": auto_pub_status,
        "VK":         "✅ Опубликовано" if vk_result.get("success") else "Пропущено",
        "Время":      log.elapsed(),
    })

    return {
        "success": True,
        "run_id": run_id,
        "content_id": content_item.content_id,
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