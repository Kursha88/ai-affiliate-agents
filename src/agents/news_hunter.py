"""
NewsHunter — агент для поиска свежих AI-новостей.

Источники (без API ключей, бесплатно):
- Hacker News Firebase API
- Reddit (публичный JSON API)

Возвращает топ-3 AI новости дня для использования в Copywriter.
"""

import re
import time
import random
import requests
from datetime import datetime, timezone
from typing import Optional


# ─── Ключевые слова для фильтрации AI-новостей ──────────────────────────────

AI_KEYWORDS = [
    # Модели и компании
    "openai", "chatgpt", "gpt-4", "gpt-5", "claude", "gemini", "llama",
    "mistral", "anthropic", "deepseek", "grok", "copilot", "midjourney",
    "stable diffusion", "dall-e", "sora", "runway", "perplexity",
    # Технологии
    "llm", "ai ", " ai", "artificial intelligence", "machine learning",
    "deep learning", "neural network", "transformer", "diffusion model",
    "rag", "fine-tuning", "embedding", "multimodal", "agent", "agentic",
    "generative ai", "gen ai", "foundation model", "language model",
    # Применения
    "ai tool", "ai assistant", "ai model", "ai system", "ai app",
    "text to image", "text to video", "voice ai", "image generation",
    # Русские ключевые слова (для HN иногда бывают)
    "нейросет", "искусственный интеллект", "ии ",
]

# Слова которые снижают релевантность
NOISE_KEYWORDS = [
    "hiring", "job", "salary", "resume", "lawsuit", "trial", "stock",
    "ipo", "acquisition", "merger", "layoffs", "funding round",
]


# ─── Hacker News ─────────────────────────────────────────────────────────────

HN_BASE = "https://hacker-news.firebaseio.com/v0"
HN_HEADERS = {"User-Agent": "AI-News-Bot/1.0"}


def _fetch_hn_top_stories(limit: int = 100) -> list:
    """Получает топ истории с Hacker News."""
    try:
        resp = requests.get(f"{HN_BASE}/topstories.json", headers=HN_HEADERS, timeout=10)
        resp.raise_for_status()
        ids = resp.json()[:limit]
        return ids
    except Exception as e:
        print(f"[NewsHunter] HN topstories ошибка: {e}")
        return []


