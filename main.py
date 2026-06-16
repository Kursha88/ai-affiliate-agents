import os
import asyncio
import requests
from telegram import Bot
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

# ============================================
# КОНФИГУРАЦИЯ (загружаем из переменных окружения)
# ============================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
REFERRAL_LINK = os.environ.get("REFERRAL_LINK", "https://pictory.ai/?ref=TEST")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# Проверка наличия всех необходимых переменных
if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, GROQ_API_KEY]):
    raise ValueError(" Missing required environment variables!")

# ============================================
# БАЗА ДАННЫХ ИИ-ИНСТРУМЕНТОВ
# ============================================

AI_TOOLS_DB = [
    {
        "name": "Notion AI",
        "description": "ИИ-помощник для заметок и организации работы",
        "category": "продуктивность",
        "features": ["автозаполнение", "суммаризация", "перевод"]
    },
    {
        "name": "ChatGPT",
        "description": "Мощный ИИ-ассистент от OpenAI",
        "category": "универсальный",
        "features": ["чат", "генерация кода", "анализ текста"]
    },
    {
        "name": "Midjourney",
        "description": "Генератор изображений по текстовому описанию",
        "category": "творчество",
        "features": ["арт", "дизайн", "иллюстрации"]
    },
    {
        "name": "Jasper AI",
        "description": "ИИ для копирайтинга и маркетинга",
        "category": "маркетинг",
        "features": ["тексты", "реклама", "SEO"]
    },
    {
        "name": "Descript",
        "description": "ИИ для редактирования видео и подкастов",
        "category": "видео",
        "features": ["монтаж", "транскрибация", "озвучка"]
    },
    {
        "name": "Leonardo AI",
        "description": "Продвинутый генератор артов и изображений",
        "category": "творчество",
        "features": ["3D", "концепт-арт", "аниме"]
    },
    {
        "name": "Copy.ai",
        "description": "ИИ для создания маркетингового контента",
        "category": "маркетинг",
        "features": ["посты", "email", "лендинги"]
    },
    {
        "name": "Murf AI",
        "description": "ИИ-генератор реалистичной речи",
        "category": "аудио",
        "features": ["озвучка", "подкасты", "видео"]
    }
]

# ============================================
# АГЕНТ 1: ИССЛЕДОВАТЕЛЬ (выбирает инструмент)
# ============================================

class ResearcherAgent:
    """Агент выбирает случайный ИИ-инструмент для обзора"""
    
    def __init__(self):
        self.tools = AI_TOOLS_DB
    
    def select_tool(self):
        """Выбирает случайный инструмент из базы"""
        import random
        return random.choice(self.tools)

# ============================================
# АГЕНТ 2: КОПИРАЙТЕР (пишет пост)
# ============================================

class CopywriterAgent:
    """Агент создает продающий пост для Telegram"""
    
    def __init__(self):
        self.llm = ChatGroq(
            model=GROQ_MODEL,
            api_key=GROQ_API_KEY,
            temperature=0.7
        )
    
    def generate_post(self, tool_info):
        """Генерирует текст поста"""
        
        prompt = ChatPromptTemplate.from_messages([
    ("system", """Ты пишешь посты для Telegram. Твой стиль — коротко, просто, по-человечески.

ПИШИ ТАК:
- Как будто советуешь другу в мессенджере
- Короткие предложения
- Простые слова (НЕ "преобразует", а "переводит"; НЕ "предлагает", а "даёт")
- БЕЗ общих фраз вроде "упрощает процесс", "облегчает работу"
- Сразу к делу: что это, что делает, зачем нужно

НЕ ПИШИ:
- "вам", "ваш" — обращайся нейтрально
- "помогает", "способствует", "обеспечивает"
- "высокая точность", "профессиональный уровень"
- Звёздочки ** — используй <b>жирный</b>

СТРУКТУРА:
<b>🎯 [Название] — [что делает в 3-5 словах]</b>

[1-2 предложения: что это]

<b>Фишки:</b>
• [функция 1]
• [функция 2]
• [функция 3]

[1 предложение: кому нужно]

👉 {referral_link}

✅ ПРИМЕР ХОРОШЕГО ПОСТА:
<b>🎬 Descript — редактор видео и подкастов</b>

Монтируешь видео как текст. Удаляешь слова в транскрипции — они исчезают из видео.

<b>Фишки:</b>
• Автоматическая расшифровка аудио и видео
• Монтаж через редактирование текста
• Готовые шаблоны озвучки

Для подкастеров и видеомейкеров

👉 https://descript.com

❌ ТАК НЕ ПИШИ:
"Помогает редактировать видео без необходимости иметь профессиональный опыт. Упрощает процесс создания контента."
(слишком официально, много воды)"""),
    
    ("user", """Инструмент: {name}
Категория: {category}
Что делает: {description}
Возможности: {features}

Напиши пост.""")
])
        
        chain = prompt | self.llm
        
        response = chain.invoke({
            "name": tool_info["name"],
            "category": tool_info["category"],
            "description": tool_info["description"],
            "features": ", ".join(tool_info.get("features", [])),
            "referral_link": REFERRAL_LINK
        })
        
        return response.content

