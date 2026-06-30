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
        "card_bg": (20, 28, 60),
        "dot_color": (88, 101, 242),
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
        "card_bg": (10, 40, 25),
        "dot_color": (16, 185, 129),
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
        "card_bg": (35, 10, 65),
        "dot_color": (167, 85, 247),
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
        "card_bg": (50, 20, 10),
        "dot_color": (249, 115, 22),
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
        "card_bg": (45, 10, 18),
        "dot_color": (239, 68, 68),
    },
    {
        "name": "ocean",
        "background": (5, 20, 40),
        "gradient_top": (10, 40, 80),
        "accent": (6, 182, 212),
        "accent2": (34, 211, 238),
        "text_primary": (255, 255, 255),
        "text_secondary": (160, 210, 230),
        "badge_bg": (6, 182, 212),
        "card_bg": (8, 32, 60),
        "dot_color": (6, 182, 212),
    },
]

PRODUCT_FACTS = {
    "default": ["Saves 10+ hours/week", "Used by 50K+ creators", "Free plan available"],
    "Castmagic": ["10x faster content", "Auto transcription", "50+ languages"],
    "ElevenLabs": ["1000+ AI voices", "Ultra realistic", "29 languages"],
    "Writesonic": ["10x faster writing", "100+ templates", "SEO optimized"],
    "Pictory AI": ["Text to video", "Auto captions", "1000+ templates"],
    "MindStudio": ["No-code AI", "Custom agents", "API access"],
    "Reply.io": ["Automate outreach", "10x more leads", "AI personalization"],
    "Murf": ["120+ voices", "Studio quality", "Team collaboration"],
}


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
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
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
    opacity: int = 255,
) -> None:
    x1, y1, x2, y2 = xy

    # Защита от слишком маленького прямоугольника
    min_size = radius * 2
    if x2 - x1 < min_size:
        x2 = x1 + min_size
    if y2 - y1 < min_size:
        y2 = y1 + min_size

    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.ellipse([x1, y1, x1 + 2 * radius, y1 + 2 * radius], fill=fill)
    draw.ellipse([x2 - 2 * radius, y1, x2, y1 + 2 * radius], fill=fill)
    draw.ellipse([x1, y2 - 2 * radius, x1 + 2 * radius, y2], fill=fill)
    draw.ellipse([x2 - 2 * radius, y2 - 2 * radius, x2, y2], fill=fill)


def _draw_dot_grid(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    cols: int,
    rows: int,
    spacing: int,
    color: tuple,
    radius: int = 3,
) -> None:
    """Рисует сетку точек — декоративный элемент"""
    for row in range(rows):
        for col in range(cols):
            cx = x + col * spacing
            cy = y + row * spacing
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=color,
            )