def _fetch_hn_item(item_id: int) -> Optional[dict]:
    """Получает один элемент HN по ID."""
    try:
        resp = requests.get(f"{HN_BASE}/item/{item_id}.json", headers=HN_HEADERS, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _score_ai_relevance(title: str, url: str = "") -> float:
    """
    Оценивает релевантность заголовка к теме AI.
    Возвращает float от 0 (нерелевантно) до 10 (очень релевантно).
    """
    text = (title + " " + url).lower()
    score = 0.0

    for kw in AI_KEYWORDS:
        if kw in text:
            # Точное совпадение - больше очков
            score += 2.0 if f" {kw} " in f" {text} " else 1.0

    for kw in NOISE_KEYWORDS:
        if kw in text:
            score -= 1.5

    return max(score, 0.0)


def fetch_hn_ai_news(max_items: int = 50) -> list:
    """
    Получает топ AI-новости с Hacker News за сегодня.
    Возвращает список словарей: {title, url, score, source, summary, age_hours}
    """
    print("[NewsHunter] Загружаю новости с Hacker News...")
    story_ids = _fetch_hn_top_stories(max_items)

    if not story_ids:
        return []

    now_ts = datetime.now(timezone.utc).timestamp()
    results = []

    for story_id in story_ids[:max_items]:
        item = _fetch_hn_item(story_id)
        if not item:
            continue

        item_type = item.get("type", "")
        if item_type != "story":
            continue

        title = item.get("title", "")
        url = item.get("url", "")
        hn_score = item.get("score", 0)
        time_ts = item.get("time", 0)

        # Возраст в часах
        age_hours = (now_ts - time_ts) / 3600 if time_ts else 999

        # Только свежие (до 48 часов)
        if age_hours > 48:
            continue

        ai_score = _score_ai_relevance(title, url)
        if ai_score < 1.5:
            continue

        # Итоговая релевантность: AI-скор * log(HN_votes) / возраст
        import math
        final_score = ai_score * math.log(max(hn_score, 2)) / max(age_hours, 1)

        results.append({
            "title": title,
            "url": url,
            "hn_score": hn_score,
            "ai_score": ai_score,
            "final_score": final_score,
            "age_hours": round(age_hours, 1),
            "source": "Hacker News",
            "summary": "",
        })

        time.sleep(0.05)  # небольшая задержка чтобы не спамить API

    results.sort(key=lambda x: x["final_score"], reverse=True)
    print(f"[NewsHunter] HN: найдено {len(results)} AI-новостей")
    return results


# ─── Reddit ──────────────────────────────────────────────────────────────────

REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

REDDIT_SUBREDDITS = [
    "MachineLearning",
    "artificial",
    "singularity",
    "ChatGPT",
    "LocalLLaMA",
]


def fetch_reddit_ai_news(posts_per_sub: int = 10) -> list:
    """
    Получает топ AI-посты с Reddit без API ключей.
    Использует публичный JSON endpoint.
    """
    print("[NewsHunter] Загружаю новости с Reddit...")
    results = []
    now_ts = datetime.now(timezone.utc).timestamp()

    for subreddit in REDDIT_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={posts_per_sub}"
            resp = requests.get(url, headers=REDDIT_HEADERS, timeout=10)

            if resp.status_code == 429:
                print(f"[NewsHunter] Reddit r/{subreddit}: rate limit, пропускаю")
                time.sleep(2)
                continue

            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", {}).get("children", [])

            for post in posts:
                p = post.get("data", {})
                title = p.get("title", "")
                url_post = p.get("url", "")
                reddit_score = p.get("score", 0)
                time_ts = p.get("created_utc", 0)

                age_hours = (now_ts - time_ts) / 3600 if time_ts else 999
                if age_hours > 72:
                    continue

                # Для Reddit не фильтруем по AI-ключевым словам — суббреддиты и так тематические
                # Но проверяем что не шитпост
                if p.get("is_self") and not title:
                    continue

                results.append({
                    "title": title,
                    "url": url_post if not url_post.startswith("https://www.reddit.com") else f"https://reddit.com/r/{subreddit}",
                    "hn_score": reddit_score,
                    "ai_score": 5.0,  # Reddit AI-сабреддиты всегда релевантны
                    "final_score": reddit_score / max(age_hours, 1),
                    "age_hours": round(age_hours, 1),
                    "source": f"Reddit r/{subreddit}",
                    "summary": p.get("selftext", "")[:200] if p.get("selftext") else "",
                })

            time.sleep(1)  # обязательная задержка между запросами к Reddit

        except Exception as e:
            print(f"[NewsHunter] Reddit r/{subreddit} ошибка: {e}")
            continue

    results.sort(key=lambda x: x["final_score"], reverse=True)
    print(f"[NewsHunter] Reddit: найдено {len(results)} постов")
    return results


# ─── Основная функция ─────────────────────────────────────────────────────────

def get_top_ai_news(count: int = 3) -> list:
    """
    Главная функция NewsHunter.
    Возвращает топ-N AI-новостей из всех источников.

    Каждый элемент:
    {
        "title": str,       — заголовок новости
        "url": str,         — ссылка на источник
        "source": str,      — "Hacker News" / "Reddit r/..."
        "age_hours": float, — возраст в часах
        "summary": str,     — краткое описание (если есть)
    }
    """
    all_news = []

    # Hacker News
    hn_news = fetch_hn_ai_news(max_items=50)
    all_news.extend(hn_news)

    # Reddit
    reddit_news = fetch_reddit_ai_news(posts_per_sub=10)
    all_news.extend(reddit_news)

    # Сортируем по итоговому скору
    all_news.sort(key=lambda x: x["final_score"], reverse=True)

    # Убираем дубли по схожим заголовкам
    seen_titles = set()
    unique_news = []
    for item in all_news:
        # Берём первые 5 слов как ключ (убирает дубли с HN и Reddit)
        key = " ".join(item["title"].lower().split()[:5])
        if key not in seen_titles:
            seen_titles.add(key)
            unique_news.append(item)

    top = unique_news[:count]

    if top:
        print(f"\n[NewsHunter] 🔥 Топ-{len(top)} AI-новостей:")
        for i, n in enumerate(top, 1):
            print(f"   {i}. [{n['source']}] {n['title'][:70]}...")
            print(f"      Возраст: {n['age_hours']}ч | Score: {n['final_score']:.1f}")

    return top


def get_fallback_topic() -> dict:
    """
    Fallback если новости не удалось загрузить.
    Возвращает актуальную тему из статичного списка.
    """
    fallback_topics = [
        {
            "title": "Как нейросети меняют способ работы с информацией в 2026 году",
            "url": "",
            "source": "editorial",
            "age_hours": 0,
            "summary": "Обзор актуальных AI-трендов",
        },
        {
            "title": "Топ-5 AI-инструментов которые экономят время прямо сейчас",
            "url": "",
            "source": "editorial",
            "age_hours": 0,
            "summary": "Подборка полезных нейросетей",
        },
        {
            "title": "Что умеет современный AI и как им пользоваться бесплатно",
            "url": "",
            "source": "editorial",
            "age_hours": 0,
            "summary": "Гид по возможностям ИИ",
        },
        {
            "title": "AI против человека: где нейросети уже лучше нас",
            "url": "",
            "source": "editorial",
            "age_hours": 0,
            "summary": "Анализ возможностей современного ИИ",
        },
    ]
    return random.choice(fallback_topics)


# ─── Тест ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("NEWS HUNTER TEST")
    print("=" * 55)

    news = get_top_ai_news(count=5)

    if news:
        print(f"\n✅ Найдено {len(news)} новостей\n")
        for i, n in enumerate(news, 1):
            print(f"{'='*50}")
            print(f"#{i} {n['title']}")
            print(f"Источник: {n['source']}")
            print(f"Ссылка:   {n['url']}")
            print(f"Возраст:  {n['age_hours']} часов")
    else:
        print("\n⚠️  Новости не найдены — fallback:")
        fallback = get_fallback_topic()
        print(f"   {fallback['title']}")
