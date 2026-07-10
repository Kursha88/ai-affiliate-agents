from abc import ABC, abstractmethod
from typing import Dict
from datetime import datetime


class BasePublisher(ABC):
    """
    Базовый класс для всех publishers.
    Каждая новая платформа наследует этот класс
    и реализует методы format_content и publish.
    """

    platform: str = "unknown"
    max_length: int = 0
    supports_markdown: bool = False
    supports_images: bool = False

    def publish_from_editor(self, editor_result: Dict) -> Dict:
        """
        Главный метод — принимает результат Editor
        и публикует на платформу.
        """
        # Проверяем что пост готов
        if not editor_result.get("ready"):
            return self._error_result(
                error=f"Пост не готов к публикации: {editor_result.get('issues')}",
                editor_result=editor_result,
            )

        # Форматируем контент под платформу
        try:
            content = self.format_content(editor_result)
        except Exception as e:
            return self._error_result(
                error=f"Ошибка форматирования: {str(e)}",
                editor_result=editor_result,
            )

        # Публикуем
        try:
            result = self.publish(content, editor_result)
        except Exception as e:
            return self._error_result(
                error=f"Ошибка публикации: {str(e)}",
                editor_result=editor_result,
            )

        return result

    @abstractmethod
    def format_content(self, editor_result: Dict) -> str:
        """
        Форматирует контент под конкретную платформу.
        Каждый publisher реализует по-своему.
        """
        pass

    @abstractmethod
    def publish(self, content: str, editor_result: Dict) -> Dict:
        """
        Отправляет контент на платформу.
        Возвращает стандартный словарь результата.
        """
        pass

    def is_available(self) -> bool:
        """
        Проверяет доступность платформы.
        Переопределяй если нужна проверка токена/API.
        """
        return True

    def _success_result(self, editor_result: Dict, **kwargs) -> Dict:
        """Стандартный успешный результат."""
        return {
            "success": True,
            "platform": self.platform,
            "published_at": datetime.now().isoformat(),
            "topic": editor_result.get("plan", {}).get("topic", ""),
            "product": editor_result.get("plan", {}).get("product", {}).get("name", ""),
            "affiliate_link": editor_result.get("plan", {}).get("product", {}).get("affiliate_link", ""),
            "length": editor_result.get("length", 0),
            "ai_source": editor_result.get("ai_source", ""),
            **kwargs,
        }

    def _error_result(self, error: str, editor_result: Dict) -> Dict:
        """Стандартный результат с ошибкой."""
        return {
            "success": False,
            "platform": self.platform,
            "published_at": datetime.now().isoformat(),
            "error": error,
            "topic": editor_result.get("plan", {}).get("topic", ""),
            "product": editor_result.get("plan", {}).get("product", {}).get("name", ""),
        }