def _draw_stat_card(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    width: int,
    height: int,
    value: str,
    scheme: dict,
) -> None:
    """Рисует карточку со статистикой"""
    # Фон карточки
    _draw_rounded_rect(
        draw,
        (x, y, x + width, y + height),
        radius=16,
        fill=scheme["card_bg"],
    )

    # Акцентная полоска сверху
    _draw_rounded_rect(
        draw,
        (x + 12, y - 3, x + 60, y + 5),
        radius=4,
        fill=scheme["accent"],
    )

    # Текст
    parts = value.split(" ", 1)
    num_font = _get_font(32, bold=True)
    label_font = _get_font(22)

    if len(parts) == 2:
        draw.text(
            (x + 16, y + 14),
            parts[0],
            font=num_font,
            fill=scheme["accent2"],
        )
        draw.text(
            (x + 16, y + 50),
            parts[1],
            font=label_font,
            fill=scheme["text_secondary"],
        )
    else:
        draw.text(
            (x + 16, y + 20),
            value,
            font=num_font,
            fill=scheme["accent2"],
        )


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

    # ── Градиентный фон ──────────────────────────────────
    for i in range(500):
        ratio = i / 500
        r = int(scheme["gradient_top"][0] * (1 - ratio) + scheme["background"][0] * ratio)
        g = int(scheme["gradient_top"][1] * (1 - ratio) + scheme["background"][1] * ratio)
        b = int(scheme["gradient_top"][2] * (1 - ratio) + scheme["background"][2] * ratio)
        draw.line([(0, i), (W, i)], fill=(r, g, b))

    # ── Декоративные большие круги ───────────────────────
    circle_color = tuple(min(255, c + 15) for c in scheme["background"])
    circle_color2 = tuple(min(255, c + 25) for c in scheme["background"])

    # Большой круг справа снизу
    draw.ellipse([(680, 580), (1180, 1080)], fill=circle_color)
    # Средний круг слева снизу
    draw.ellipse([(-150, 680), (320, 1130)], fill=circle_color)
    # Малый круг справа сверху
    draw.ellipse([(820, -80), (1100, 200)], fill=circle_color2)

    # ── Сетка точек (декор) ──────────────────────────────
    dot_color = tuple(min(255, c + 35) for c in scheme["background"])
    _draw_dot_grid(
        draw, x=700, y=200, cols=8, rows=8,
        spacing=45, color=dot_color, radius=2,
    )
    _draw_dot_grid(
        draw, x=60, y=750, cols=5, rows=5,
        spacing=40, color=dot_color, radius=2,
    )

    # ── Акцентный круг с градиентом (правый верхний) ─────
    draw.ellipse([(840, 60), (1000, 220)], fill=scheme["accent"])
    accent_inner = tuple(min(255, c + 50) for c in scheme["accent"])
    draw.ellipse([(865, 85), (975, 195)], fill=accent_inner)
    draw.ellipse([(890, 110), (950, 170)], fill=scheme["accent2"])

    # ── Верхняя полоса ───────────────────────────────────
    draw.rectangle([(0, 0), (W, 7)], fill=scheme["accent"])

    # ── Бейдж AI TOOLS ───────────────────────────────────
    badge_font = _get_font(24, bold=True)
    badge_text = "⚡ AI TOOLS"
    badge_w = 170
    _draw_rounded_rect(
        draw,
        (60, 50, 60 + badge_w, 95),
        radius=22,
        fill=scheme["badge_bg"],
    )
    draw.text((80, 58), badge_text, font=badge_font, fill=(255, 255, 255))

    # ── Название продукта ─────────────────────────────────
    product_font = _get_font(36, bold=True)
    draw.text(
        (65, 120),
        f"> {product_name.upper()}",
        font=product_font,
        fill=scheme["accent2"],
    )

    # ── Декоративная линия ────────────────────────────────
    draw.rectangle([(65, 172), (200, 176)], fill=scheme["accent"])
    draw.rectangle([(210, 172), (290, 176)], fill=scheme["text_secondary"])
    draw.rectangle([(300, 172), (330, 176)], fill=scheme["accent2"])

    # ── Главный заголовок ─────────────────────────────────
    title_font = _get_font(82, bold=True)
    title_lines = _wrap_text(title, 15)

    title_y = 200
    for line in title_lines[:3]:
        # Тень
        draw.text((68, title_y + 4), line, font=title_font, fill=(0, 0, 0))
        # Основной текст
        draw.text((65, title_y), line, font=title_font, fill=scheme["text_primary"])
        title_y += 95

    # ── Подзаголовок ─────────────────────────────────────
    sub_font = _get_font(30)
    draw.text(
        (65, title_y + 15),
        "Попробуй прямо сейчас ->",
        font=sub_font,
        fill=scheme["text_secondary"],
    )

    # ── Карточки со статистикой ───────────────────────────
    facts = PRODUCT_FACTS.get(product_name, PRODUCT_FACTS["default"])
    card_y = title_y + 80
    card_w = 290
    card_h = 95
    card_gap = 18

    for i, fact in enumerate(facts[:3]):
        card_x = 65 + i * (card_w + card_gap)
        _draw_stat_card(
            draw,
            x=card_x,
            y=card_y,
            width=card_w,
            height=card_h,
            value=fact,
            scheme=scheme,
        )

    # ── Горизонтальная линия ─────────────────────────────
    line_y = card_y + card_h + 35
    draw.rectangle([(65, line_y), (W - 65, line_y + 1)], fill=scheme["card_bg"])

    # ── CTA кнопка ───────────────────────────────────────
    cta_font = _get_font(38, bold=True)
    cta_y = H - 210

    # Вычисляем ширину кнопки
    cta_text = cta if len(cta) < 25 else cta[:22] + "..."
    cta_w = min(len(cta_text) * 23 + 80, W - 130)

    # Тень кнопки
    _draw_rounded_rect(
        draw,
        (65, cta_y + 5, 65 + cta_w, cta_y + 75),
        radius=37,
        fill=(0, 0, 0),
    )
    # Кнопка
    _draw_rounded_rect(
        draw,
        (65, cta_y, 65 + cta_w, cta_y + 70),
        radius=37,
        fill=scheme["accent"],
    )
    # Текст кнопки
    draw.text((95, cta_y + 15), cta_text, font=cta_font, fill=(255, 255, 255))

    # ── Разделитель перед футером ─────────────────────────
    draw.rectangle(
        [(65, H - 108), (W - 65, H - 106)],
        fill=scheme["text_secondary"],
    )

    # ── Футер ─────────────────────────────────────────────
    footer_font = _get_font(28)
    footer_bold = _get_font(28, bold=True)

    draw.text((65, H - 87), "Channel:", font=footer_font, fill=scheme["accent2"])
    draw.text((200, H - 87), channel_display, font=footer_bold, fill=scheme["text_secondary"])

    draw.text((W - 230, H - 87), "Podpishis!", font=footer_font, fill=scheme["accent2"])

    # ── Нижняя полоса ─────────────────────────────────────
    draw.rectangle([(0, H - 7), (W, H)], fill=scheme["accent"])

    # ── Сохраняем ─────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"post_{timestamp}.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    img.save(filepath, "PNG", quality=95)

    return filepath


def create_image_for_post(content_plan: Dict) -> Optional[str]:
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

    for i in range(len(COLOR_SCHEMES)):
        plan = create_content_plan()
        print(f"Схема {i}: {COLOR_SCHEMES[i]['name']}")
        print(f"Тема: {plan['topic']}")
        print(f"Продукт: {plan['product']['name']}")

        filepath = create_telegram_image(
            title=plan["topic"],
            product_name=plan["product"]["name"],
            cta=plan.get("cta", "Попробовать бесплатно"),
            scheme_index=i,
        )

        if filepath:
            print(f"✅ Создана: {filepath}\n")
            img = Image.open(filepath)
            img.show()
            input("Нажми Enter для следующей схемы...")
        else:
            print("❌ Ошибка\n")