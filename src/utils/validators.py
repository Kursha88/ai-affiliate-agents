from typing import Dict, List, Optional


# ─── Константы ───────────────────────────────────────────
FALLBACK_MARKERS = [
    "Не удалось сгенерировать",
    "Проверь API ключи",
    "fallback",
    "error generating",
]

MAX_TELEGRAM_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024
MAX_TWEET_LENGTH = 280
MIN_POST_LENGTH = 100


def is_fallback_text(text: str) -> bool:
    """
    Проверяет что текст является fallback заглушкой.
    Защита от публикации мусора в канал.
    """
    if not text or not text.strip():
        return True
    return any(marker in text for marker in FALLBACK_MARKERS)


def validate_post_text(text: str) -> Dict:
    """
    Валидирует текст поста для Telegram.
    Возвращает словарь с результатом и проблемами.
    """
    issues: List[str] = []

    if not text or not text.strip():
        return {
            "valid": False,
            "issues": ["Текст пустой"],
            "length": 0,
        }

    length = len(text)

    if is_fallback_text(text):
        issues.append("Текст является fallback заглушкой")

    if length < MIN_POST_LENGTH:
        issues.append(f"Текст слишком короткий: {length} символов (мин {MIN_POST_LENGTH})")

    if length > MAX_TELEGRAM_LENGTH:
        issues.append(f"Текст слишком длинный: {length} символов (макс {MAX_TELEGRAM_LENGTH})")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "length": length,
    }


def validate_tweet_text(text: str) -> Dict:
    """
    Валидирует текст твита для Twitter/X.
    """
    issues: List[str] = []

    if not text or not text.strip():
        return {
            "valid": False,
            "issues": ["Текст твита пустой"],
            "length": 0,
        }

    length = len(text)

    if length > MAX_TWEET_LENGTH:
        issues.append(f"Твит слишком длинный: {length} символов (макс {MAX_TWEET_LENGTH})")

    if length < 20:
        issues.append(f"Твит слишком короткий: {length} символов")

    if text.count("#") > 3:
        issues.append("Слишком много хэштегов (рекомендуется не более 2)")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "length": length,
    }


def validate_content_plan(plan: Dict) -> Dict:
    """
    Валидирует план контента от Strategist.
    """
    issues: List[str] = []
    required_fields = ["topic", "format", "product", "cta"]

    for field in required_fields:
        if not plan.get(field):
            issues.append(f"Отсутствует обязательное поле: {field}")

    product = plan.get("product", {})
    required_product_fields = ["name", "description", "affiliate_link"]

    for field in required_product_fields:
        if not product.get(field):
            issues.append(f"Отсутствует поле продукта: {field}")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }


def validate_api_keys(keys: Dict[str, Optional[str]]) -> Dict:
    """
    Проверяет наличие API ключей.
    """
    missing = []
    for name, value in keys.items():
        if not value or not value.strip():
            missing.append(name)

    return {
        "valid": len(missing) == 0,
        "missing": missing,
    }


if __name__ == "__main__":
    print("=== VALIDATORS TEST ===\n")

    # Тест fallback
    print("1. Fallback detection:")
    print(f"   'Не удалось сгенерировать' → {is_fallback_text('Не удалось сгенерировать текст')}")
    print(f"   'Нормальный текст' → {is_fallback_text('Нормальный текст поста')}")

    # Тест валидации поста
    print("\n2. Post validation:")
    result = validate_post_text("Короткий текст")
    print(f"   Короткий текст → valid={result['valid']}, issues={result['issues']}")

    result = validate_post_text("А" * 5000)
    print(f"   Длинный текст → valid={result['valid']}, issues={result['issues']}")

    # Тест валидации твита
    print("\n3. Tweet validation:")
    result = validate_tweet_text("Отличный твит про AI! https://t.me/nejroavtomatizacia")
    print(f"   Нормальный твит → valid={result['valid']}")

    result = validate_tweet_text("А" * 300)
    print(f"   Длинный твит → valid={result['valid']}, issues={result['issues']}")

    print("\n✅ Все тесты пройдены!")