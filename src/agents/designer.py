import os
import random
from datetime import datetime
from typing import Dict, Optional
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = "assets/output"
TEMPLATES_DIR = "assets/templates"

COLOR_SCHEMES = [
    {
        "name": "midnight_blue",
        "background": (10, 15, 35),
        "gradient_top": (20, 30, 70),
        "accent": (88, 101, 242),
        "accent2": (130, 140, 255),
        "text_primary": (255, 255, 255),
        "text_secondary": (180, 190, 220),
        "badge_bg": (88, 101, 242),
    },
    {
        "name": "emerald",
        "background": (5, 25, 15),
        "gradient_top": (10, 50, 30),
        "accent": (16, 185, 129),
        "accent2": (52, 211, 153),
        "text_primary": (255, 255, 255),
        "text_secondary": (160, 220, 190),
        "badge_bg": (16, 185, 129),
    },
    {
        "name": "royal_purple",
        "background": (20, 5, 40),
        "gradient_top": (40, 10, 80),
        "accent": (167, 85, 247),
        "accent2": (196, 130, 255),
        "text_primary": (255, 255, 255),
        "text_secondary": (200, 170, 240),
        "badge_bg": (167, 85, 247),
    },
    {
        "name": "sunset_orange",
        "background": (30, 10, 5),
        "gradient_top": (60, 20, 10),
        "accent": (249, 115, 22),
        "accent2": (251, 160, 80),
        "text_primary": (255, 255, 255),
        "text_secondary": (240, 200, 170),
        "badge_bg": (249, 115, 22),
    },
    {
        "name": "crimson",
        "background": (25, 5, 10),
        "gradient_top": (55, 10, 20),
        "accent": (239, 68, 68),
        "accent2": (252, 120, 120),
        "text_primary": (255, 255, 255),
        "text_secondary": (240, 180, 180),
        "badge_bg": (239, 68, 68),
    },
]


def _ensure_dirs() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMPLATES_DIR, exist_ok=True)


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    font_paths_bold = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ]
    font_paths_regular = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    paths = font_paths_bold if bold else font_paths_regular
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    for path in font_paths_regular:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, max_chars: int) -> list:
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


def _draw_rounded_rect(
    draw: ImageDraw.Draw,
    xy: tuple,
    radius: int,
    fill: tuple,
) -> None:
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.ellipse([x1, y1, x1 + 2 * radius, y1 + 2 * radius], fill=fill)
    draw.ellipse([x2 - 2 * radius, y1, x2, y1 + 2 * radius], fill=fill)
    draw.ellipse([x1, y2 - 2 * radius, x1 + 2 * radius, y2], fill=fill)
    draw.ellipse([x2 - 2 * radius, y2 - 2 * radius, x2, y2], fill=fill)


