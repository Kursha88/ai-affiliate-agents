"""
Pinterest API v5 клиент — автопостинг пинов со ссылкой на Telegram-канал.
Поддерживает автоматическое создание доски (Board), если она еще не создана.
"""

import os
import base64
import requests
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()


def is_pinterest_configured() -> bool:
    """Проверяет наличие токена Pinterest."""
    return bool(os.getenv("PINTEREST_ACCESS_TOKEN", "").strip())


def _get_or_create_board(token: str, board_id: Optional[str] = None) -> Optional[str]:
    """
    Получает существующий board_id или автоматически создает новую доску на Pinterest.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if board_id and board_id.strip():
        return board_id.strip()

    # 1. Проверяем список существующих досок
    try:
        boards_url = "https://api.pinterest.com/v5/boards"
        resp = requests.get(boards_url, headers=headers, timeout=15)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                first_board_id = items[0].get("id")
                print(f"[Pinterest] Найдена существующая доска: {items[0].get('name')} (ID: {first_board_id})")
                return first_board_id

        # 2. Если досок нет — создаем новую доску автоматически
        print("[Pinterest] Создаю новую доску 'Нейросети и AI Лайфхаки'...")
        create_payload = {
            "name": "Нейросети и AI Лайфхаки",
            "description": "Секреты, промпты и бесплатные инструменты искусственного интеллекта",
            "privacy": "PUBLIC",
        }
        create_resp = requests.post(boards_url, headers=headers, json=create_payload, timeout=15)
        if create_resp.status_code in [200, 201]:
            new_id = create_resp.json().get("id")
            print(f"[Pinterest] ✅ Доска успешно создана! ID: {new_id}")
            return new_id
        else:
            print(f"[Pinterest] ❌ Ошибка создания доски: {create_resp.status_code} - {create_resp.text}")
            return None

    except Exception as e:
        print(f"[Pinterest] Ошибка проверки досок: {e}")
        return None


def create_pin(
    title: str,
    description: str,
    image_url_or_path: str,
    link: Optional[str] = None,
) -> Dict:
    """
    Создает новый Пин на Pinterest через API v5.
    """
    token = os.getenv("PINTEREST_ACCESS_TOKEN", "").strip()
    target_link = link or os.getenv("TELEGRAM_CHANNEL_LINK", "https://t.me/nejroavtomatizacia")

    if not token:
        return {
            "success": False,
            "error": "PINTEREST_ACCESS_TOKEN не настроен в Secrets / .env",
        }

    # Получаем или создаем доску
    env_board_id = os.getenv("PINTEREST_BOARD_ID", "").strip()
    board_id = _get_or_create_board(token, env_board_id)

    if not board_id:
        return {
            "success": False,
            "error": "Не удалось получить или создать доску на Pinterest. Проверьте права токена (нужны boards:read, boards:write, pins:read, pins:write)",
        }

    try:
        url = "https://api.pinterest.com/v5/pins"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Формируем Base64 медиа
        if image_url_or_path and os.path.exists(image_url_or_path):
            with open(image_url_or_path, "rb") as img_file:
                b64_data = base64.b64encode(img_file.read()).decode("utf-8")
            media_source = {
                "source_type": "image_base64",
                "content_type": "image/png",
                "data": b64_data,
            }
        else:
            return {"success": False, "error": "Изображение не найдено на диске"}

        payload = {
            "board_id": board_id,
            "title": title[:100],
            "description": f"{description[:400]}\n\nВсе секреты и промпты в Telegram: {target_link}",
            "link": target_link,
            "media_source": media_source,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code in [200, 201]:
            data = resp.json()
            pin_id = data.get("id")
            pin_url = f"https://www.pinterest.com/pin/{pin_id}"
            print(f"[Pinterest] ✅ ПИН УСПЕШНО ОПУБЛИКОВАН! {pin_url}")
            return {
                "success": True,
                "pin_id": pin_id,
                "url": pin_url,
            }
        else:
            err_text = resp.text
            print(f"[Pinterest] ❌ HTTP {resp.status_code}: {err_text}")
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {err_text[:200]}",
            }

    except Exception as e:
        print(f"[Pinterest] Ошибка: {e}")
        return {"success": False, "error": str(e)}
