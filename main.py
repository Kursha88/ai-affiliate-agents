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
    raise ValueError("Missing required environment variables!")

# ============================================
# БАЗА ДАННЫХ ИИ-ИНСТРУМЕНТОВ (40 инструментов)
# ============================================

AI_TOOLS_DB = [
    {
        "name": "Notion AI",
        "description": "ИИ-помощник для заметок и организации работы",
        "category": "продуктивность",
        "features": ["автозаполнение", "суммаризация", "перевод", "генерация идей"]
    },
    {
        "name": "ChatGPT",
        "description": "Мощный ИИ-ассистент от OpenAI",
        "category": "универсальный",
        "features": ["чат", "генерация кода", "анализ текста", "ответы на вопросы"]
    },
    {
        "name": "Midjourney",
        "description": "Генератор изображений по текстовому описанию",
        "category": "творчество",
        "features": ["арт", "дизайн", "иллюстрации", "фотореализм"]
    },
    {
        "name": "Jasper AI",
        "description": "ИИ для копирайтинга и маркетинга",
        "category": "маркетинг",
        "features": ["тексты", "реклама", "SEO", "блог-посты"]
    },
    {
        "name": "Descript",
        "description": "ИИ для редактирования видео и подкастов",
        "category": "видео",
        "features": ["монтаж", "транскрибация", "озвучка", "удаление слов"]
    },
    {
        "name": "Leonardo AI",
        "description": "Продвинутый генератор артов и изображений",
        "category": "творчество",
        "features": ["3D", "концепт-арт", "аниме", "редактирование"]
    },
    {
        "name": "Copy.ai",
        "description": "ИИ для создания маркетингового контента",
        "category": "маркетинг",
        "features": ["посты", "email", "лендинги", "рекламные тексты"]
    },
    {
        "name": "Murf AI",
        "description": "ИИ-генератор реалистичной речи",
        "category": "аудио",
        "features": ["озвучка", "подкасты", "видео", "40+ голосов"]
    },
    {
        "name": "Pictory",
        "description": "Превращает текст в видео автоматически",
        "category": "видео",
        "features": ["текст в видео", "субтитры", "монтаж", "стоковые видео"]
    },
    {
        "name": "Runway ML",
        "description": "Профессиональный ИИ для видеомонтажа",
        "category": "видео",
        "features": ["удаление фона", "генерация видео", "эффекты", "ротоскопинг"]
    },
    {
        "name": "Synthesia",
        "description": "Создавай видео с ИИ-аватарами",
        "category": "видео",
        "features": ["ИИ-аватары", "120+ языков", "презентации", "обучение"]
    },
    {
        "name": "ElevenLabs",
        "description": "Лучший ИИ для клонирования голоса",
        "category": "аудио",
        "features": ["клонирование голоса", "озвучка", "29+ языков", "эмоции"]
    },
    {
        "name": "Grammarly",
        "description": "ИИ-помощник для проверки текста",
        "category": "письмо",
        "features": ["грамматика", "стиль", "тон", "плагиат"]
    },
    {
        "name": "Writesonic",
        "description": "ИИ для создания контента и статей",
        "category": "маркетинг",
        "features": ["статьи", "посты", "реклама", "SEO-оптимизация"]
    },
    {
        "name": "Canva AI",
        "description": "Дизайн с ИИ-инструментами",
        "category": "дизайн",
        "features": ["Magic Studio", "генерация изображений", "шаблоны", "редактирование"]
    },
    {
        "name": "GitHub Copilot",
        "description": "ИИ-помощник для программистов",
        "category": "код",
        "features": ["автодополнение", "генерация кода", "отладка", "20+ языков"]
    },
    {
        "name": "Replit AI",
        "description": "ИИ для разработки в браузере",
        "category": "код",
        "features": ["генерация кода", "отладка", "объяснение кода", "рефакторинг"]
    },
    {
        "name": "Framer AI",
        "description": "Создавай сайты с помощью ИИ",
        "category": "веб",
        "features": ["генерация сайтов", "дизайн", "анимации", "публикация"]
    },
    {
        "name": "Durable",
        "description": "ИИ-конструктор сайтов за 30 секунд",
        "category": "веб",
        "features": ["быстрый запуск", "CRM", "инвойсы", "маркетинг"]
    },
    {
        "name": "Loom AI",
        "description": "ИИ для записи и редактирования видео",
        "category": "видео",
        "features": ["запись экрана", "транскрибация", "суммаризация", "шаринг"]
    },
    {
        "name": "Otter.ai",
        "description": "Автоматическая транскрибация встреч",
        "category": "аудио",
        "features": ["транскрибация", "заметки", "поиск", "интеграции"]
    },
    {
        "name": "Beautiful.ai",
        "description": "ИИ для создания презентаций",
        "category": "презентации",
        "features": ["автодизайн", "шаблоны", "анимации", "экспорт"]
    },
    {
        "name": "Tome",
        "description": "Рассказывай истории с ИИ-презентациями",
        "category": "презентации",
        "features": ["генерация слайдов", "ИИ-изображения", "нарратив", "шаринг"]
    },
    {
        "name": "Gamma",
        "description": "Создавай презентации, документы и сайты",
        "category": "презентации",
        "features": ["презентации", "документы", "веб-страницы", "ИИ-генерация"]
    },
    {
        "name": "Perplexity AI",
        "description": "ИИ-поисковик с источниками",
        "category": "поиск",
        "features": ["поиск", "цитирование", "анализ", "копилот"]
    },
    {
        "name": "Claude",
        "description": "Продвинутый ИИ-ассистент от Anthropic",
        "category": "универсальный",
        "features": ["анализ текста", "код", "диалог", "100K контекст"]
    },
    {
        "name": "Bard (Gemini)",
        "description": "ИИ от Google с доступом в интернет",
        "category": "универсальный",
        "features": ["поиск", "генерация", "анализ", "интеграции Google"]
    },
    {
        "name": "Character.AI",
        "description": "Общайся с ИИ-персонажами",
        "category": "развлечения",
        "features": ["чат с персонажами", "ролевые игры", "обучение", "развлечение"]
    },
    {
        "name": "Stable Diffusion",
        "description": "Open-source генератор изображений",
        "category": "творчество",
        "features": ["генерация", "редактирование", "inpainting", "локальная установка"]
    },
    {
        "name": "DALL-E 3",
        "description": "Генератор изображений от OpenAI",
        "category": "творчество",
        "features": ["высокое качество", "понимание контекста", "текст на изображениях", "интеграция с ChatGPT"]
    },
    {
        "name": "InVideo AI",
        "description": "Создавай видео по текстовому описанию",
        "category": "видео",
        "features": ["текст в видео", "шаблоны", "озвучка", "монтаж"]
    },
    {
        "name": "Peech",
        "description": "ИИ для редактирования видео-контента",
        "category": "видео",
        "features": ["авто-нарезка", "субтитры", "брендинг", "публикация"]
    },
    {
        "name": "Podcastle",
        "description": "Студия подкастов с ИИ",
        "category": "аудио",
        "features": ["запись", "редактирование", "очистка звука", "транскрибация"]
    },
    {
        "name": "Krisp",
        "description": "ИИ для удаления шума в звонках",
        "category": "аудио",
        "features": ["шумоподавление", "эхо", "работает со всеми приложениями", "офлайн"]
    },
    {
        "name": "Fireflies.ai",
        "description": "ИИ-ассистент для встреч",
        "category": "продуктивность",
        "features": ["запись встреч", "транскрибация", "заметки", "поиск"]
    },
    {
        "name": "Reclaim AI",
        "description": "ИИ для планирования времени",
        "category": "продуктивность",
        "features": ["автопланирование", "привычки", "встречи", "интеграция с календарём"]
    },
    {
        "name": "Motion",
        "description": "ИИ-планировщик задач и календаря",
        "category": "продуктивность",
        "features": ["автопланирование", "приоритеты", "дедлайны", "календарь"]
    },
    {
        "name": "Lindy AI",
        "description": "Создавай ИИ-агентов без кода",
        "category": "автоматизация",
        "features": ["ИИ-агенты", "автоматизация", "интеграции", "no-code"]
    },
    {
        "name": "Zapier AI",
        "description": "Автоматизация с ИИ между приложениями",
        "category": "автоматизация",
        "features": ["интеграции", "автоматизация", "ИИ-помощник", "5000+ приложений"]
    },
    {
        "name": "Bardeen",
        "description": "Автоматизация рутинных задач",
        "category": "автоматизация",
        "features": ["скрейпинг", "автоматизация", "шаблоны", "интеграции"]
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
- Простые слова (НЕ "преобразует", а "переводит")
- БЕЗ общих фраз вроде "упрощает процесс", "облегчает работу"
- Сразу к делу: что это, что делает, зачем нужно

НЕ ПИШИ:
- "вам", "ваш" — обращайся нейтрально
- "помогает", "способствует", "обеспечивает"
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

"📢 Больше обзоров ИИ-инструментов: @{channel_username}"""),
            
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
            "referral_link": REFERRAL_LINK,
            "channel_username": "nejroavtomatizacia"  # ЗАМЕНИ на свой юзернейм канала
        })
        
        return response.content

