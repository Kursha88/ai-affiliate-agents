from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.core.config import Config
from src.utils.logger import get_logger


class BaseAgent(ABC):
    """
    Базовый класс для всех агентов пайплайна.

    Каждый агент:
    - Имеет имя и логгер
    - Принимает данные через run()
    - Возвращает стандартизированный результат
    - Обрабатывает ошибки единообразно
    """

    def __init__(self, name: str):
        self.name = name
        self.config = Config
        self.logger = get_logger()
        self._last_error: Optional[str] = None

    @abstractmethod
    def run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Основной метод агента.
        Принимает данные от предыдущего шага.
        Возвращает результат для следующего шага.
        """
        pass

    def _success(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Стандартный успешный ответ"""
        return {
            "success": True,
            "agent": self.name,
            **data,
        }

    def _error(self, message: str, step: Optional[str] = None) -> Dict[str, Any]:
        """Стандартный ответ с ошибкой"""
        self._last_error = message
        self.logger.error(f"{self.name}: {message}")
        return {
            "success": False,
            "agent": self.name,
            "step": step or self.name,
            "error": message,
        }

    def _warn(self, message: str) -> None:
        """Логирует предупреждение"""
        self.logger.warning(f"{self.name}: {message}")

    def _info(self, message: str) -> None:
        """Логирует информацию"""
        self.logger.success(f"{message}")

    def safe_run(self, data: Dict[str, Any], critical: bool = True) -> Dict[str, Any]:
        """
        Безопасный запуск агента с перехватом ошибок.

        Args:
            data: входные данные
            critical: если True — ошибка останавливает пайплайн
                      если False — ошибка логируется но не останавливает

        Returns:
            Результат агента или error dict
        """
        try:
            return self.run(data)
        except Exception as e:
            error_msg = f"Неожиданная ошибка: {str(e)}"
            if critical:
                return self._error(error_msg)
            else:
                self._warn(f"{error_msg} (не критично, продолжаем)")
                return {
                    "success": False,
                    "agent": self.name,
                    "error": error_msg,
                    "critical": False,
                }

    def __repr__(self) -> str:
        return f"<Agent: {self.name}>"


class AgentResult:
    """
    Хелпер для работы с результатами агентов.
    Позволяет легко проверять успех и получать данные.
    """

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    @property
    def success(self) -> bool:
        return self._data.get("success", False)

    @property
    def error(self) -> Optional[str]:
        return self._data.get("error")

    @property
    def agent(self) -> str:
        return self._data.get("agent", "unknown")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def to_dict(self) -> Dict[str, Any]:
        return self._data


if __name__ == "__main__":
    print("=== BASE AGENT TEST ===\n")

    # Создаём тестового агента
    class TestAgent(BaseAgent):
        def __init__(self):
            super().__init__("TestAgent")

        def run(self, data: Dict[str, Any]) -> Dict[str, Any]:
            self._info("Тестовый агент запущен")
            return self._success({
                "result": "test_data",
                "input": data,
            })

    agent = TestAgent()
    print(f"Агент: {agent}")

    result = agent.safe_run({"test": "input"})
    print(f"Успех: {result['success']}")
    print(f"Агент: {result['agent']}")
    print(f"Результат: {result['result']}")

    # Тест AgentResult
    ar = AgentResult(result)
    print(f"\nAgentResult:")
    print(f"  success: {ar.success}")
    print(f"  agent: {ar.agent}")
    print(f"  result: {ar.get('result')}")

    print("\n✅ Base Agent работает!")