def create_telegram_image(
    title: str,
    product_name: str,
    cta: str,
    scheme_index: Optional[int] = None,
) -> str:
    _ensure_dirs()

    channel = os.getenv("TELEGRAM_CHANNEL_USERNAME", "@nejroavtomatizacia")
    channel_display = channel.replace("@", "t.me/")

    if scheme_index is None:
        scheme_index = random.randint(0, len(COLOR_SCHEMES) - 1)
    scheme = COLOR_SCHEMES[scheme_index % len(COLOR_SCHEMES)]

    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), scheme["background"])
    draw = ImageDraw.Draw(img)

    # Градиентный фон
    for i in range(400):
        ratio = i / 400
        r = int(scheme["gradient_top"][0] * (1 - ratio) + scheme["background"][0] * ratio)
        g = int(scheme["gradient_top"][1] * (1 - ratio) + scheme["background"][1] * ratio)
        b = int(scheme["gradient_top"][2] * (1 - ratio) + scheme["background"][2] * ratio)
        draw.line([(0, i), (W, i)], fill=(r, g, b))

    # Декоративные круги
    circle_color = tuple(min(255, c + 20) for c in scheme["background"])
    draw.ellipse([(700, 650), (1200, 1150)], fill=circle_color)
    draw.ellipse([(-100, 700), (300, 1100)], fill=circle_color)

    # Акцентный круг справа сверху
    accent_light = tuple(min(255, c + 40) for c in scheme["accent"])
    draw.ellipse([(850, 80), (980, 210)], fill=scheme["accent"])
    draw.ellipse([(870, 100), (960, 190)], fill=accent_light)

    # Верхняя полоса
    draw.rectangle([(0, 0), (W, 6)], fill=scheme["accent"])

    # Бейдж AI TOOLS
    badge_font = _get_font(26, bold=True)
    badge_text = "AI TOOLS"
    badge_w = len(badge_text) * 16 + 40
    _draw_rounded_rect(
        draw,
        (60, 55, 60 + badge_w, 100),
        radius=20,
        fill=scheme["badge_bg"],
    )
    draw.text((78, 63), badge_text, font=badge_font, fill=(255, 255, 255))

    # Название продукта
    product_font = _get_font(34, bold=True)
    draw.text(
        (65, 125),
        f"> {product_name.upper()}",
        font=product_font,
        fill=scheme["accent2"],
    )

    # Декоративная линия
    draw.rectangle([(65, 175), (180, 179)], fill=scheme["accent"])
    draw.rectangle([(190, 175), (260, 179)], fill=scheme["text_secondary"])

    # Главный заголовок
    title_font = _get_font(78, bold=True)
    title_lines = _wrap_text(title, 16)

    title_y = 210
    for line in title_lines[:3]:
        draw.text((67, title_y + 3), line, font=title_font, fill=(0, 0, 0))
        draw.text((65, title_y), line, font=title_font, fill=scheme["text_primary"])
        title_y += 92

    # Подзаголовок
    sub_font = _get_font(32)
    draw.text(
        (65, title_y + 20),
        "Попробуй прямо сейчас ->",
        font=sub_font,
        fill=scheme["text_secondary"],
    )

    # CTA кнопка
    cta_font = _get_font(38, bold=True)
    cta_y = H - 200
    cta_w = len(cta) * 22 + 80

    # Тень кнопки
    _draw_rounded_rect(
        draw,
        (65, cta_y + 4, 65 + cta_w, cta_y + 74),
        radius=35,
        fill=(0, 0, 0),
    )
    # Кнопка
    _draw_rounded_rect(
        draw,
        (65, cta_y, 65 + cta_w, cta_y + 70),
        radius=35,
        fill=scheme["accent"],
    )
    draw.text((90, cta_y + 14), cta, font=cta_font, fill=(255, 255, 255))

    # Разделитель
    draw.rectangle(
        [(65, H - 105), (W - 65, H - 103)],
        fill=scheme["text_secondary"],
    )

    # Нижняя подпись
    footer_font = _get_font(28)
    draw.text(
        (65, H - 85),
        "Channel:",
        font=footer_font,
        fill=scheme["accent2"],
    )
    draw.text(
        (190, H - 85),
        channel_display,
        font=footer_font,
        fill=scheme["text_secondary"],
    )

    right_font = _get_font(26)
    draw.text(
        (W - 220, H - 85),
        "Podpishis!",
        font=right_font,
        fill=scheme["accent2"],
    )

    # Нижняя полоса
    draw.rectangle([(0, H - 6), (W, H)], fill=scheme["accent"])

    # Сохраняем
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"post_{timestamp}.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    img.save(filepath, "PNG", quality=95)

    return filepath


def create_image_for_post(content_plan: Dict) -> Optional[str]:
    try:
        title = content_plan.get("topic", "AI инструменты")
        product_name = content_plan.get("product", {}).get("name", "AI Tool")
        cta = content_plan.get("cta", "Попrobovat besplatno")

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
    print("\nСоздаём картинку...")

    filepath = create_image_for_post(plan)

    if filepath:
        print(f"\n✅ Картинка создана: {filepath}")
        img = Image.open(filepath)
        img.show()
    else:
        print("❌ Ошибка создания картинки")