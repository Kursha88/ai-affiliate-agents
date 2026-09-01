"""
Twitter/X клиент — автоматическая публикация твитов через Tweepy v4.
Использует OAuth 1.0a (API Key + Access Token).
"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def _get_twitter_client():
    """
    Создаёт Tweepy Client с OAuth 1.0a credentials.
    Требует переменные:
      TWITTER_API_KEY
      TWITTER_API_SECRET
      TWITTER_ACCESS_TOKEN
      TWITTER_ACCESS_SECRET
    """
    try:
        import tweepy

        api_key = os.getenv("TWITTER_API_KEY", "").strip()
        api_secret = os.getenv("TWITTER_API_SECRET", "").strip()
        access_token = os.getenv("TWITTER_ACCESS_TOKEN", "").strip()
        access_secret = os.getenv("TWITTER_ACCESS_SECRET", "").strip()

        if not all([api_key, api_secret, access_token, access_secret]):
            missing = []
            if not api_key:
                missing.append("TWITTER_API_KEY")
            if not api_secret:
                missing.append("TWITTER_API_SECRET")
            if not access_token:
                missing.append("TWITTER_ACCESS_TOKEN")
            if not access_secret:
                missing.append("TWITTER_ACCESS_SECRET")
            print(f"[Twitter] Отсутствуют переменные: {', '.join(missing)}")
            return None

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        return client

    except ImportError:
        print("[Twitter] tweepy не установлен. Запусти: pip install tweepy")
        return None
    except Exception as e:
        print(f"[Twitter] Ошибка инициализации клиента: {e}")
        return None


def post_tweet(tweet_text: str) -> dict:
    """
    Публикует твит в Twitter/X.

    Args:
        tweet_text: Текст твита (максимум 280 символов)

    Returns:
        dict с ключами: success, tweet_id, error
    """
    if not tweet_text or not tweet_text.strip():
        return {"success": False, "error": "Пустой текст твита"}

    # Обрезаем до 280 символов если нужно
    if len(tweet_text) > 280:
        tweet_text = tweet_text[:277] + "..."
        print(f"[Twitter] Твит обрезан до 280 символов")

    client = _get_twitter_client()
    if not client:
        return {"success": False, "error": "Twitter клиент не инициализирован"}

    try:
        response = client.create_tweet(text=tweet_text)

        if response.data:
            tweet_id = response.data.get("id", "")
            print(f"[Twitter] ✅ Твит опубликован! ID: {tweet_id}")
            return {
                "success": True,
                "tweet_id": tweet_id,
                "tweet_url": f"https://twitter.com/i/web/status/{tweet_id}",
                "tweet_length": len(tweet_text),
            }
        else:
            return {"success": False, "error": "Пустой ответ от Twitter API"}

    except Exception as e:
        error_msg = str(e)
        print(f"[Twitter] ❌ Ошибка публикации: {error_msg}")

        # Распознаём типичные ошибки
        if "403" in error_msg:
            return {
                "success": False,
                "error": "403 Forbidden — проверь права приложения (нужен Read and Write)",
            }
        elif "429" in error_msg:
            return {
                "success": False,
                "error": "429 Rate Limit — превышен лимит запросов. Попробуй позже.",
            }
        elif "duplicate" in error_msg.lower():
            return {
                "success": False,
                "error": "Дублированный твит — такой текст уже публиковался",
            }
        else:
            return {"success": False, "error": error_msg}


def is_twitter_configured() -> bool:
    """Проверяет наличие всех Twitter ключей."""
    return all([
        os.getenv("TWITTER_API_KEY"),
        os.getenv("TWITTER_API_SECRET"),
        os.getenv("TWITTER_ACCESS_TOKEN"),
        os.getenv("TWITTER_ACCESS_SECRET"),
    ])


def print_drafts_report() -> None:
    """
    Показывает статус Twitter интеграции.
    Совместимость с исходным main.py.
    """
    if is_twitter_configured():
        print("[Twitter] ✅ Ключи настроены — автопубликация активна")
    else:
        print("[Twitter] ⚠️ Ключи не настроены — твиты не публикуются")


# ─── Тест ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== TWITTER CLIENT TEST ===")

    if not is_twitter_configured():
        print("❌ Twitter ключи не найдены в .env")
        print("Добавь в .env файл:")
        print("  TWITTER_API_KEY=...")
        print("  TWITTER_API_SECRET=...")
        print("  TWITTER_ACCESS_TOKEN=...")
        print("  TWITTER_ACCESS_SECRET=...")
    else:
        print("✅ Ключи найдены")

        test_text = (
            "🧪 Тест автопостинга AI-канала\n\n"
            "Если видишь этот твит — интеграция работает ✅\n\n"
            "Подписывайся на AI-новости → https://t.me/nejroavtomatizacia"
        )

        print(f"\nТекст ({len(test_text)} символов):")
        print(test_text)
        print("\nОтправляю...")

        result = post_tweet(test_text)

        if result["success"]:
            print(f"\n✅ Успешно! Tweet ID: {result['tweet_id']}")
            print(f"🔗 {result.get('tweet_url', '')}")
        else:
            print(f"\n❌ Ошибка: {result['error']}")