# ============================================
# АГЕНТ 3: ВИЗУАЛ (генерирует картинку)
# ============================================

class VisualAgent:
    """Агент создает изображение через Pollinations.ai"""
    
    def generate_image(self, tool_name, category):
        """Генерирует URL изображения"""
        
        prompt = f"modern minimalist tech illustration of {tool_name} AI tool, {category}, blue and purple gradient, professional, clean design, 4k"
        
        import urllib.parse
        encoded_prompt = urllib.parse.quote(prompt)
        
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
# АГЕНТ 4: TELEGRAM ПУБЛИКАТОР
# ============================================

class PublisherAgent:
    """Агент публикует пост в Telegram"""
    
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    async def publish_post(self, text, image_path=None):
        """Публикует пост с текстом и опционально с изображением"""
        
        try:
            if image_path and os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    await self.bot.send_photo(
                        chat_id=TELEGRAM_CHANNEL_ID,
                        photo=photo,
                        caption=text,
                        parse_mode='HTML'
                    )
            else:
                await self.bot.send_message(
                    chat_id=TELEGRAM_CHANNEL_ID,
                    text=text,
                    parse_mode='HTML'
                )
            
            print("✅ Пост опубликован в Telegram!")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка публикации в Telegram: {e}")
            return False

# ============================================
# АГЕНТ 5: TWITTER ПУБЛИКАТОР (через Buffer)
# ============================================

