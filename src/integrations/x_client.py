import os
from typing import Dict

from dotenv import load_dotenv

load_dotenv()


def _get_channel_link() -> str:
    username = os.getenv("TELEGRAM_CHANNEL_USERNAME", "@nejroavtomatizacia")
    username = username.replace("@", "").strip()
    return f"https://t.me/{username}"


def print_drafts_report() -> None:
    """
    Заглушка для совместимости.
    Twitter-драфты теперь отправляются в Telegram Admin.
    """
    print("\n" + "=" * 50)
    print("🐦 TWITTER/X REPORT")
    print("=" * 50)
    print("✅ Твиты отправляются напрямую в Telegram Admin")
    print("📱 Файловые драфты больше не используются")
    print("=" * 50)


if __name__ == "__main__":
    print("=== X CLIENT INFO ===")
    print("Файловые драфты убраны.")
    print("Твиты теперь идут через telegram_admin.py")
    print_drafts_report()