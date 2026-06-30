import os
import yaml
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    Единая конфигурация проекта.
    Читает из .env и config/settings.yaml
    Используется всеми агентами и интеграциями.
    """

    # ─── Telegram ─────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHANNEL_ID: str = os.getenv("TELEGRAM_CHANNEL_ID", "")
    TELEGRAM_CHANNEL_USERNAME: str = os.getenv(
        "TELEGRAM_CHANNEL_USERNAME", "@nejroavtomatizacia"
    )
    TELEGRAM_ADMIN_CHAT_ID: str = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")
    TELEGRAM_OWNER_ID: str = os.getenv("TELEGRAM_OWNER_ID", "")

    # ─── AI провайдеры ────────────────────────────────────
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # ─── Пути к файлам ────────────────────────────────────
    DATA_DIR: str = "data"
    ASSETS_DIR: str = "assets/output"
    CONFIG_DIR: str = "config"
    LOGS_DIR: str = "data/logs"

    POSTS_FILE: str = "data/published_posts.csv"
    HISTORY_FILE: str = "data/topic_history.json"
    ANALYTICS_FILE: str = "data/analytics.csv"
    LOG_FILE: str = "data/logs/pipeline.log"

    SETTINGS_FILE: str = "config/settings.yaml"
    PARTNERS_FILE: str = "config/partners.yaml"

    # ─── Telegram канал ───────────────────────────────────
    TELEGRAM_CHANNEL_LINK: str = "https://t.me/nejroavtomatizacia"

    # ─── Лимиты ───────────────────────────────────────────
    MAX_POST_LENGTH: int = 4096
    MAX_CAPTION_LENGTH: int = 1024
    MAX_TWEET_LENGTH: int = 280
    MIN_POST_LENGTH: int = 100
    MAX_TOPIC_HISTORY: int = 30

    # ─── AI настройки ─────────────────────────────────────
    AI_TEMPERATURE: float = 0.7
    AI_MAX_TOKENS: int = 1000

    _settings_cache: Optional[dict] = None
    _partners_cache: Optional[dict] = None

    @classmethod
    def get_settings(cls) -> dict:
        """Возвращает настройки из settings.yaml"""
        if cls._settings_cache is None:
            try:
                with open(cls.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    cls._settings_cache = yaml.safe_load(f)
            except Exception as e:
                print(f"[Config] Ошибка загрузки settings.yaml: {e}")
                cls._settings_cache = {}
        return cls._settings_cache

    @classmethod
    def get_partners(cls) -> dict:
        """Возвращает партнёрскую конфигурацию"""
        if cls._partners_cache is None:
            try:
                with open(cls.PARTNERS_FILE, "r", encoding="utf-8") as f:
                    cls._partners_cache = yaml.safe_load(f)
            except Exception as e:
                print(f"[Config] Ошибка загрузки partners.yaml: {e}")
                cls._partners_cache = {}
        return cls._partners_cache

    @classmethod
    def get_topics(cls) -> list:
        """Возвращает список тем контента"""
        settings = cls.get_settings()
        return settings.get("content", {}).get("topics", [])

    @classmethod
    def get_formats(cls) -> list:
        """Возвращает список форматов постов"""
        settings = cls.get_settings()
        return settings.get("content", {}).get("formats", [])

    @classmethod
    def get_active_partners(cls) -> list:
        """Возвращает только активных партнёров"""
        partners = cls.get_partners()
        return [
            p for p in partners.get("partners", [])
            if p.get("active", False)
        ]

    @classmethod
    def get_channel_link(cls) -> str:
        """Возвращает ссылку на Telegram канал"""
        username = cls.TELEGRAM_CHANNEL_USERNAME.replace("@", "").strip()
        return f"https://t.me/{username}"

    @classmethod
    def validate(cls) -> dict:
        """
        Проверяет наличие всех обязательных переменных.
        Вызывается при старте пайплайна.
        """
        required = {
            "TELEGRAM_BOT_TOKEN": cls.TELEGRAM_BOT_TOKEN,
            "TELEGRAM_CHANNEL_ID": cls.TELEGRAM_CHANNEL_ID,
            "TELEGRAM_ADMIN_CHAT_ID": cls.TELEGRAM_ADMIN_CHAT_ID,
        }

        ai_keys = {
            "GEMINI_API_KEY": cls.GEMINI_API_KEY,
            "GROQ_API_KEY": cls.GROQ_API_KEY,
        }

        missing = [k for k, v in required.items() if not v]
        ai_available = any(v for v in ai_keys.values())

        issues = []
        if missing:
            issues.append(f"Отсутствуют переменные: {', '.join(missing)}")
        if not ai_available:
            issues.append("Нет доступных AI провайдеров (GEMINI или GROQ)")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "ai_available": ai_available,
            "missing": missing,
        }

    @classmethod
    def ensure_dirs(cls) -> None:
        """Создаёт необходимые папки если не существуют"""
        dirs = [
            cls.DATA_DIR,
            cls.ASSETS_DIR,
            cls.LOGS_DIR,
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

    @classmethod
    def print_status(cls) -> None:
        """Выводит статус конфигурации"""
        print("\n=== CONFIG STATUS ===")
        print(f"📱 Telegram Bot:     {'✅' if cls.TELEGRAM_BOT_TOKEN else '❌'}")
        print(f"📢 Channel ID:       {'✅' if cls.TELEGRAM_CHANNEL_ID else '❌'}")
        print(f"👤 Admin Chat ID:    {'✅' if cls.TELEGRAM_ADMIN_CHAT_ID else '❌'}")
        print(f"🤖 Gemini API:       {'✅' if cls.GEMINI_API_KEY else '❌'}")
        print(f"🤖 Groq API:         {'✅' if cls.GROQ_API_KEY else '❌'}")
        print(f"📁 Data dir:         {cls.DATA_DIR}")
        print(f"🖼  Assets dir:       {cls.ASSETS_DIR}")

        partners = cls.get_active_partners()
        print(f"🤝 Active partners:  {len(partners)}")

        validation = cls.validate()
        print(f"\n{'✅ Конфигурация OK' if validation['valid'] else '❌ Есть проблемы'}")
        if validation["issues"]:
            for issue in validation["issues"]:
                print(f"   ⚠️  {issue}")
        print("=" * 20)


if __name__ == "__main__":
    Config.print_status()