class TwitterPublisherAgent:
    """Публикует посты в Twitter через Buffer API"""
    
    def publish_to_twitter(self, text):
        """Отправляет пост в Twitter через Buffer API"""
        
        buffer_token = os.environ.get("BUFFER_ACCESS_TOKEN")
        
        if not buffer_token:
            print("⚠️ BUFFER_ACCESS_TOKEN не найден, пропускаем Twitter")
            return False
        
        try:
            # Получаем ID профиля Twitter
            profiles_response = requests.get(
                "https://api.bufferapp.com/1/profiles.json",
                params={"access_token": buffer_token}
            )
            profiles = profiles_response.json()
            
            # Находим Twitter профиль
            twitter_profile_id = None
            for profile in profiles:
                if profile.get('service') == 'twitter':
                    twitter_profile_id = profile['id']
                    break
            
            if not twitter_profile_id:
                print("❌ Twitter профиль не найден в Buffer")
                return False
            
            # Публикуем пост
            post_data = {
                "text": text,
                "profile_ids[]": twitter_profile_id,
                "now": "true"
            }
            
            response = requests.post(
                "https://api.bufferapp.com/1/updates/create.json",
                data=post_data,
                params={"access_token": buffer_token}
            )
            
            if response.status_code == 200:
                print("✅ Пост опубликован в Twitter!")
                return True
            else:
                print(f"❌ Ошибка Twitter: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка Twitter API: {e}")
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
        self.twitter_publisher = TwitterPublisherAgent()
    
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
        
        # Шаг 4: Публикуем в Telegram
        print("📤 Агент-публикатор отправляет пост в Telegram...")
        tg_success = await self.publisher.publish_post(post_text, image_path)
        
        # Шаг 5: Публикуем в Twitter
        print("🐦 Агент-Twitter публикует пост...")
        twitter_success = self.twitter_publisher.publish_to_twitter(post_text)
        
        # Удаляем временный файл
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        
        if tg_success:
            print("\n✅ Пост опубликован в Telegram!")
        if twitter_success:
            print("🎉 Пост опубликован в Twitter!")
        
        return tg_success or twitter_success

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