import re
from typing import Dict


# Слова которые нужно заменить
REPLACEMENTS = {
    "automate": "автоматизировать",
    "content": "контент",
    "routine": "рутинные",
    "AI-инструмент": "AI-инструмент",
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

# Фразы которые нельзя использовать
FORBIDDEN_PHRASES = [
    "гарантированный заработок",
    "100% результат",
    "зарабатывай миллионы",
    "быстрые деньги",
    "без усилий",
    "пассивный доход гарантирован",
]

# Пометка о партнёрской ссылке
DISCLOSURE = (
    "\n\n⚠️ <i>Ссылка может быть партнёрской. "
    "Если вы зарегистрируетесь по ней, автор может получить "
    "небольшую комиссию — без доплаты для вас.</i>"
)


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


def _fix_html_tags(text: str) -> str:
    """
    Убирает незакрытые или неправильные HTML теги
    которые Telegram не поддерживает
    """
    # Оставляем только безопасные теги Telegram
    allowed_tags = ['b', 'i', 'u', 's', 'code', 'pre', 'a']
    
    # Убираем теги которые не поддерживает Telegram
    text = re.sub(r'<(?!/?(?:' + '|'.join(allowed_tags) + r')(?:\s[^>]*)?>)[^>]+>', '', text)
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


def edit_post(copywriter_result: Dict) -> Dict:
    """
    Основная функция агента Editor.
    Принимает результат от Copywriter и возвращает готовый пост.
    """
    text = copywriter_result["draft_text"]
    plan = copywriter_result["plan"]
    affiliate_link = plan["product"]["affiliate_link"]

    issues = []

    # 1. Чистим английские слова
    text = _clean_english_words(text)

    # 2. Проверяем запрещённые фразы
    forbidden = _check_forbidden_phrases(text)
    if forbidden:
        issues.append(f"Запрещённые фразы: {', '.join(forbidden)}")

    # 3. Проверяем наличие ссылки
    if not _check_link_present(text, affiliate_link):
        issues.append(f"Ссылка {affiliate_link} не найдена в тексте")
        text += f"\n\n🔗 {affiliate_link}"

    # 4. Чистим HTML теги
    text = _fix_html_tags(text)

    # 5. Добавляем пометку о партнёрской ссылке
    text = _add_disclosure(text)

    # 6. Проверяем длину
    length_check = _check_length(text)
    if length_check["warning"]:
        issues.append(length_check["warning"])

    # 7. Убираем лишние пробелы и переносы
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

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
    print(f"✔️  Готов к публикации: {editor_result['ready']}")

    if editor_result["issues"]:
        print(f"⚠️  Замечания: {editor_result['issues']}")

    print("\n" + "=" * 50)
    print("ФИНАЛЬНЫЙ ТЕКСТ:")
    print("=" * 50)
    print(editor_result["final_text"])
    print("=" * 50)