# ============================================
# АГЕНТ 3: ВИЗУАЛ (генерирует картинку)
# ============================================

class VisualAgent:
    """Агент создает изображение через Pollinations.ai"""
    
    def generate_image(self, tool_name, category):
        """Генерирует URL изображения"""
        
        # Создаем промпт для генерации
        prompt = f"modern minimalist tech illustration of {tool_name} AI tool, {category}, blue and purple gradient, professional, clean design, 4k"
        
        # Кодируем промпт для URL
        import urllib.parse
        encoded_prompt = urllib.parse.quote(prompt)
        
        # Генерируем URL изображения (бесплатный сервис)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1080&nologo=true"
        
        return image_url
    
    def download_image(self, image_url, filename="temp_image.jpg"):
        """Скачивает изображение локально"""
        try:
            response = requests.get(image_url, timeout=10)
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                return filename
        except Exception as e:
            print(f"⚠️ Ошибка загрузки изображения: {e}")
        return None

# ============================================
# АГЕНТ 4: ПУБЛИКАТОР (отправляет в Telegram)
# ============================================

class PublisherAgent:
    """Агент публикует пост в Telegram"""
    
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    async def publish_post(self, text, image_path=None):
        """Публикует пост с текстом и опционально с изображением"""
        
        try:
            if image_path and os.path.exists(image_path):
                # Отправляем с фото
                with open(image_path, 'rb') as photo:
                    await self.bot.send_photo(
                        chat_id=TELEGRAM_CHANNEL_ID,
                        photo=photo,
                        caption=text,
                        parse_mode='HTML'
                    )
            else:
                # Отправляем только текст
                await self.bot.send_message(
                    chat_id=TELEGRAM_CHANNEL_ID,
                    text=text,
                    parse_mode='HTML'
                )
            
            print("✅ Пост успешно опубликован!")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка публикации: {e}")
            return False

# ============================================
# ОРКЕСТРАТОР (координирует агентов)
# ============================================

class AgentOrchestrator:
    """Координирует работу всех агентов"""
    
    def __init__(self):
        self.researcher = ResearcherAgent()
        self.copywriter = CopywriterAgent()
        self.visual = VisualAgent()
        self.publisher = PublisherAgent()
    
    async def run(self):
        """Запускает полный цикл создания и публикации поста"""
        
        print("\n🤖 Запуск мультиагентной системы...\n")
        
        # Шаг 1: Исследователь выбирает инструмент
        print("🔍 Агент-исследователь выбирает инструмент...")
        tool = self.researcher.select_tool()
        print(f"✅ Выбран инструмент: {tool['name']} ({tool['category']})\n")
        
        # Шаг 2: Копирайтер пишет пост
        print("✍️ Агент-копирайтер пишет пост...")
        post_text = self.copywriter.generate_post(tool)
        print(f"✅ Пост готов (длина: {len(post_text)} символов)\n")
        
        # Шаг 3: Визуал генерирует изображение
        print("🎨 Агент-визуал создает изображение...")
        image_url = self.visual.generate_image(tool['name'], tool['category'])
        image_path = self.visual.download_image(image_url)
        if image_path:
            print(f"✅ Изображение загружено: {image_path}\n")
        
        # Шаг 4: Публикатор отправляет в Telegram
        print("📤 Агент-публикатор отправляет пост...")
        success = await self.publisher.publish_post(post_text, image_path)
        
        # Удаляем временный файл
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        
        if success:
            print("\n🎉 Миссия выполнена! Пост опубликован.")
        else:
            print("\n⚠️ Пост не опубликован. Проверьте настройки бота.")
        
        return success

# ============================================
# ЗАПУСК СИСТЕМЫ
# ============================================

async def main():
    """Основная функция"""
    
    print("=" * 60)
    print("🚀 AI AFFILIATE AGENT - Мультиагентная система")
    print("=" * 60)
    print(f"📊 Канал: {TELEGRAM_CHANNEL_ID}")
    print(f"🤖 Модель: {GROQ_MODEL}")
    print(f"🔗 Реферальная ссылка: {REFERRAL_LINK}")
    print("=" * 60)
    
    orchestrator = AgentOrchestrator()
    await orchestrator.run()

if __name__ == "__main__":
    asyncio.run(main())