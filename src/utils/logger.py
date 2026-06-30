import os
import logging
from datetime import datetime
from typing import Optional


# ─── Цвета для терминала ─────────────────────────────────
COLORS = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "red":     "\033[91m",
    "green":   "\033[92m",
    "yellow":  "\033[93m",
    "blue":    "\033[94m",
    "magenta": "\033[95m",
    "cyan":    "\033[96m",
    "white":   "\033[97m",
    "gray":    "\033[90m",
}

# ─── Эмодзи для уровней ──────────────────────────────────
LEVEL_ICONS = {
    "DEBUG":    "🔍",
    "INFO":     "✅",
    "WARNING":  "⚠️ ",
    "ERROR":    "❌",
    "CRITICAL": "🚨",
    "STEP":     "▶️ ",
    "SUCCESS":  "🎉",
    "SKIP":     "⏭️ ",
}


class PipelineLogger:
    """
    Единый логгер для всего проекта.
    Красивый вывод в терминал + запись в файл.
    """

    def __init__(self, name: str = "pipeline", log_file: Optional[str] = None):
        self.name = name
        self._step_counter = 0
        self._start_time = datetime.now()

        # Настраиваем Python logging
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)

        # Убираем дублирование handlers
        if not self._logger.handlers:
            # Консольный handler
            console = logging.StreamHandler()
            console.setLevel(logging.DEBUG)
            console.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(console)

            # Файловый handler если нужен
            if log_file:
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                file_handler = logging.FileHandler(log_file, encoding="utf-8")
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(
                    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
                )
                self._logger.addHandler(file_handler)

    def _format(self, level: str, message: str, color: str = "white") -> str:
        icon = LEVEL_ICONS.get(level, "•")
        c = COLORS.get(color, "")
        reset = COLORS["reset"]
        return f"   {icon} {c}{message}{reset}"

    def step(self, number: int, title: str) -> None:
        """Красивый заголовок шага пайплайна"""
        self._step_counter = number
        line = f"\n{number}️⃣  {title}..."
        self._logger.info(line)

    def success(self, message: str) -> None:
        self._logger.info(self._format("INFO", message, "green"))

    def warning(self, message: str) -> None:
        self._logger.warning(self._format("WARNING", message, "yellow"))

    def error(self, message: str) -> None:
        self._logger.error(self._format("ERROR", message, "red"))

    def info(self, message: str) -> None:
        self._logger.info(self._format("INFO", message, "cyan"))

    def skip(self, message: str) -> None:
        self._logger.info(self._format("SKIP", message, "gray"))

    def debug(self, message: str) -> None:
        self._logger.debug(self._format("DEBUG", message, "gray"))

    def divider(self, char: str = "=", length: int = 55) -> None:
        self._logger.info(char * length)

    def header(self, title: str) -> None:
        """Красивый заголовок пайплайна"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.divider()
        self._logger.info(f"🤖 {title}")
        self._logger.info(f"⏰ {now}")
        self.divider()

    def summary(self, items: dict) -> None:
        """Итоговая сводка"""
        self.divider()
        self._logger.info("🎉 ПАЙПЛАЙН ЗАВЕРШЁН УСПЕШНО!")
        for key, value in items.items():
            self._logger.info(f"   {key}: {value}")
        self.divider()

    def elapsed(self) -> str:
        """Возвращает время выполнения"""
        delta = datetime.now() - self._start_time
        seconds = delta.total_seconds()
        if seconds < 60:
            return f"{seconds:.1f}с"
        return f"{int(seconds // 60)}м {int(seconds % 60)}с"


# ─── Глобальный экземпляр ────────────────────────────────
_logger: Optional[PipelineLogger] = None


def get_logger(name: str = "pipeline") -> PipelineLogger:
    """
    Возвращает глобальный экземпляр логгера.
    Создаёт его при первом вызове.
    """
    global _logger
    if _logger is None:
        _logger = PipelineLogger(
            name=name,
            log_file="data/logs/pipeline.log",
        )
    return _logger


def reset_logger() -> None:
    """Сбрасывает логгер (для тестов)"""
    global _logger
    _logger = None


if __name__ == "__main__":
    log = get_logger()

    log.header("AI AFFILIATE AGENTS — ТЕСТ ЛОГГЕРА")

    log.step(1, "STRATEGIST: выбираю тему и продукт")
    log.success("Тема: AI для создания видео")
    log.success("Продукт: Castmagic")

    log.step(2, "COPYWRITER: пишу пост")
    log.success("Черновик готов (368 символов)")
    log.warning("Замечание: текст немного длинноват")

    log.step(3, "DESIGNER: создаю картинку")
    log.skip("Картинка не создана — публикуем без фото")

    log.step(4, "PUBLISHER: публикую в Telegram")
    log.success("Опубликовано! Message ID: 141")
    log.error("Ошибка отправки (тест)")

    log.summary({
        "Тема":     "AI для создания видео",
        "Продукт":  "Castmagic",
        "Telegram": "✅ Опубликовано",
        "Время":    log.elapsed(),
    })