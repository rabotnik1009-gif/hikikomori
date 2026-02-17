import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# TODO: замените на свой токен бота
BOT_TOKEN = "8447461008:AAFrXSPSzFLkRyqpXrebt4DiybZ5DFr2Ck0"

# Настройки API Kufar
KUFAR_API_URL = "https://api.kufar.by/search-api/v2/search/rendered-paginated"
SEARCH_QUERY = "hikikomori kai"
DAYS_BACK = 3

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class Database:
    """Класс для работы с SQLite базой данных"""
    
    def __init__(self, db_name: str = "sent_ads.db"):
        self.db_name = db_name
        self._init_db()
    
    def _init_db(self):
        """Инициализация таблицы в базе данных"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sent_ads (
                    ad_id TEXT PRIMARY KEY,
                    title TEXT,
                    price REAL,
                    link TEXT,
                    sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    
    def is_ad_sent(self, ad_id: str) -> bool:
        """Проверка, было ли объявление уже отправлено"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM sent_ads WHERE ad_id = ?", (ad_id,))
            return cursor.fetchone() is not None
    
    def save_ad(self, ad_id: str, title: str, price: float, link: str):
        """Сохранение отправленного объявления в базу"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO sent_ads (ad_id, title, price, link) VALUES (?, ?, ?, ?)",
                (ad_id, title, price, link)
            )
            conn.commit()
    
    def clean_old_records(self, days: int = 30):
        """Очистка старых записей (для экономии места)"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("DELETE FROM sent_ads WHERE sent_date < ?", (cutoff_date,))
            conn.commit()


class KufarAPI:
    """Класс для работы с API Kufar"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _build_params(self) -> Dict[str, Any]:
        """Формирование параметров запроса к API"""
        # Вычисляем дату для фильтрации (последние 3 дня)
        date_from = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        
        # Параметры запроса согласно документации Kufar API
        return {
            "query": SEARCH_QUERY,  # Поиск по тексту в заголовке
            "cat": 1010,  # Категория "Весь Kufar" (обычно 1010 для всех категорий)
            "size": 50,  # Количество результатов на странице
            "lang": "ru",  # Язык ответа
            "rgn": 1,  # Регион (1 - вся Беларусь)
            "cur": "USD",  # Валюта USD
            "prc": f"r:{date_from}",  # Фильтр по дате (r: - от определенной даты)
            "sort": "lst.d"  # Сортировка по дате (сначала новые)
        }
    
    async def search_ads(self) -> List[Dict[str, Any]]:
        """Поиск объявлений по заданным критериям"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        params = self._build_params()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Origin": "https://kufar.by",
            "Referer": "https://kufar.by/"
        }
        
        try:
            async with self.session.get(KUFAR_API_URL, params=params, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_ads(data)
                else:
                    logger.error(f"API вернул статус {response.status}")
                    return []
        except asyncio.TimeoutError:
            logger.error("Таймаут при запросе к API Kufar")
            return []
        except Exception as e:
            logger.error(f"Ошибка при запросе к API: {e}")
            return []
    
    def _parse_ads(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Парсинг JSON-ответа и извлечение нужных полей"""
        ads = []
        
        try:
            products = data.get("products", []) or data.get("ads", [])
            
            for product in products:
                # Получаем ID объявления
                ad_id = str(product.get("ad_id", "")) or str(product.get("id", ""))
                if not ad_id:
                    continue
                
                # Получаем заголовок
                title = product.get("subject", "") or product.get("title", "")
                
                # Получаем цену (уже в долларах, так как мы запросили cur=USD)
                price = product.get("price_usd") or product.get("price", {}).get("usd") or 0
                if isinstance(price, dict):
                    price = price.get("amount", 0)
                
                # Получаем ссылку
                link = product.get("ad_link", "") or f"https://kufar.by/item/{ad_id}"
                
                # Получаем первое фото (опционально)
                images = product.get("images", [])
                photo = images[0] if images else None
                
                ads.append({
                    "id": ad_id,
                    "title": title,
                    "price": float(price) if price else 0,
                    "link": link,
                    "photo": photo
                })
        except Exception as e:
            logger.error(f"Ошибка при парсинге ответа API: {e}")
        
        return ads


# Клавиатура с кнопкой "Чек хикикомори"
def get_main_keyboard() -> types.ReplyKeyboardMarkup:
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button = types.KeyboardButton("🔍 Чек хикикомори")
    keyboard.add(button)
    return keyboard


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    await message.answer(
        "👋 Привет! Я бот для отслеживания объявлений на Kufar по запросу 'hikikomori kai'.\n\n"
        "Нажми кнопку 'Чек хикикомори', чтобы найти новые объявления за последние 3 дня.",
        reply_markup=get_main_keyboard()
    )


@dp.message_handler(Text(equals="🔍 Чек хикикомори", ignore_case=True))
async def check_hikikomori(message: types.Message):
    """Обработчик нажатия на кнопку 'Чек хикикомори'"""
    await message.answer("🔍 Ищу новые объявления... Это может занять несколько секунд.")
    
    db = Database()
    # Очищаем старые записи (старше 30 дней)
    db.clean_old_records()
    
    try:
        async with KufarAPI() as api:
            ads = await api.search_ads()
        
        if not ads:
            await message.answer("😕 Не удалось найти объявления. Попробуйте позже.")
            return
        
        # Фильтруем только новые объявления
        new_ads = [ad for ad in ads if not db.is_ad_sent(ad["id"])]
        
        if not new_ads:
            await message.answer(
                "📭 Новых объявлений не найдено.\n"
                f"Всего найдено: {len(ads)} (все уже были показаны ранее)."
            )
            return
        
        # Отправляем каждое новое объявление
        sent_count = 0
        for ad in new_ads:
            try:
                await send_ad_to_user(message.chat.id, ad)
                db.save_ad(ad["id"], ad["title"], ad["price"], ad["link"])
                sent_count += 1
                # Небольшая задержка между сообщениями
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Ошибка при отправке объявления {ad['id']}: {e}")
        
        await message.answer(
            f"✅ Готово! Найдено {len(new_ads)} новых объявлений.\n"
            f"Отправлено: {sent_count}"
        )
        
    except Exception as e:
        logger.error(f"Общая ошибка при поиске: {e}")
        await message.answer("❌ Произошла ошибка при поиске. Попробуйте позже.")


async def send_ad_to_user(chat_id: int, ad: Dict[str, Any]):
    """Отправка объявления пользователю"""
    caption = (
        f"🆕 <b>Найдено объявление:</b>\n"
        f"📌 <b>Название:</b> {ad['title']}\n"
        f"💰 <b>Цена:</b> {ad['price']:.2f} $\n"
        f"🔗 <b>Ссылка:</b> {ad['link']}"
    )
    
    # Пробуем отправить с фото
    if ad.get("photo"):
        try:
            await bot.send_photo(chat_id, ad["photo"], caption=caption)
            return
        except Exception as e:
            logger.warning(f"Не удалось отправить фото: {e}")
    
    # Если фото нет или не удалось отправить, отправляем текстом
    await bot.send_message(chat_id, caption)


@dp.message_handler()
async def handle_unknown(message: types.Message):
    """Обработчик неизвестных команд"""
    await message.answer(
        "Я понимаю только команду /start и кнопку 'Чек хикикомори'.",
        reply_markup=get_main_keyboard()
    )


if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)