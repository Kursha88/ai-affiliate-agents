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


def _format_telegram_html(text: str) -> str:
    """
    Преобразует Markdown разметку в валидный Telegram HTML:
    **жирный** ➔ <b>жирный</b>
    *курсив* ➔ <i>курсив</i>
    `код` ➔ <code>код</code>
    """
    # 1. Сначала превращаем **жирный** в <b>жирный</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # 2. Одиночные *курсив* в <i>курсив</i> (если не часть буллитов)
    text = re.sub(r'(?<!\*)\*([^\*\n]+?)\*(?!\*)', r'<i>\1</i>', text)

    # 3. `inline code` в <code>code</code>
    text = re.sub(r'`([^`\n]+?)`', r'<code>\1</code>', text)

    # 4. Убираем заголовки ## Заголовок ➔ Заголовок
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # 5. Убираем горизонтальные линии ---
    text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)

    # 6. Убираем markdown буллиты * текст ➔ • текст
    text = re.sub(r'^\*\s+(.+)$', r'• \1', text, flags=re.MULTILINE)

    return text


def _clean_ai_chatter(text: str) -> str:
    """Дополнительная защита от роботских вводных фраз."""
    lines = text.split("\n")
    cleaned = []
    skip = True
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if skip:
            if not stripped:
                continue
            if lower.startswith("вот ") or "для твоего telegram" in lower or "для вашего telegram" in lower:
                continue
            skip = False
        cleaned.append(line)
    return "\n".join(cleaned).strip()


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


def _fix_bullets(text: str) -> str:
    """Заменяет разные виды дефисов на красивые точки"""
    text = re.sub(r'^[\-–—]\s+', '• ', text, flags=re.MULTILINE)
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
    """Обрезает до последнего полного предложения перед лимитом"""
    if len(text) <= max_length:
        return text

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
    Чистит и форматирует пост в HTML для Telegram.
    """
    text = copywriter_result["draft_text"]
    plan = copywriter_result["plan"]
    mode = plan.get("mode", "growth")

    issues = []

    # 1. Удаляем вступительный мусор
    text = _clean_ai_chatter(text)

    # 2. Форматируем в Telegram HTML (жирный <b>, курсив <i>)
    text = _format_telegram_html(text)

    # 3. Чистим английские слова
    text = _clean_english_words(text)

    # 4. Унифицируем буллиты
    text = _fix_bullets(text)

    # 5. Проверяем запрещённые фразы
    forbidden = _check_forbidden_phrases(text)
    if forbidden:
        issues.append(f"Запрещённые фразы: {', '.join(forbidden)}")

    # 6. Если партнерский режим (affiliate) — добавляем партнерскую ссылку
    if mode == "affiliate":
        affiliate_link = plan.get("product", {}).get("affiliate_link", "")
        if affiliate_link and affiliate_link not in text:
            text += f"\n\n🔗 Попробовать: {affiliate_link}"

    # 7. Обрезаем если слишком длинный
    text = _trim_if_too_long(text)

    # 8. Убираем лишние пустые строки
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
        "mode": mode,
    }