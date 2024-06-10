import re
import os
import sqlite3
import nltk
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from telethon import TelegramClient
from telethon.tl.types import Channel
from tqdm import tqdm
from nltk.corpus import wordnet
from nltk.stem import WordNetLemmatizer

# Импортируем местоположения из файла locations.py
from locations import locations

# Установка пути для NLTK данных
nltk_data_path = os.path.join(os.path.expanduser('~'), 'nltk_data')
nltk.data.path.append(nltk_data_path)

# Загрузка данных NLTK
nltk.download('punkt', download_dir=nltk_data_path)
nltk.download('wordnet', download_dir=nltk_data_path)

# Telegram Bot API токен
BOT_TOKEN = '7440949629:AAFMSCwhTqRwhpEo0WL0w9xSmgjV0Rh35EQ'

# Telegram API ID и API hash
api_id = '22221223'
api_hash = '4058ee4c1d29cb9b297866f63a3096df'
session_file = 'telegram_user_session'  # Используем тот же файл сессии

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера с использованием MemoryStorage
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=storage)

# Подключение к базе данных SQLite
conn = sqlite3.connect('telegram_news.db')
cursor = conn.cursor()

# Создание таблицы для хранения новостей
cursor.execute('''
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER UNIQUE,
    title TEXT,
    link TEXT,
    content TEXT,
    location TEXT,
    casualties TEXT
)
''')
conn.commit()

lemmatizer = WordNetLemmatizer()

# Определение состояний для FSM
class Form(StatesGroup):
    waiting_for_url = State()
    waiting_for_keywords = State()

# Функция для лемматизации ключевых слов
def lemmatize_keywords(keywords):
    return [lemmatizer.lemmatize(word.lower()) for word in keywords]

# Функция для лемматизации слова
def lemmatize_word(word):
    lemma = lemmatizer.lemmatize(word, wordnet.VERB)
    if lemma == word:
        lemma = lemmatizer.lemmatize(word, wordnet.NOUN)
    return lemma

# Функция для проверки наличия ключевых слов в тексте
def contains_keywords(text, keywords):
    words = nltk.word_tokenize(text.lower())
    lemmatized_words = [lemmatize_word(word) for word in words]
    logger.info(f"Лемматизированные слова: {lemmatized_words}")
    return any(keyword in lemmatized_words for keyword in keywords)

# Функция для извлечения информации из текста
def extract_information(text):
    location = None
    casualties_pattern = re.compile(r'(\d+)\s+(погибших|раненых|спасенных|жертв|пострадавших|убитых|раненных)')
    location_pattern = re.compile(r'[«"](.*?)[»"]')

    for loc, forms in locations.items():
        for form in forms:
            if form in text:
                location = loc
                break
        if location:
            break

    if location is None:  # Если местоположение не найдено, попробуем найти название места в кавычках
        match = location_pattern.search(text)
        if match:
            location = match.group(1)

    casualties_match = casualties_pattern.search(text)
    casualties = casualties_match.group(0) if casualties_match else None

    return location, casualties

# Функция для парсинга новостей
async def fetch_news(client, entity, keywords, user_id, limit=500):
    channel = entity
    progress_bar = tqdm(total=limit)

    try:
        async for message in client.iter_messages(channel, limit=limit):
            if message.message:
                if contains_keywords(message.message, keywords):
                    title = message.message.split('\n')[0]
                    link = f"https://t.me/{entity.username}/{message.id}" if entity.username else None
                    content = message.message
                    location, casualties = extract_information(content)

                    cursor.execute('''
                        INSERT OR IGNORE INTO news (message_id, title, link, content, location, casualties)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ''', (message.id, title, link, content, location, casualties))
                    conn.commit()

                    info_message = (
                        f"Новость сохранена:\n"
                        f"Заголовок: {title}\n"
                        f"Содержание: {content}\n"
                        f"Ссылка: {link}\n"
                        f"Местоположение: {location}\n"
                        f"Пострадавшие: {casualties}\n"
                        f"{'-' * 40}"
                    )

                    # Вывод информации в консоль
                    logger.info(info_message)

                    # Отправка информации пользователю
                    await bot.send_message(user_id, info_message)

                progress_bar.update(1)

                if progress_bar.n >= limit:
                    break

        progress_bar.close()

    except Exception as e:
        logger.error(f"Произошла ошибка при парсинге новостей: {str(e)}", exc_info=True)
        progress_bar.close()

    finally:
        await client.disconnect()  # Убедимся, что клиент всегда корректно завершает работу

# Функция для обработки URL
async def handle_url(url, keywords, user_id):
    client = TelegramClient(session_file, api_id, api_hash)
    await client.start()

    try:
        logger.info(f"Получен URL: {url}")
        entity = await client.get_entity(url)
        logger.info(f"Entity: {entity}")

        if isinstance(entity, Channel):
            logger.info(f"Начинаем парсинг канала: {entity.title}")
            await fetch_news(client, entity, keywords, user_id, limit=500)
        else:
            logger.error("Ошибка: это не публичный канал.")
            await bot.send_message(user_id, "Ошибка: это не публичный канал.")
            return
    except Exception as e:
        logger.error(f"Произошла ошибка: {str(e)}", exc_info=True)
        await bot.send_message(user_id, f"Произошла ошибка: {str(e)}")
    finally:
        await client.disconnect()

    await bot.send_message(user_id, "Парсинг завершен и данные сохранены в базе данных.")

# Хендлер для команды /start
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.reply("Привет! Отправь мне URL Telegram-канала, чтобы я мог начать парсинг новостей.")
    await Form.waiting_for_url.set()

# Хендлер для получения URL
@dp.message_handler(state=Form.waiting_for_url, content_types=types.ContentTypes.TEXT)
async def process_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    await state.update_data(url=url)
    await message.reply("Спасибо! Теперь отправь ключевые слова через запятую.")
    await Form.waiting_for_keywords.set()

# Хендлер для получения ключевых слов
@dp.message_handler(state=Form.waiting_for_keywords, content_types=types.ContentTypes.TEXT)
async def process_keywords(message: types.Message, state: FSMContext):
    keywords_text = message.text.strip()
    keywords = [keyword.strip() for keyword in keywords_text.split(',')]
    lemmatized_keywords = lemmatize_keywords(keywords)

    user_data = await state.get_data()
    url = user_data['url']

    await handle_url(url, lemmatized_keywords, message.from_user.id)
    await state.finish()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
