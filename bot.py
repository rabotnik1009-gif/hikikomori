import asyncio
import logging
import os
import sqlite3
import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
from aiogram.utils import executor
from aiogram.utils.callback_data import CallbackData

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Настройки API Kufar
KUFAR_API_URL = "https://api.kufar.by/search-api/v2/search/rendered-paginated"
ALT_KUFAR_API_URLS = [
    "https://api.kufar.by/search-api/v1/search/rendered-paginated",
    "https://cre-api.kufar.by/search-api/v2/search/rendered-paginated",
]


# Состояния для FSM
class SearchStates(StatesGroup):
    waiting_for_query = State()


class PaginationStates(StatesGroup):
    browsing_results = State()


# Поисковые запросы
SEARCH_QUERIES = {
    "hikikomori": "hikikomori kai",
    "bladnes": "bladnes",
    "redan": "редан",
    "ryodan": "ryodan",
    "zxcursed": "zxcursed",
    "shadowraze": "shadowraze",
    "holy_sinner": "holy sinner",
    "neform": "нефор",
    "cvrsxdcrown": "cvrsxdcrown",
    "hatred888": "hatred888",
    "hikinight": "hikinight",
    "enemy_in_reflection": "enemy in reflection",
    "enemy": "enemy",
    "conjunctiva": "conjunctiva",
    "convulsive": "convulsive",
    "hikkomori_kai": "хикикомори кай",
    "ethereal": "ethereal",
    "double_minded": "double minded",
    "kusakabe": "kusakabe",
    "sheydov": "sheydov"
}

# Отображение названий для кнопок
BUTTON_NAMES = {
    "hikikomori": "Хикикомори Кай",
    "bladnes": "Бладнес",
    "redan": "Редан",
    "ryodan": "Ryodan",
    "zxcursed": "Zxcursed",
    "shadowraze": "Shadowraze",
    "holy_sinner": "Holy Sinner",
    "neform": "Нефор",
    "cvrsxdcrown": "Cvrsxdcrown",
    "hatred888": "Hatred888",
    "hikinight": "Hikinight",
    "enemy_in_reflection": "Enemy in Reflection",
    "enemy": "Enemy",
    "conjunctiva": "Conjunctiva",
    "convulsive": "Convulsive",
    "hikkomori_kai": "Хикикомори Кай (рус)",
    "ethereal": "Ethereal",
    "double_minded": "Double Minded",
    "kusakabe": "Kusakabe",
    "sheydov": "Sheydov"
}

# Кастомные обложки для брендов
BRAND_IMAGES = {
    "Хикикомори Кай": "🖤",
    "Хикикомори Кай (рус)": "🖤",
    "Бладнес": "🖤",
    "Редан": "🖤",
    "Ryodan": "🖤",
    "Zxcursed": "🖤",
    "Shadowraze": "🖤",
    "Holy Sinner": "🖤",
    "Нефор": "🖤",
    "Cvrsxdcrown": "🖤",
    "Hatred888": "🖤",
    "Hikinight": "🖤",
    "Conjunctiva": "🖤",
    "Convulsive": "🖤",
    "Ethereal": "🖤",
    "Double Minded": "🖤",
    "Kusakabe": "🖤",
    "Sheydov": "🖤",
    "Enemy in Reflection": "🪞",
    "Enemy": "👿"
}

DAYS_BACK = 10
LAST_24H_HOURS = 1
USD_TO_BYN = 3.2
MAX_MESSAGE_LENGTH = 3500
ITEMS_PER_PAGE = 10  # Для пагинации

# Расширенный список интересных фактов о Kufar
KUFAR_FACTS = [
    "📊 На Kufar ежедневно публикуется более 10 000 объявлений",
    "🏷️ Самая популярная категория — 'Одежда и обувь'",
    "💬 Пользователи Kufar отправляют 50 000 сообщений в день",
    "📱 Мобильное приложение Kufar скачали 2 млн раз",
    "⭐️ Средняя оценка приложения — 4.8",
    "🕒 Пик активности на Kufar — с 19:00 до 22:00",
    "💰 Средняя цена товара на Kufar — 75 BYN",
    "🌍 Kufar работает по всей Беларуси",
    "🔄 Каждую минуту на Kufar появляется 7 новых объявлений",
    "👥 Ежемесячная аудитория Kufar — 3 миллиона человек",
    "🏆 Самый дорогой товар на Kufar стоил 50 000 BYN",
    "🎁 Самая популярная категория подарков — 'Детские товары'",
    "📦 В день продается более 5 000 товаров",
    "🔍 Самый популярный поисковый запрос — 'iPhone'",
    "💎 Редкие бренды ищут в 3 раза чаще обычных",
    "🚚 Бесплатная доставка — самый частый фильтр",
    "⭐️ Топ-продавцы имеют рейтинг 4.9 и выше",
    "📈 Трафик Kufar вырос на 30% за последний год",
    "🎯 Точность поиска на Kufar — 95%",
    "💼 Бизнес-аккаунты приносят 40% всех продаж"
]

