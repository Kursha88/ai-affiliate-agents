"""
VKontakte API клиент — автопостинг в группу/паблик ВКонтакте.
Позволяет привлекать русскоязычную аудиторию из VK в Telegram-канал.
"""

import os
import requests
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()


def is_vk_configured() -> bool:
    """Проверяет наличие токена VK и ID группы."""
    return bool(
        os.getenv("VK_ACCESS_TOKEN", "").strip() and
        os.getenv("VK_GROUP_ID", "").strip()
    )


def publish_to_vk(text: str, image_path: Optional[str] = None) -> Dict:
    """
    Публикует пост от имени группы в паблик ВКонтакте с ссылкой на Telegram.

    Требуемые переменные окружения:
      VK_ACCESS_TOKEN: токен сообщества или пользователя с правами wall, photos, groups
      VK_GROUP_ID: ID группы/сообщества (числовое значение, например 123456789)
    """
    token = os.getenv("VK_ACCESS_TOKEN", "").strip()
    group_id_str = os.getenv("VK_GROUP_ID", "").strip().replace("-", "")

    if not token or not group_id_str:
        return {
            "success": False,
            "error": "VK_ACCESS_TOKEN или VK_GROUP_ID не заданы",
        }

    try:
        group_id = int(group_id_str)
        # Для wall.post от имени группы owner_id должен быть отрицательным
        owner_id = -group_id

        # Добавляем ссылку на Telegram в конце поста для VK
        channel_link = os.getenv("TELEGRAM_CHANNEL_LINK", "https://t.me/nejroavtomatizacia")
        vk_text = f"{text}\n\n👉 Больше секретов и нейросетей в нашем Telegram: {channel_link}"

        payload = {
            "owner_id": owner_id,
            "from_group": 1,
            "message": vk_text,
            "access_token": token,
            "v": "5.199",
        }

        # Если есть картинка — пробуем загрузить на сервер VK
        attachments = []
        if image_path and os.path.exists(image_path):
            try:
                # 1. Получаем URL сервера для загрузки
                upload_server_url = "https://api.vk.com/method/photos.getWallUploadServer"
                srv_resp = requests.get(upload_server_url, params={
                    "group_id": group_id,
                    "access_token": token,
                    "v": "5.199",
                }, timeout=10).json()

                if "response" in srv_resp:
                    upload_url = srv_resp["response"]["upload_url"]

                    # 2. Отправляем файл
                    with open(image_path, "rb") as f:
                        up_resp = requests.post(upload_url, files={"photo": f}, timeout=15).json()

                    # 3. Сохраняем фото на стене
                    save_url = "https://api.vk.com/method/photos.saveWallPhoto"
                    save_resp = requests.post(save_url, data={
                        "group_id": group_id,
                        "photo": up_resp["photo"],
                        "server": up_resp["server"],
                        "hash": up_resp["hash"],
                        "access_token": token,
                        "v": "5.199",
                    }, timeout=10).json()

                    if "response" in save_resp and len(save_resp["response"]) > 0:
                        photo_data = save_resp["response"][0]
                        media_id = f"photo{photo_data['owner_id']}_{photo_data['id']}"
                        attachments.append(media_id)
            except Exception as img_err:
                print(f"[VK] Ошибка прикрепления фото: {img_err}")

        if attachments:
            payload["attachments"] = ",".join(attachments)

        # Публикуем запись на стену
        post_url = "https://api.vk.com/method/wall.post"
        resp = requests.post(post_url, data=payload, timeout=15).json()

        if "response" in resp:
            post_id = resp["response"].get("post_id")
            print(f"[VK] ✅ Опубликовано в группу! Post ID: {post_id}")
            return {
                "success": True,
                "post_id": post_id,
                "url": f"https://vk.com/wall-{group_id}_{post_id}",
            }
        else:
            err = resp.get("error", {})
            err_msg = f"VK Error {err.get('error_code')}: {err.get('error_msg')}"
            print(f"[VK] ❌ {err_msg}")
            return {"success": False, "error": err_msg}

    except Exception as e:
        print(f"[VK] Исключение: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print("=== VK CLIENT TEST ===")
    if is_vk_configured():
        print("VK настроен")
    else:
        print("VK не настроен (добавьте VK_ACCESS_TOKEN и VK_GROUP_ID)")
