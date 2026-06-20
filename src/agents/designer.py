import os
import textwrap
from datetime import datetime
from typing import Dict, Optional
from PIL import Image, ImageDraw, ImageFont

from dotenv import load_dotenv
load_dotenv()

# Папка для сохранения картинок
OUTPUT_DIR = "assets/output"
TEMPLATES_DIR = "assets/templates"

# Цветовые схемы
COLOR_SCHEMES = [
    {
        "name": "dark_blue",
        "background": (15, 23, 42),
        "accent": (99, 102, 241),
        "text_primary": (248, 250, 252),
        "text_secondary": (148, 163, 184),
    },
    {
        "name": "dark_green",
        "background": (5, 46, 22),
        "accent": (34, 197, 94),
        "text_primary": (240, 253, 244),
        "text_secondary": (134, 239, 172),
    },
    {
        "name": "dark_purple",
        "background": (29, 10, 57),
        "accent": (168, 85, 247),
        "text_primary": (250, 245, 255),
        "text_secondary": (196, 181, 253),
    },
    {
        "name": "dark_orange",
        "background": (43, 15, 5),
        "accent": (249, 115, 22),
        "text_primary": (255, 247, 237),
        "text_secondary": (253, 186, 116),
    },
]


def _ensure_dirs() -> None:
    """Создаёт нужные папки если не существуют"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMPLATES_DIR, exist_ok=True)


def _get_font(size: int) -> ImageFont.ImageFont:
    """Возвращает шрифт — системный или дефолтный"""
    font_paths = [
        # Windows
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        # Linux (GitHub Actions Ubuntu)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        # macOS
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, max_chars: int) -> list:
    """Переносит текст по словам"""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current += (" " if current else "") + word
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def create_telegram_image(
    title: str,
    product_name: str,
    cta: str,
    scheme_index: Optional[int] = None,
) -> str:
    """
    Создаёт квадратную картинку для Telegram поста.
    Размер: 1080x1080px
    Возвращает путь к файлу.
    """
    _ensure_dirs()

    # Получаем username канала
    channel = os.getenv("TELEGRAM_CHANNEL_USERNAME", "@your_channel")
    channel_display = channel.replace("@", "t.me/")

    # Выбираем цветовую схему
    if scheme_index is None:
        import random
        scheme_index = random.randint(0, len(COLOR_SCHEMES) - 1)
    scheme = COLOR_SCHEMES[scheme_index % len(COLOR_SCHEMES)]

    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), scheme["background"])
    draw = ImageDraw.Draw(img)

    # ─── Декоративные элементы ───────────────────────────

    # Верхняя полоса акцента
    draw.rectangle([(0, 0), (W, 8)], fill=scheme["accent"])

    # Нижняя полоса акцента
    draw.rectangle([(0, H - 8), (W, H)], fill=scheme["accent"])

    # Большой круг — декор справа снизу
    draw.ellipse(
        [(W - 350, H - 350), (W + 150, H + 150)],
        fill=tuple(max(0, c - 10) for c in scheme["background"]),
    )

    # Маленький круг — декор слева сверху
    draw.ellipse(
        [(-100, -100), (200, 200)],
        fill=tuple(min(255, c + 10) for c in scheme["background"]),
    )

    # ─── Логотип / бейдж "AI Tools" ──────────────────────
    badge_font = _get_font(28)
    badge_text = "AI TOOLS"
    draw.rectangle([(60, 60), (260, 100)], fill=scheme["accent"])
    draw.text((70, 65), badge_text, font=badge_font, fill=scheme["text_primary"])

    # ─── Название продукта ────────────────────────────────
    product_font = _get_font(36)
    draw.text(
        (60, 130),
        f"> {product_name.upper()}",
        font=product_font,
        fill=scheme["accent"],
    )

    # ─── Заголовок (главный текст) ────────────────────────
    title_font = _get_font(72)
    title_lines = _wrap_text(title, 18)

    title_y = 220
    for line in title_lines[:4]:
        draw.text((60, title_y), line, font=title_font, fill=scheme["text_primary"])
        title_y += 85

    # ─── Разделитель ──────────────────────────────────────
    sep_y = title_y + 20
    draw.rectangle([(60, sep_y), (120, sep_y + 6)], fill=scheme["accent"])
    draw.rectangle([(130, sep_y), (190, sep_y + 6)], fill=scheme["text_secondary"])

    # ─── CTA кнопка ───────────────────────────────────────
    cta_y = H - 180
    cta_font = _get_font(40)
    cta_width = len(cta) * 22 + 60
    draw.rectangle(
        [(60, cta_y), (60 + cta_width, cta_y + 65)],
        fill=scheme["accent"],
    )
    draw.text((80, cta_y + 10), cta, font=cta_font, fill=scheme["text_primary"])

    # ─── Нижняя подпись ───────────────────────────────────
    footer_font = _get_font(26)
    draw.text(
        (60, H - 90),
        channel_display,
        font=footer_font,
        fill=scheme["text_secondary"],
    )

    # ─── Сохраняем файл ───────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"post_{timestamp}.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    img.save(filepath, "PNG", quality=95)

    return filepath


def create_image_for_post(content_plan: Dict) -> Optional[str]:
    """
    Создаёт картинку на основе плана от Strategist.
    Возвращает путь к файлу или None если ошибка.
    """
    try:
        title = content_plan.get("topic", "AI инструменты")
        product_name = content_plan.get("product", {}).get("name", "AI Tool")
        cta = content_plan.get("cta", "Попробовать бесплатно")

        filepath = create_telegram_image(
            title=title,
            product_name=product_name,
            cta=cta,
        )
        return filepath

    except Exception as e:
        print(f"[Designer] Ошибка создания картинки: {e}")
        return None


if __name__ == "__main__":
    from src.agents.strategist import create_content_plan

    print("=== DESIGNER TEST ===\n")

    plan = create_content_plan()
    print(f"Тема: {plan['topic']}")
    print(f"Продукт: {plan['product']['name']}")
    print(f"CTA: {plan['cta']}")
    print("\nСоздаём картинку...")

    filepath = create_image_for_post(plan)

    if filepath:
        print(f"\n✅ Картинка создана!")
        print(f"📁 Путь: {filepath}")
        print(f"📐 Размер: 1080x1080px")
        img = Image.open(filepath)
        img.show()
    else:
        print("❌ Ошибка создания картинки")