# Анимационные смайлики для загрузки
LOADING_EMOJIS = ["⏳", "⌛️", "⏳", "⌛️", "⏳", "⌛️", "⏳", "⌛️"]

# Callback данные для статистики и пагинации
stats_cb = CallbackData("stats", "query_key")
pagination_cb = CallbackData("page", "action", "page_num")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

search_cb = CallbackData("search", "query_key")
recent_cb = CallbackData("recent", "action")
custom_search_cb = CallbackData("custom", "action")


class Database:

    def __init__(self, db_name: str = "sent_ads.db"):
        self.db_name = db_name
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sent_ads (
                    ad_id TEXT PRIMARY KEY,
                    title TEXT,
                    price REAL,
                    link TEXT,
                    search_query TEXT,
                    sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def is_ad_sent(self, ad_id: str) -> bool:
        return False

    def save_ad(self,
                ad_id: str,
                title: str,
                price: float,
                link: str,
                search_query: str = ""):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO sent_ads (ad_id, title, price, link, search_query) VALUES (?, ?, ?, ?, ?)",
                (ad_id, title, price, link, search_query))
            conn.commit()

    def clean_old_records(self, days: int = 30):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cutoff_date = (datetime.now() -
                           timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("DELETE FROM sent_ads WHERE sent_date < ?",
                           (cutoff_date, ))
            conn.commit()


class KufarAPI:

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def search_ads(self,
                         search_query: str,
                         days_back: int = DAYS_BACK) -> List[Dict[str, Any]]:
        if not self.session:
            self.session = aiohttp.ClientSession()

        headers = {
            "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Origin": "https://kufar.by",
            "Referer": "https://kufar.by/",
        }

        all_ads = []

        for url in [KUFAR_API_URL] + ALT_KUFAR_API_URLS:
            try:
                params = {
                    "query": search_query,
                    "size": 100,
                    "lang": "ru",
                    "sort": "lst.d"
                }
                logger.info(
                    f"📡 Запрос к API: {url} для запроса '{search_query}'")
                logger.info(f"📋 Параметры запроса: {params}")

                async with self.session.get(url,
                                            params=params,
                                            headers=headers,
                                            timeout=10) as response:
                    logger.info(f"📊 Статус ответа: {response.status}")

                    if response.status == 200:
                        data = await response.json()

                        debug_file = f'kufar_debug_{search_query}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        logger.info(
                            f"💾 Ответ API сохранен в файл: {debug_file}")

                        ads = self._parse_ads(data, search_query)
                        all_ads.extend(ads)
                        logger.info(
                            f"✅ Получено {len(ads)} объявлений от API для запроса '{search_query}'"
                        )
                        break
                    else:
                        logger.warning(f"⚠️ Ошибка {response.status} от API")
            except Exception as e:
                logger.warning(f"❌ Ошибка при запросе к {url}: {e}")

        cutoff_date = datetime.now() - timedelta(days=days_back)
        filtered_ads = []

        logger.info("=" * 50)
        logger.info(
            f"📅 ФИЛЬТРАЦИЯ ПО ДАТЕ для запроса '{search_query}' (за {days_back} дн.)"
        )
        logger.info(
            f"📅 Текущая дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(
            f"📅 Показываем объявления новее чем: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.info("=" * 50)

        for ad in all_ads:
            if "date" in ad:
                ad_date = ad["date"]
                logger.info(f"\n📦 Объявление: {ad['title']}")
                logger.info(f"   🆔 ID: {ad['id']}")
                logger.info(
                    f"   📅 Дата публикации (UTC): {ad_date.strftime('%Y-%m-%d %H:%M:%S')}"
                )

                if ad_date >= cutoff_date:
                    filtered_ads.append(ad)
                    logger.info(f"   ✅ ПРОПУСКАЕМ (новее {days_back} дн.)")
                else:
                    days_old = (datetime.now() - ad_date).days
                    logger.info(
                        f"   ❌ ИСКЛЮЧАЕМ (старше {days_back} дн., точно {days_old} дн.)"
                    )
            else:
                logger.info(f"\n📦 Объявление: {ad['title']}")
                logger.info(f"   ⚠️ Нет даты публикации, показываем")
                filtered_ads.append(ad)

        logger.info("=" * 50)
        logger.info(
            f"📊 ИТОГ для '{search_query}': Всего объявлений: {len(all_ads)}")
        logger.info(f"📊 После фильтрации по дате: {len(filtered_ads)}")
        logger.info("=" * 50)

        return filtered_ads

    async def search_all_ads_recent(self) -> List[Dict[str, Any]]:
        all_results = []

        for query_key, search_query in SEARCH_QUERIES.items():
            try:
                ads = await self.search_ads(search_query,
                                            days_back=LAST_24H_HOURS)
                for ad in ads:
                    ad["search_query_display"] = BUTTON_NAMES.get(
                        query_key, query_key)
                all_results.extend(ads)
                logger.info(
                    f"✅ Для '{search_query}' найдено {len(ads)} объявлений за 24ч"
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при поиске '{search_query}': {e}")

        all_results.sort(key=lambda x: x.get("date", datetime.min),
                         reverse=True)
        return all_results

    def _parse_ads(self, data: Dict[str, Any],
                   search_query: str) -> List[Dict[str, Any]]:
        ads = []
        try:
            products = data.get("ads", []) or data.get("products", [])
            logger.info(f"🔍 Найдено продуктов в ответе: {len(products)}")

            for i, product in enumerate(products):
                if not isinstance(product, dict):
                    continue

                title = product.get("subject", "") or product.get(
                    "title", "") or product.get("name", "")

                if search_query.lower() not in title.lower():
                    continue

                ad_id = str(product.get("ad_id", "")) or str(
                    product.get("id", "")) or str(product.get("item_id", ""))
                if not ad_id:
                    continue

                ad_date = None

                if "list_time" in product:
                    list_time = product["list_time"]
                    if isinstance(list_time, str):
                        try:
                            list_time = list_time.replace('Z', '')
                            ad_date = datetime.fromisoformat(list_time)
                            logger.info(
                                f"📅 Найдена дата в list_time: {list_time}")
                        except Exception as e:
                            logger.warning(
                                f"⚠️ Ошибка парсинга list_time {list_time}: {e}"
                            )

                if not ad_date and "date" in product:
                    try:
                        date_str = product["date"].replace('Z', '')
                        ad_date = datetime.fromisoformat(date_str)
                        logger.info(f"📅 Найдена дата в date: {date_str}")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка парсинга date: {e}")

                if not ad_date and "published_at" in product:
                    try:
                        date_str = product["published_at"].replace('Z', '')
                        ad_date = datetime.fromisoformat(date_str)
                        logger.info(
                            f"📅 Найдена дата в published_at: {date_str}")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка парсинга published_at: {e}")

                price = 0
                if "price_byn" in product:
                    price = float(product["price_byn"]) / 100
                elif "price" in product:
                    if isinstance(product["price"], dict):
                        price_val = product["price"].get(
                            "byn", 0) or product["price"].get("amount", 0)
                        if price_val:
                            price = float(price_val) / 100
                    else:
                        price = float(product["price"]) / 100

                if price == 0 and "price_usd" in product:
                    price = (float(product["price_usd"]) * USD_TO_BYN) / 100

                link = product.get("ad_link", "") or product.get("url", "")
                if not link and ad_id:
                    link = f"https://kufar.by/item/{ad_id}"

                ad_data = {
                    "id": ad_id,
                    "title": title,
                    "price": float(price) if price else 0,
                    "link": link,
                    "search_query": search_query
                }

                if ad_date:
                    ad_data["date"] = ad_date

                ads.append(ad_data)
                logger.info(
                    f"✅ Добавлено: {title} (ID: {ad_id}) для запроса '{search_query}', цена: {price} BYN"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}", exc_info=True)

        logger.info(
            f"📊 Всего распаршено объявлений для '{search_query}': {len(ads)}")
        return ads


def format_price(price: float) -> str:
    """Форматирует цену, обрабатывая договорную"""
    if price == 0:
        return "💰 <b>Цена:</b> Договорная"
    elif price < 50:
        return f"🟢 {price:.2f} BYN"
    elif price < 100:
        return f"🟡 {price:.2f} BYN"
    else:
        return f"🔴 {price:.2f} BYN"


def get_brand_icon(brand_name: str) -> str:
    """Получить иконку для бренда"""
    return BRAND_IMAGES.get(brand_name, "🖤")


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру главного меню"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    sorted_buttons = sorted(BUTTON_NAMES.items(), key=lambda x: x[1])

    buttons = []
    for key, name in sorted_buttons:
        icon = get_brand_icon(name)
        buttons.append(
            InlineKeyboardButton(text=f"{icon} {name}",
                                 callback_data=search_cb.new(query_key=key)))

    keyboard.add(*buttons)

    # Добавляем кнопки в нижней части
    keyboard.add(
        InlineKeyboardButton(
            text="🔍 Поиск по своему запросу",
            callback_data=custom_search_cb.new(action="start")))
    keyboard.add(
        InlineKeyboardButton(text="📱 Последние объявления (24ч)",
                             callback_data=recent_cb.new(action="show")))
    keyboard.add(
        InlineKeyboardButton(text="📊 Статистика по брендам",
                             callback_data=stats_cb.new(query_key="all")))

    return keyboard


def get_stats_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для статистики"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    sorted_buttons = sorted(BUTTON_NAMES.items(), key=lambda x: x[1])

    buttons = []
    for key, name in sorted_buttons:
        icon = get_brand_icon(name)
        buttons.append(
            InlineKeyboardButton(text=f"{icon} {name}",
                                 callback_data=stats_cb.new(query_key=key)))

    keyboard.add(*buttons)
    keyboard.add(
        InlineKeyboardButton(text="◀️ Назад в меню",
                             callback_data="back_to_menu"))
    return keyboard


def get_pagination_keyboard(page_num: int,
                            total_pages: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для пагинации"""
    keyboard = InlineKeyboardMarkup(row_width=3)

    nav_buttons = []
    if page_num > 1:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️",
                                 callback_data=pagination_cb.new(
                                     action="prev", page_num=page_num - 1)))

    nav_buttons.append(
        InlineKeyboardButton(text=f"{page_num}/{total_pages}",
                             callback_data="noop"))

    if page_num < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(text="▶️",
                                 callback_data=pagination_cb.new(
                                     action="next", page_num=page_num + 1)))

    keyboard.row(*nav_buttons)
    keyboard.add(
        InlineKeyboardButton(text="◀️ Выбрать другой бренд",
                             callback_data="back_to_menu"))
    return keyboard


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой назад"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(text="◀️ Назад в меню",
                             callback_data="back_to_menu"))
    return keyboard


async def delete_previous_messages(chat_id: int, current_message_id: int):
    """Удаляет все предыдущие сообщения в чате (включая пользовательские)"""
    try:
        deleted_count = 0
        # Пытаемся удалить последние 20 сообщений
        for msg_id in range(current_message_id - 20, current_message_id):
            if msg_id > 0:
                try:
                    await bot.delete_message(chat_id, msg_id)
                    deleted_count += 1
                except Exception:
                    pass
        if deleted_count > 0:
            logger.info(f"🧹 Очищено {deleted_count} старых сообщений")
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке: {e}")


def format_ad_text(ad: Dict[str, Any],
                   index: int,
                   show_source: bool = False) -> str:
    """Форматирует текст объявления"""
    date_str = ""
    if "date" in ad:
        msk_date = ad["date"] + timedelta(hours=3)
        date_str = f"📅 {msk_date.strftime('%d.%m.%Y %H:%M')} МСК\n"

    source_str = ""
    if show_source and "search_query_display" in ad:
        source_str = f"🏷️ <b>Бренд:</b> {ad['search_query_display']}\n"

    # Используем новую функцию format_price
    price_text = format_price(ad['price'])

    ad_text = (f"<b>{index}. {ad['title']}</b>\n"
               f"{source_str}"
               f"{date_str}"
               f"{price_text}\n"
               f"🔗 <a href='{ad['link']}'>Ссылка на объявление</a>\n\n")

    return ad_text


async def update_message_with_results(message: types.Message,
                                      state: FSMContext,
                                      ads: List[Dict[str, Any]],
                                      title: str,
                                      show_source: bool = False,
                                      page: int = 1):
    """Обновляет сообщение с результатами поиска (с поддержкой пагинации через FSM)"""

    if not ads:
        await state.finish()
        await message.edit_text(
            f"📭 <b>Нет объявлений по запросу '{title}'</b>\n\n"
            f"за последние {DAYS_BACK} дней.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML)
        return

    # Рассчитываем пагинацию
    total_pages = (len(ads) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if page > total_pages:
        page = total_pages
    if page < 1:
        page = 1

    # Сохраняем данные в FSM
    async with state.proxy() as data:
        data['ads'] = ads
        data['title'] = title
        data['show_source'] = show_source
        data['total_pages'] = total_pages

    await PaginationStates.browsing_results.set()

    # Получаем объявления для текущей страницы
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, len(ads))
    current_page_ads = ads[start_idx:end_idx]

    # Формируем заголовок
    full_text = (f"🔍 <b>Результаты поиска: {title}</b>\n"
                 f"📊 <b>Всего найдено:</b> {len(ads)}\n"
                 f"📄 <b>Страница {page}/{total_pages}</b>\n"
                 f"{'═' * 30}\n\n")

    # Добавляем объявления текущей страницы
    for i, ad in enumerate(current_page_ads, start=start_idx + 1):
        full_text += format_ad_text(ad, i, show_source)

    full_text += f"{'═' * 30}\n◀️ <b>Выберите действие:</b>"

    # Отправляем сообщение с клавиатурой пагинации
    await message.edit_text(full_text,
                            reply_markup=get_pagination_keyboard(
                                page, total_pages),
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True)


@dp.callback_query_handler(pagination_cb.filter(),
                           state=PaginationStates.browsing_results)
async def process_pagination(callback_query: CallbackQuery,
                             callback_data: dict, state: FSMContext):
    """Обработчик переключения страниц"""
    page_num = int(callback_data["page_num"])

    async with state.proxy() as data:
        ads = data.get('ads', [])
        title = data.get('title', 'Результаты')
        show_source = data.get('show_source', False)

    if not ads:
        await callback_query.answer("Данные устарели, начните поиск заново",
                                    show_alert=True)
        await state.finish()
        return

    await callback_query.answer()
    await update_message_with_results(callback_query.message,
                                      state,
                                      ads,
                                      title,
                                      show_source=show_source,
                                      page=page_num)


async def calculate_brand_statistics(search_query: str) -> Dict[str, Any]:
    """Рассчитывает статистику по бренду"""
    async with KufarAPI() as api:
        ads = await api.search_ads(search_query, days_back=30
                                   )  # Ищем за 30 дней для статистики

    if not ads:
        return {
            "total": 0,
            "week": 0,
            "avg_price": 0,
            "max_price": 0,
            "min_price": 0
        }

    # Фильтруем за неделю
    week_ago = datetime.now() - timedelta(days=7)
    week_ads = [ad for ad in ads if ad.get("date", datetime.min) >= week_ago]

    prices = [ad["price"] for ad in ads if ad["price"] > 0]

    stats = {
        "total": len(ads),
        "week": len(week_ads),
        "avg_price": sum(prices) / len(prices) if prices else 0,
        "max_price": max(prices) if prices else 0,
        "min_price": min(prices) if prices else 0
    }

    return stats


@dp.callback_query_handler(stats_cb.filter())
async def process_stats_callback(callback_query: CallbackQuery,
                                 callback_data: dict):
    """Обработчик статистики"""
    query_key = callback_data["query_key"]

    await callback_query.answer()

    if query_key == "all":
        # Показываем список брендов для статистики
        await callback_query.message.edit_text(
            "📊 <b>Выберите бренд для просмотра статистики:</b>\n\n"
            "Нажмите на любой бренд, чтобы увидеть детальную информацию.",
            reply_markup=get_stats_keyboard(),
            parse_mode=ParseMode.HTML)
        return

    # Получаем статистику для конкретного бренда
    search_query = SEARCH_QUERIES.get(query_key, query_key)
    button_name = BUTTON_NAMES.get(query_key, query_key)
    icon = get_brand_icon(button_name)

    await callback_query.message.edit_text(
        f"📊 <b>Анализирую данные для {icon} {button_name}...</b>\n\n"
        f"⏳ <i>Это может занять несколько секунд</i>",
        parse_mode=ParseMode.HTML)

    try:
        stats = await calculate_brand_statistics(search_query)

        if stats["total"] == 0:
            stats_text = (f"📊 <b>Статистика для {icon} {button_name}</b>\n\n"
                          f"❌ Нет данных за последние 30 дней")
        else:
            stats_text = (
                f"📊 <b>Статистика для {icon} {button_name}</b>\n\n"
                f"📦 <b>Всего объявлений:</b> {stats['total']}\n"
                f"📅 <b>За неделю:</b> {stats['week']}\n"
                f"💰 <b>Средняя цена:</b> {format_price(stats['avg_price'])}\n"
                f"🏆 <b>Самое дорогое:</b> {format_price(stats['max_price'])}\n"
                f"🎁 <b>Самое дешевое:</b> {format_price(stats['min_price'])}\n\n"
                f"📊 <i>Статистика за последние 30 дней</i>")

        # Добавляем кнопки
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton(text="◀️ Назад к списку брендов",
                                 callback_data=stats_cb.new(query_key="all")))
        keyboard.add(
            InlineKeyboardButton(text="🏠 Главное меню",
                                 callback_data="back_to_menu"))

        await callback_query.message.edit_text(stats_text,
                                               reply_markup=keyboard,
                                               parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"❌ Ошибка при расчете статистики: {e}", exc_info=True)
        await callback_query.message.edit_text(
            f"❌ <b>Произошла ошибка при расчете статистики</b>\n\n"
            f"Попробуйте позже.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML)


# ==================== УЛУЧШЕННАЯ ПАРАЛЛЕЛЬНАЯ АНИМАЦИЯ ====================
async def show_parallel_animation(message: types.Message, button_name: str,
                                  search_task):
    """
    Улучшенная анимация с максимально частым обновлением (каждые 0.5 сек)
    и случайными фактами (с новыми смайликами)
    """
    start_time = time.time()
    last_fact_change = time.time()
    current_fact = random.choice(KUFAR_FACTS)
    update_count = 0

    # Анимируем, пока не завершится поиск
    while not search_task.done():
        current_time = time.time()
        elapsed = int(current_time - start_time)

        # Меняем анимационный смайлик часто (каждые 0.5 сек)
        loading_emoji = LOADING_EMOJIS[update_count % len(LOADING_EMOJIS)]
        update_count += 1

        # Меняем факт каждые 7 секунд
        if current_time - last_fact_change > 7:
            current_fact = random.choice(KUFAR_FACTS)
            last_fact_change = current_time

        # Формируем сообщение с анимацией
        animation_text = (f"🔍 <b>Поиск: {button_name}</b>\n\n"
                          f"{loading_emoji} <i>Ищем на Kufar...</i>\n"
                          f"⏱️ <b>Прошло:</b> {elapsed} сек.\n\n"
                          f"📌 <b>Знаете ли вы?</b>\n"
                          f"{current_fact}")

        try:
            await message.edit_text(animation_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            # Игнорируем ошибки редактирования
            pass

        # Максимально частая пауза (0.5 сек) - Telegram допускает
        await asyncio.sleep(0.5)

    # Поиск завершен - показываем финальное сообщение
    elapsed = int(time.time() - start_time)
    await message.edit_text(
        f"🔍 <b>Поиск: {button_name}</b>\n\n"
        f"✅ <b>Поиск завершен за {elapsed} сек.!</b>\n"
        f"⏳ Загружаю результаты...",
        parse_mode=ParseMode.HTML)


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    """Главное меню при старте"""
    await message.answer("🔄 Обновляю меню...",
                         reply_markup=ReplyKeyboardRemove())

    welcome_text = ("👋 <b>Добро пожаловать в Kufar Search Bot!</b>\n\n"
                    "🎯 <b>Что я умею:</b>\n"
                    "• Искать объявления на Kufar по разным брендам\n"
                    "• Показывать только свежие объявления (до 10 дней)\n"
                    "• Отображать цену в BYN\n"
                    "• Показывать время по МСК\n"
                    "• Статистика по каждому бренду\n"
                    "• Цветное форматирование цен\n"
                    "• Пагинация результатов\n\n"
                    "📌 <b>Выберите действие:</b>")

    sent_message = await message.answer(welcome_text,
                                        reply_markup=get_main_menu_keyboard(),
                                        parse_mode=ParseMode.HTML)
    await delete_previous_messages(message.chat.id, sent_message.message_id)


@dp.message_handler(commands=["menu"])
async def cmd_menu(message: types.Message):
    """Показывает главное меню"""
    sent_message = await message.answer("📌 <b>Выберите действие:</b>",
                                        reply_markup=get_main_menu_keyboard(),
                                        parse_mode=ParseMode.HTML)
    await delete_previous_messages(message.chat.id, sent_message.message_id)


@dp.callback_query_handler(text="back_to_menu", state="*")
async def process_back_to_menu(callback_query: CallbackQuery,
                               state: FSMContext):
    """Возвращает пользователя в главное меню"""
    await state.finish()
    await callback_query.answer()

    welcome_text = ("👋 <b>Добро пожаловать в Kufar Search Bot!</b>\n\n"
                    "🎯 <b>Что я умею:</b>\n"
                    "• Искать объявления на Kufar по разным брендам\n"
                    "• Показывать только свежие объявления (до 10 дней)\n"
                    "• Отображать цену в BYN\n"
                    "• Показывать время по МСК\n"
                    "• Статистика по каждому бренду\n"
                    "• Цветное форматирование цен\n"
                    "• Пагинация результатов\n\n"
                    "📌 <b>Выберите действие:</b>")

    await callback_query.message.edit_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.HTML)
    await delete_previous_messages(callback_query.message.chat.id,
                                   callback_query.message.message_id)


@dp.callback_query_handler(search_cb.filter())
async def process_search_callback(callback_query: CallbackQuery,
                                  callback_data: dict, state: FSMContext):
    query_key = callback_data["query_key"]
    search_query = SEARCH_QUERIES.get(query_key, query_key)
    button_name = BUTTON_NAMES.get(query_key, query_key)

    await callback_query.answer()

    # Показываем начальное сообщение
    await callback_query.message.edit_text(
        f"🔍 <b>Поиск: {button_name}</b>\n\n"
        f"⏳ <i>Запускаем поиск...</i>",
        parse_mode=ParseMode.HTML)

    try:
        # Запускаем реальный поиск в фоне
        api = KufarAPI()
        await api.__aenter__()
        search_task = asyncio.create_task(api.search_ads(search_query))

        # Параллельно показываем улучшенную анимацию
        await show_parallel_animation(callback_query.message, button_name,
                                      search_task)

        # Получаем результат поиска
        ads = await search_task
        await api.__aexit__(None, None, None)

        # Обновляем сообщение с результатами (первая страница)
        await update_message_with_results(callback_query.message,
                                          state,
                                          ads,
                                          button_name,
                                          show_source=False,
                                          page=1)

    except Exception as e:
        logger.error(f"❌ Общая ошибка: {e}", exc_info=True)
        await callback_query.message.edit_text(
            f"❌ <b>Произошла ошибка при поиске</b>\n\n"
            f"Попробуйте позже или проверьте вручную:\n"
            f"https://www.kufar.by/l?ot=1&query={search_query.replace(' ', '%20')}&sort=lst.d\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Выберите действие:</b>",
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML)


@dp.callback_query_handler(recent_cb.filter(action="show"))
async def process_recent_callback(callback_query: CallbackQuery,
                                  state: FSMContext):
    await callback_query.answer()

    await callback_query.message.edit_text(
        "🔍 <b>Поиск: все бренды за 24ч</b>\n\n"
        "⏳ <i>Запускаем поиск...</i>",
        parse_mode=ParseMode.HTML)

    try:
        # Запускаем реальный поиск в фоне
        api = KufarAPI()
        await api.__aenter__()
        search_task = asyncio.create_task(api.search_all_ads_recent())

        # Параллельно показываем улучшенную анимацию
        await show_parallel_animation(callback_query.message,
                                      "все бренды за 24ч", search_task)

        # Получаем результат поиска
        ads = await search_task
        await api.__aexit__(None, None, None)

        # Обновляем сообщение с результатами (первая страница)
        await update_message_with_results(callback_query.message,
                                          state,
                                          ads,
                                          "Свежие за 24ч",
                                          show_source=True,
                                          page=1)

    except Exception as e:
        logger.error(f"❌ Ошибка при поиске всех объявлений: {e}",
                     exc_info=True)
        await callback_query.message.edit_text(
            f"❌ <b>Произошла ошибка при поиске</b>\n\n"
            f"Попробуйте позже.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Выберите действие:</b>",
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML)


@dp.callback_query_handler(custom_search_cb.filter(action="start"))
async def process_custom_search_start(callback_query: CallbackQuery,
                                      state: FSMContext):
    """Начало кастомного поиска"""
    await callback_query.answer()

    logger.info("🔍 Начало кастомного поиска")

    # Устанавливаем состояние ожидания запроса
    await SearchStates.waiting_for_query.set()

    # Сохраняем ID сообщения для последующего обновления
    async with state.proxy() as data:
        data['message_id'] = callback_query.message.message_id
        data['chat_id'] = callback_query.message.chat.id

    # Показываем красивое приглашение к вводу
    search_prompt = ("🔍 <b>Поиск по своему запросу</b>\n\n"
                     "📝 <b>Как это работает:</b>\n"
                     "• Введите любой бренд, модель или ключевое слово\n"
                     "• Я покажу объявления за последние 10 дней\n"
                     "• Можно вводить на русском или английском\n"
                     "• Покажу статистику по вашему запросу\n\n"
                     "✨ <b>Примеры запросов:</b>\n"
                     "• <code>nike air max</code>\n"
                     "• <code>iphone 13</code>\n"
                     "• <code>дизель джинсы</code>\n\n"
                     "⬇️ <b>Введите ваш запрос ниже:</b>")

    await callback_query.message.edit_text(search_prompt,
                                           reply_markup=get_back_keyboard(),
                                           parse_mode=ParseMode.HTML)


@dp.message_handler(state=SearchStates.waiting_for_query,
                    content_types=types.ContentTypes.TEXT)
async def process_custom_search_query(message: types.Message,
                                      state: FSMContext):
    """Обработка введенного запроса"""

    search_query = message.text.strip()
    logger.info(f"📝 Получен запрос от пользователя: '{search_query}'")

    if not search_query:
        await message.answer(
            "❌ <b>Пустой запрос</b>\n\n"
            "Пожалуйста, введите текст для поиска.",
            reply_markup=get_back_keyboard(),
            parse_mode=ParseMode.HTML)
        return

    # Получаем сохраненные данные
    async with state.proxy() as data:
        original_message_id = data.get('message_id')
        chat_id = data.get('chat_id')

    logger.info(
        f"📦 Оригинальное сообщение ID: {original_message_id}, Chat ID: {chat_id}"
    )

    # Завершаем состояние
    await state.finish()

    # Удаляем сообщение с запросом пользователя (для чистоты)
    await message.delete()

    # Получаем оригинальное сообщение для обновления
    try:
        original_message = await bot.edit_message_text(
            chat_id=chat_id,
            message_id=original_message_id,
            text=f"🔍 <b>Поиск: '{search_query}'</b>\n\n"
            f"⏳ <i>Запускаем поиск...</i>",
            parse_mode=ParseMode.HTML)
        logger.info("✅ Оригинальное сообщение обновлено")
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении сообщения: {e}")
        original_message = await bot.send_message(
            chat_id, f"🔍 <b>Поиск: '{search_query}'</b>\n\n"
            f"⏳ <i>Запускаем поиск...</i>",
            parse_mode=ParseMode.HTML)
        logger.info("✅ Отправлено новое сообщение")

    try:
        # Запускаем реальный поиск в фоне
        api = KufarAPI()
        await api.__aenter__()
        search_task = asyncio.create_task(api.search_ads(search_query))

        # Параллельно показываем улучшенную анимацию
        await show_parallel_animation(original_message, f"'{search_query}'",
                                      search_task)

        # Получаем результат поиска
        ads = await search_task
        await api.__aexit__(None, None, None)

        logger.info(f"📊 Найдено {len(ads)} объявлений")

        # Обновляем сообщение с результатами (первая страница)
        await update_message_with_results(original_message,
                                          state,
                                          ads,
                                          search_query,
                                          show_source=False,
                                          page=1)

    except Exception as e:
        logger.error(f"❌ Ошибка при кастомном поиске: {e}", exc_info=True)
        await original_message.edit_text(
            f"❌ <b>Произошла ошибка при поиске</b>\n\n"
            f"Запрос: <code>{search_query}</code>\n"
            f"Попробуйте позже или измените запрос.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML)


@dp.callback_query_handler()
async def debug_all_callbacks(callback_query: CallbackQuery):
    """Отлавливает все callback запросы для отладки"""
    await callback_query.answer()
    logger.info(f"🔍 ПОЛУЧЕН CALLBACK: data = '{callback_query.data}'")

    if callback_query.data == "noop":
        # Заглушка для кнопки с номером страницы
        await callback_query.answer("Вы здесь", show_alert=False)
    elif callback_query.data == "back_to_menu":
        logger.info("🔙 Это кнопка 'Назад'!")
        welcome_text = ("👋 <b>Добро пожаловать в Kufar Search Bot!</b>\n\n"
                        "🎯 <b>Что я умею:</b>\n"
                        "• Искать объявления на Kufar по разным брендам\n"
                        "• Показывать только свежие объявления (до 10 дней)\n"
                        "• Отображать цену в BYN\n"
                        "• Показывать время по МСК\n"
                        "• Статистика по каждому бренду\n"
                        "• Цветное форматирование цен\n"
                        "• Пагинация результатов\n\n"
                        "📌 <b>Выберите действие:</b>")

        await callback_query.message.edit_text(
            welcome_text,
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML)
        logger.info("✅ Возврат в главное меню выполнен")
    else:
        logger.info(f"⚠️ Неизвестный callback: {callback_query.data}")


@dp.message_handler()
async def handle_unknown(message: types.Message):
    """Обработчик неизвестных команд"""
    sent_message = await message.answer(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте /start для главного меню\n"
        "или /menu для возврата к выбору брендов.",
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.HTML)
    await delete_previous_messages(message.chat.id, sent_message.message_id)


if __name__ == "__main__":
    print("=" * 70)
    print("🚀 БОТ С НОВЫМИ ФУНКЦИЯМИ")
    print("=" * 70)
    print(f"📅 Поиск за последние {DAYS_BACK} дней")
    print("⏰ Время: МСК (UTC+3)")
    print("💰 Валюта: BYN (с цветным форматированием и 'Договорная')")
    print(f"🔍 Кнопок в меню: {len(SEARCH_QUERIES)} + 3 доп. кнопки")
    print("🎨 Кастомные обложки для брендов (🖤 для большинства)")
    print("📊 Статистика по каждому бренду")
    print("📄 Пагинация результатов (через FSM)")
    print("⚡ Улучшенная анимация (⏳/⌛️)")
    print("🧹 Автоочистка старых сообщений")
    print(f"📚 {len(KUFAR_FACTS)} фактов о Kufar")
    print("=" * 70)
    executor.start_polling(dp, skip_updates=True)
