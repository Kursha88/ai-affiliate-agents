"""
Pinterest API v5 клиент — автопостинг пинов со ссылкой на Telegram-канал.
"""

import os
import requests
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()


def is_pinterest_configured() -> bool:
    """Проверяет наличие токена Pinterest и ID доски."""
    return bool(
        os.getenv("PINTEREST_ACCESS_TOKEN", "").strip() and
        os.getenv("PINTEREST_BOARD_ID", "").strip()
    )


def create_pin(
    title: str,
    description: str,
    image_url_or_path: str,
    link: Optional[str] = None,
) -> Dict:
    """
    Создает новый Пин на Pinterest через API v5.

    Требуемые переменные окружения:
      PINTEREST_ACCESS_TOKEN: Access Token с правами boards:read, pins:read, pins:write
      PINTEREST_BOARD_ID: ID доски, куда публиковать пины
    """
    token = os.getenv("PINTEREST_ACCESS_TOKEN", "").strip()
    board_id = os.getenv("PINTEREST_BOARD_ID", "").strip()
    target_link = link or os.getenv("TELEGRAM_CHANNEL_LINK", "https://t.me/nejroavtomatizacia")

    if not token or not board_id:
        return {
            "success": False,
            "error": "PINTEREST_ACCESS_TOKEN или PINTEREST_BOARD_ID не настроены",
        }

    try:
        url = "https://api.pinterest.com/v5/pins"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Если передана локальная картинка — в Pinterest API v5 передается media_source
        payload = {
            "board_id": board_id,
            "title": title[:100],
            "description": f"{description[:450]}\n\nПодробнее в Telegram: {target_link}",
            "link": target_link,
            "media_source": {
                "source_type": "image_url",
                "url": image_url_or_path if image_url_or_path.startswith("http") else "",
            }
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code in [200, 201]:
            data = resp.json()
            pin_id = data.get("id")
            print(f"[Pinterest] ✅ Пин создан! ID: {pin_id}")
            return {
                "success": True,
                "pin_id": pin_id,
                "url": f"https://www.pinterest.com/pin/{pin_id}",
            }
        else:
            print(f"[Pinterest] ❌ HTTP {resp.status_code}: {resp.text}")
            return {
                "success": False,
                "error": f"Pinterest HTTP {resp.status_code}: {resp.text}",
            }

    except Exception as e:
        print(f"[Pinterest] Ошибка: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print("=== PINTEREST TEST ===")
    if is_pinterest_configured():
        print("Pinterest настроен")
    else:
        print("Pinterest не настроен (нужен PINTEREST_ACCESS_TOKEN и PINTEREST_BOARD_ID)")
