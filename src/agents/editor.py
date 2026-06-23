import re
from typing import Dict


REPLACEMENTS = {
    "automate": "автоматизировать",
    "content": "контент",
    "routine": "рутинные",
    "best": "лучший",
    "free": "бесплатно",
    "online": "онлайн",
    "workflow": "рабочий процесс",
    "deadline": "дедлайн",
    "feedback": "обратная связь",
    "update": "обновление",
    "upload": "загрузка",
    "download": "скачать",
}

FORBIDDEN_PHRASES = [
    "гарантированный заработок",
    "100% результат",
    "зарабатывай миллионы",
    "быстрые деньги",
    "без усилий",
    "пассивный доход гарантирован",
]

DISCLOSURE = (
    "\n\n⚠️ <i>Ссылка может быть партнёрской. "
    "Если вы зарегистрируетесь по ней, автор может получить "
    "небольшую комиссию — без доплаты для вас.</i>"
)


def _remove_markdown(text: str) -> str:
    """
    Убирает Markdown разметку которую добавляет AI
    и которую Telegram не поддерживает в обычном режиме
    """
    # Убираем жирный текст **текст** → текст
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)

    # Убираем курсив *текст* → текст
    text = re.sub(r'\*(.+?)\*', r'\1', text)

    # Убираем markdown ссылки [текст](url) → url
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\2', text)

    # Убираем заголовки ## Заголовок → Заголовок
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Убираем горизонтальные линии ---
    text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)

    # Убираем markdown буллиты * текст → • текст
    text = re.sub(r'^\* (.+)$', r'• \1', text, flags=re.MULTILINE)

    # Убираем inline code `код` → код
    text = re.sub(r'`([^`]+)`', r'\1', text)

    return text


def _clean_english_words(text: str) -> str:
    """Заменяет английские слова на русские аналоги"""
    for eng, rus in REPLACEMENTS.items():
        text = re.sub(rf'\b{re.escape(eng)}\b', rus, text, flags=re.IGNORECASE)
    return text


def _check_forbidden_phrases(text: str) -> list:
    """Проверяет наличие запрещённых фраз"""
    found = []
    for phrase in FORBIDDEN_PHRASES:
        if phrase.lower() in text.lower():
            found.append(phrase)
    return found


def _check_link_present(text: str, affiliate_link: str) -> bool:
    """Проверяет что партнёрская ссылка есть в тексте"""
    domain = affiliate_link.replace("https://", "").replace("http://", "").split("/")[0]
    return domain in text


def _fix_bullets(text: str) -> str:
    """Заменяет разные виды буллитов на единый стиль"""
    # Заменяем - буллиты на •
    text = re.sub(r'^[\-–—]\s+', '• ', text, flags=re.MULTILINE)
    return text


def _add_disclosure(text: str) -> str:
    """Добавляет пометку о партнёрской ссылке"""
    if "партнёрской" not in text and "партнерской" not in text:
        text += DISCLOSURE
    return text


def _check_length(text: str) -> dict:
    """Проверяет длину текста"""
    length = len(text)
    return {
        "length": length,
        "ok": 100 <= length <= 4096,
        "warning": "Текст слишком короткий" if length < 100 else (
            "Текст слишком длинный для Telegram" if length > 4096 else None
        ),
    }


def _trim_if_too_long(text: str, max_length: int = 3800) -> str:
    """
    Если текст слишком длинный — обрезаем до последнего
    полного предложения перед лимитом
    """
    if len(text) <= max_length:
        return text

    # Ищем последнюю точку перед лимитом
    trimmed = text[:max_length]
    last_dot = max(
        trimmed.rfind('.'),
        trimmed.rfind('!'),
        trimmed.rfind('?'),
    )

    if last_dot > 0:
        return trimmed[:last_dot + 1]

    return trimmed


def edit_post(copywriter_result: Dict) -> Dict:
    """
    Основная функция агента Editor.
    Принимает результат от Copywriter и возвращает готовый пост.
    """
    text = copywriter_result["draft_text"]
    plan = copywriter_result["plan"]
    affiliate_link = plan["product"]["affiliate_link"]

    issues = []

    # 1. Убираем Markdown разметку
    text = _remove_markdown(text)

    # 2. Чистим английские слова
    text = _clean_english_words(text)

    # 3. Унифицируем буллиты
    text = _fix_bullets(text)

    # 4. Проверяем запрещённые фразы
    forbidden = _check_forbidden_phrases(text)
    if forbidden:
        issues.append(f"Запрещённые фразы: {', '.join(forbidden)}")

    # 5. Проверяем наличие ссылки
    if not _check_link_present(text, affiliate_link):
        issues.append(f"Ссылка {affiliate_link} не найдена в тексте")
        text += f"\n\n🔗 {affiliate_link}"

    # 6. Добавляем пометку о партнёрской ссылке
    text = _add_disclosure(text)

    # 7. Обрезаем если слишком длинный
    text = _trim_if_too_long(text)

    # 8. Убираем лишние пробелы и переносы
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    # 9. Проверяем длину
    length_check = _check_length(text)
    if length_check["warning"]:
        issues.append(length_check["warning"])

    return {
        "plan": plan,
        "final_text": text,
        "ai_source": copywriter_result["ai_source"],
        "length": length_check["length"],
        "issues": issues,
        "ready": len(issues) == 0,
    }


if __name__ == "__main__":
    from src.agents.strategist import create_content_plan
    from src.agents.copywriter import write_post

    print("=== EDITOR TEST ===\n")

    plan = create_content_plan()
    copywriter_result = write_post(plan)
    editor_result = edit_post(copywriter_result)

    print(f"✅ Пост отредактирован! (AI: {editor_result['ai_source']})")
    print(f"📏 Длина: {editor_result['length']} символов")
    print(f"✔️  Готов: {editor_result['ready']}")

    if editor_result["issues"]:
        print(f"⚠️  Замечания: {editor_result['issues']}")

    print("\n" + "=" * 50)
    print("ФИНАЛЬНЫЙ ТЕКСТ:")
    print("=" * 50)
    print(editor_result["final_text"])
    print("=" * 50)