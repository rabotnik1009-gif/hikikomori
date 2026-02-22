import asyncio
import logging
import os
import sqlite3
import json
import random
import time
import aiohttp
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

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


# Функция для получения актуальных курсов валют (BYN к другим валютам)
def get_currency_rates():
    try:
        response = requests.get(
            "https://api.exchangerate-api.com/v4/latest/BYN", timeout=5)
        if response.status_code == 200:
            data = response.json()
            rates = data.get("rates", {})
            # Возвращаем курс BYN к выбранной валюте
            return {
                "BYN": 1.0,
                "USD": 1 / rates.get(
                    "USD", 0.32
                ),  # Пример: 1 BYN = 0.32 USD, значит курс BYN->USD = 1/0.32 ≈ 3.12
                "EUR": 1 / rates.get("EUR", 0.30),
                "RUB": 1 / rates.get("RUB", 30.0),
                "UAH": 1 / rates.get("UAH", 12.0)
            }
    except Exception as e:
        logger.error(f"Ошибка получения курсов валют: {e}")

    # Возвращаем примерные курсы, если API недоступно (BYN как базовая)
    return {"BYN": 1.0, "USD": 0.32, "EUR": 0.30, "RUB": 30.0, "UAH": 12.0}


# Курсы валют (обновляются при запуске)
CURRENCY_RATES = get_currency_rates()

# Переводы на разные языки
TRANSLATIONS = {
    "ru": {
        "welcome":
        "👋 Добро пожаловать в Kufar Search Bot!",
        "features":
        "🎯 Что я умею:",
        "feature1":
        "• Искать объявления на Kufar по разным брендам",
        "feature2":
        "• Статистика по каждому бренду",
        "feature3":
        "• Пагинация результатов",
        "search":
        "🔍 Поиск по своему запросу",
        "recent":
        "📱 Последние объявления (24ч)",
        "stats":
        "📊 Статистика по брендам",
        "settings":
        "⚙️ Настройки",
        "back":
        "◀️ Назад",
        "choose_action":
        "◀️ Выберите действие:",
        "settings_title":
        "⚙️ Настройки",
        "settings_desc":
        "Выберите категорию настроек:",
        "depth":
        "📅 Глубина поиска",
        "currency":
        "💰 Валюта",
        "language":
        "🌐 Язык",
        "current_settings":
        "Текущие настройки",
        "search_depth":
        "Глубина поиска",
        "days_24h":
        "24 часа",
        "days_3":
        "3 дня",
        "days_7":
        "7 дней",
        "days_14":
        "14 дней",
        "days_30":
        "30 дней",
        "custom":
        "✨ Свой период",
        "enter_custom_days":
        "Введите количество дней (1-365):",
        "invalid_days":
        "❌ Неверное значение. Введите число от 1 до 365:",
        "depth_updated":
        "✅ Глубина поиска обновлена на {days} дн.",
        "currency_title":
        "💰 Выберите валюту:",
        "currency_updated":
        "✅ Валюта обновлена на {currency}",
        "language_title":
        "🌐 Выберите язык:",
        "language_updated":
        "✅ Язык обновлен",
        "back_to_settings":
        "◀️ Назад к настройкам",
        "unknown":
        "❓ Неизвестная команда\nИспользуйте /start для главного меню",
        "search_results":
        "🔍 Результаты поиска: {title}",
        "found_total":
        "📊 Всего найдено: {count}",
        "page_info":
        "📄 Страница {page}/{total}",
        "last_days":
        "за последние {days} дней",
        "last_24h":
        "⏱️ за последние 24ч",  # Добавлено для 24ч
        "choose_other_brand":
        "◀️ Выбрать другой бренд",
        "search_animation":
        "Ищем на Kufar",
        "did_you_know":
        "Знаете ли вы",
        "search_completed":
        "Поиск завершен",
        "loading_results":
        "Загружаю результаты",
        "no_ads_found":
        "📭 <b>Нет объявлений по запросу '{query}'</b>",
        "custom_search_prompt":
        ("🔍 <b>Поиск по своему запросу</b>\n\n"
         "📝 <b>Как это работает:</b>\n"
         "• Введите любой бренд, модель или ключевое слово\n"
         "• Я покажу объявления за последние 10 дней\n"
         "• Можно вводить на русском или английском\n"
         "• Покажу статистику по вашему запросу\n\n"
         "✨ <b>Примеры запросов:</b>\n"
         "• <code>nike air max</code>\n"
         "• <code>iphone 13</code>\n"
         "• <code>дизель джинсы</code>\n\n"
         "⬇️ <b>Введите ваш запрос ниже:</b>"),
        "stats_for_brand":
        "📊 Статистика для {icon} {brand_name}",
        "no_data_30_days":
        "❌ Нет данных за последние 30 дней",
        "total_ads":
        "📦 <b>Всего объявлений:</b> {count}",
        "per_week":
        "📅 <b>За неделю:</b> {count}",
        "avg_price":
        "💰 <b>Средняя цена:</b> {price} {currency}",
        "max_price":
        "🏆 <b>Самое дорогое:</b> {price} {currency}",
        "min_price":
        "🎁 <b>Самое дешевое:</b> {price} {currency}",
        "stats_period":
        "📊 <i>Статистика за последние 30 дней</i>",
        "back_to_brand_list":
        "◀️ Назад к списку брендов",
        "main_menu":
        "🏠 Главное меню",
        "analysing_data":
        "📊 <b>Анализирую данные для {icon} {brand_name}...</b>\n\n⏳ <i>Это может занять несколько секунд</i>",
        "error_occurred":
        "❌ <b>Произошла ошибка</b>\n\nПопробуйте позже.",
        "search_error":
        "❌ <b>Произошла ошибка при поиске</b>\n\nПопробуйте позже или проверьте вручную."
    },
    "be": {
        "welcome":
        "👋 Сардэчна запрашаем у Kufar Search Bot!",
        "features":
        "🎯 Што я ўмею:",
        "feature1":
        "• Шукаць аб'явы на Kufar па розных брэндах",
        "feature2":
        "• Статыстыка па кожным брэндзе",
        "feature3":
        "• Пагінацыя вынікаў",
        "search":
        "🔍 Пошук па сваім запыце",
        "recent":
        "📱 Апошнія аб'явы (24г)",
        "stats":
        "📊 Статыстыка па брэндах",
        "settings":
        "⚙️ Налады",
        "back":
        "◀️ Назад",
        "choose_action":
        "◀️ Выберыце дзеянне:",
        "settings_title":
        "⚙️ Налады",
        "settings_desc":
        "Выберыце катэгорыю наладаў:",
        "depth":
        "📅 Глыбіня пошуку",
        "currency":
        "💰 Валюта",
        "language":
        "🌐 Мова",
        "current_settings":
        "Бягучыя налады",
        "search_depth":
        "Глыбіня пошуку",
        "days_24h":
        "24 гадзіны",
        "days_3":
        "3 дні",
        "days_7":
        "7 дзён",
        "days_14":
        "14 дзён",
        "days_30":
        "30 дзён",
        "custom":
        "✨ Свой перыяд",
        "enter_custom_days":
        "Увядзіце колькасць дзён (1-365):",
        "invalid_days":
        "❌ Памылковае значэнне. Увядзіце лік ад 1 да 365:",
        "depth_updated":
        "✅ Глыбіня пошуку абноўлена на {days} дн.",
        "currency_title":
        "💰 Выберыце валюту:",
        "currency_updated":
        "✅ Валюта абноўлена на {currency}",
        "language_title":
        "🌐 Выберыце мову:",
        "language_updated":
        "✅ Мова абноўлена",
        "back_to_settings":
        "◀️ Назад да наладаў",
        "unknown":
        "❓ Невядомая каманда\nВыкарыстоўвайце /start для галоўнага меню",
        "search_results":
        "🔍 Вынікі пошуку: {title}",
        "found_total":
        "📊 Усяго знойдзена: {count}",
        "page_info":
        "📄 Старонка {page}/{total}",
        "last_days":
        "за апошнія {days} дзён",
        "last_24h":
        "⏱️ за апошнія 24г",
        "choose_other_brand":
        "◀️ Выбраць іншы брэнд",
        "search_animation":
        "Шукаем на Kufar",
        "did_you_know":
        "Ці ведаеце вы",
        "search_completed":
        "Пошук завершаны",
        "loading_results":
        "Загружаю вынікі",
        "no_ads_found":
        "📭 <b>Няма аб'яў па запыце '{query}'</b>",
        "custom_search_prompt":
        ("🔍 <b>Пошук па сваім запыце</b>\n\n"
         "📝 <b>Як гэта працуе:</b>\n"
         "• Увядзіце любы брэнд, мадэль або ключавое слова\n"
         "• Я пакажу аб'явы за апошнія 10 дзён\n"
         "• Можна ўводзіць на рускай ці англійскай\n"
         "• Пакажу статыстыку па вашым запыце\n\n"
         "✨ <b>Прыклады запытаў:</b>\n"
         "• <code>nike air max</code>\n"
         "• <code>iphone 13</code>\n"
         "• <code>дизель джинсы</code>\n\n"
         "⬇️ <b>Увядзіце ваш запыт ніжэй:</b>"),
        "stats_for_brand":
        "📊 Статыстыка для {icon} {brand_name}",
        "no_data_30_days":
        "❌ Няма дадзеных за апошнія 30 дзён",
        "total_ads":
        "📦 <b>Усяго аб'яў:</b> {count}",
        "per_week":
        "📅 <b>За тыдзень:</b> {count}",
        "avg_price":
        "💰 <b>Сярэдні кошт:</b> {price} {currency}",
        "max_price":
        "🏆 <b>Самы дарагі:</b> {price} {currency}",
        "min_price":
        "🎁 <b>Самы танны:</b> {price} {currency}",
        "stats_period":
        "📊 <i>Статыстыка за апошнія 30 дзён</i>",
        "back_to_brand_list":
        "◀️ Назад да спісу брэндаў",
        "main_menu":
        "🏠 Галоўнае меню",
        "analysing_data":
        "📊 <b>Аналізую дадзеныя для {icon} {brand_name}...</b>\n\n⏳ <i>Гэта можа заняць некалькі секунд</i>",
        "error_occurred":
        "❌ <b>Адбылася памылка</b>\n\nПаспрабуйце пазней.",
        "search_error":
        "❌ <b>Адбылася памылка пры пошуку</b>\n\nПаспрабуйце пазней ці праверце ўручную."
    },
    "en": {
        "welcome":
        "👋 Welcome to Kufar Search Bot!",
        "features":
        "🎯 What I can do:",
        "feature1":
        "• Search Kufar listings by different brands",
        "feature2":
        "• Statistics for each brand",
        "feature3":
        "• Pagination of results",
        "search":
        "🔍 Custom search",
        "recent":
        "📱 Recent listings (24h)",
        "stats":
        "📊 Brand statistics",
        "settings":
        "⚙️ Settings",
        "back":
        "◀️ Back",
        "choose_action":
        "◀️ Choose action:",
        "settings_title":
        "⚙️ Settings",
        "settings_desc":
        "Choose settings category:",
        "depth":
        "📅 Search depth",
        "currency":
        "💰 Currency",
        "language":
        "🌐 Language",
        "current_settings":
        "Current settings",
        "search_depth":
        "Search depth",
        "days_24h":
        "24 hours",
        "days_3":
        "3 days",
        "days_7":
        "7 days",
        "days_14":
        "14 days",
        "days_30":
        "30 days",
        "custom":
        "✨ Custom period",
        "enter_custom_days":
        "Enter number of days (1-365):",
        "invalid_days":
        "❌ Invalid value. Enter number from 1 to 365:",
        "depth_updated":
        "✅ Search depth updated to {days} days",
        "currency_title":
        "💰 Choose currency:",
        "currency_updated":
        "✅ Currency updated to {currency}",
        "language_title":
        "🌐 Choose language:",
        "language_updated":
        "✅ Language updated",
        "back_to_settings":
        "◀️ Back to settings",
        "unknown":
        "❓ Unknown command\nUse /start for main menu",
        "search_results":
        "🔍 Search results: {title}",
        "found_total":
        "📊 Total found: {count}",
        "page_info":
        "📄 Page {page}/{total}",
        "last_days":
        "for the last {days} days",
        "last_24h":
        "⏱️ for the last 24h",
        "choose_other_brand":
        "◀️ Choose another brand",
        "search_animation":
        "Searching on Kufar",
        "did_you_know":
        "Did you know",
        "search_completed":
        "Search completed",
        "loading_results":
        "Loading results",
        "no_ads_found":
        "📭 <b>No listings found for '{query}'</b>",
        "custom_search_prompt": ("🔍 <b>Custom Search</b>\n\n"
                                 "📝 <b>How it works:</b>\n"
                                 "• Enter any brand, model or keyword\n"
                                 "• I'll show listings from the last 10 days\n"
                                 "• You can enter in Russian or English\n"
                                 "• I'll show statistics for your query\n\n"
                                 "✨ <b>Query examples:</b>\n"
                                 "• <code>nike air max</code>\n"
                                 "• <code>iphone 13</code>\n"
                                 "• <code>дизель джинсы</code>\n\n"
                                 "⬇️ <b>Enter your query below:</b>"),
        "stats_for_brand":
        "📊 Statistics for {icon} {brand_name}",
        "no_data_30_days":
        "❌ No data for the last 30 days",
        "total_ads":
        "📦 <b>Total listings:</b> {count}",
        "per_week":
        "📅 <b>Per week:</b> {count}",
        "avg_price":
        "💰 <b>Average price:</b> {price} {currency}",
        "max_price":
        "🏆 <b>Most expensive:</b> {price} {currency}",
        "min_price":
        "🎁 <b>Cheapest:</b> {price} {currency}",
        "stats_period":
        "📊 <i>Statistics for the last 30 days</i>",
        "back_to_brand_list":
        "◀️ Back to brand list",
        "main_menu":
        "🏠 Main menu",
        "analysing_data":
        "📊 <b>Analysing data for {icon} {brand_name}...</b>\n\n⏳ <i>This may take a few seconds</i>",
        "error_occurred":
        "❌ <b>An error occurred</b>\n\nPlease try again later.",
        "search_error":
        "❌ <b>An error occurred while searching</b>\n\nPlease try again later or check manually."
    },
    "uk": {
        "welcome":
        "👋 Ласкаво просимо до Kufar Search Bot!",
        "features":
        "🎯 Що я вмію:",
        "feature1":
        "• Шукати оголошення на Kufar за різними брендами",
        "feature2":
        "• Статистика по кожному бренду",
        "feature3":
        "• Пагінація результатів",
        "search":
        "🔍 Пошук за своїм запитом",
        "recent":
        "📱 Останні оголошення (24год)",
        "stats":
        "📊 Статистика по брендам",
        "settings":
        "⚙️ Налаштування",
        "back":
        "◀️ Назад",
        "choose_action":
        "◀️ Виберіть дію:",
        "settings_title":
        "⚙️ Налаштування",
        "settings_desc":
        "Виберіть категорію налаштувань:",
        "depth":
        "📅 Глибина пошуку",
        "currency":
        "💰 Валюта",
        "language":
        "🌐 Мова",
        "current_settings":
        "Поточні налаштування",
        "search_depth":
        "Глибина пошуку",
        "days_24h":
        "24 години",
        "days_3":
        "3 дні",
        "days_7":
        "7 днів",
        "days_14":
        "14 днів",
        "days_30":
        "30 днів",
        "custom":
        "✨ Свій період",
        "enter_custom_days":
        "Введіть кількість днів (1-365):",
        "invalid_days":
        "❌ Невірне значення. Введіть число від 1 до 365:",
        "depth_updated":
        "✅ Глибину пошуку оновлено на {days} дн.",
        "currency_title":
        "💰 Виберіть валюту:",
        "currency_updated":
        "✅ Валюту оновлено на {currency}",
        "language_title":
        "🌐 Виберіть мову:",
        "language_updated":
        "✅ Мову оновлено",
        "back_to_settings":
        "◀️ Назад до налаштувань",
        "unknown":
        "❓ Невідома команда\nВикористовуйте /start для головного меню",
        "search_results":
        "🔍 Результати пошуку: {title}",
        "found_total":
        "📊 Всього знайдено: {count}",
        "page_info":
        "📄 Сторінка {page}/{total}",
        "last_days":
        "за останні {days} днів",
        "last_24h":
        "⏱️ за останні 24год",
        "choose_other_brand":
        "◀️ Вибрати інший бренд",
        "search_animation":
        "Шукаємо на Kufar",
        "did_you_know":
        "Чи знаєте ви",
        "search_completed":
        "Пошук завершено",
        "loading_results":
        "Завантажую результати",
        "no_ads_found":
        "📭 <b>Немає оголошень за запитом '{query}'</b>",
        "custom_search_prompt":
        ("🔍 <b>Пошук за своїм запитом</b>\n\n"
         "📝 <b>Як це працює:</b>\n"
         "• Введіть будь-який бренд, модель або ключове слово\n"
         "• Я покажу оголошення за останні 10 днів\n"
         "• Можна вводити російською або англійською\n"
         "• Покажу статистику за вашим запитом\n\n"
         "✨ <b>Приклади запитів:</b>\n"
         "• <code>nike air max</code>\n"
         "• <code>iphone 13</code>\n"
         "• <code>дизель джинсы</code>\n\n"
         "⬇️ <b>Введіть ваш запит нижче:</b>"),
        "stats_for_brand":
        "📊 Статистика для {icon} {brand_name}",
        "no_data_30_days":
        "❌ Немає даних за останні 30 днів",
        "total_ads":
        "📦 <b>Всього оголошень:</b> {count}",
        "per_week":
        "📅 <b>За тиждень:</b> {count}",
        "avg_price":
        "💰 <b>Середня ціна:</b> {price} {currency}",
        "max_price":
        "🏆 <b>Найдорожче:</b> {price} {currency}",
        "min_price":
        "🎁 <b>Найдешевше:</b> {price} {currency}",
        "stats_period":
        "📊 <i>Статистика за останні 30 днів</i>",
        "back_to_brand_list":
        "◀️ Назад до списку брендів",
        "main_menu":
        "🏠 Головне меню",
        "analysing_data":
        "📊 <b>Аналізую дані для {icon} {brand_name}...</b>\n\n⏳ <i>Це може зайняти кілька секунд</i>",
        "error_occurred":
        "❌ <b>Сталася помилка</b>\n\nСпробуйте пізніше.",
        "search_error":
        "❌ <b>Сталася помилка під час пошуку</b>\n\nСпробуйте пізніше або перевірте вручну."
    },
    "de": {
        "welcome":
        "👋 Willkommen beim Kufar Search Bot!",
        "features":
        "🎯 Was ich kann:",
        "feature1":
        "• Kufar-Anzeigen nach verschiedenen Marken durchsuchen",
        "feature2":
        "• Statistiken für jede Marke",
        "feature3":
        "• Seitennavigation der Ergebnisse",
        "search":
        "🔍 Eigene Suche",
        "recent":
        "📱 Neueste Anzeigen (24h)",
        "stats":
        "📊 Markenstatistiken",
        "settings":
        "⚙️ Einstellungen",
        "back":
        "◀️ Zurück",
        "choose_action":
        "◀️ Aktion auswählen:",
        "settings_title":
        "⚙️ Einstellungen",
        "settings_desc":
        "Wählen Sie eine Kategorie:",
        "depth":
        "📅 Suchtiefe",
        "currency":
        "💰 Währung",
        "language":
        "🌐 Sprache",
        "current_settings":
        "Aktuelle Einstellungen",
        "search_depth":
        "Suchtiefe",
        "days_24h":
        "24 Stunden",
        "days_3":
        "3 Tage",
        "days_7":
        "7 Tage",
        "days_14":
        "14 Tage",
        "days_30":
        "30 Tage",
        "custom":
        "✨ Benutzerdefiniert",
        "enter_custom_days":
        "Geben Sie die Anzahl der Tage ein (1-365):",
        "invalid_days":
        "❌ Ungültiger Wert. Geben Sie eine Zahl von 1 bis 365 ein:",
        "depth_updated":
        "✅ Suchtiefe auf {days} Tage aktualisiert",
        "currency_title":
        "💰 Währung auswählen:",
        "currency_updated":
        "✅ Währung auf {currency} aktualisiert",
        "language_title":
        "🌐 Sprache auswählen:",
        "language_updated":
        "✅ Sprache aktualisiert",
        "back_to_settings":
        "◀️ Zurück zu den Einstellungen",
        "unknown":
        "❓ Unbekannter Befehl\nVerwenden Sie /start für das Hauptmenü",
        "search_results":
        "🔍 Suchergebnisse: {title}",
        "found_total":
        "📊 Insgesamt gefunden: {count}",
        "page_info":
        "📄 Seite {page}/{total}",
        "last_days":
        "für die letzten {days} Tage",
        "last_24h":
        "⏱️ für die letzten 24h",
        "choose_other_brand":
        "◀️ Andere Marke wählen",
        "search_animation":
        "Suche auf Kufar",
        "did_you_know":
        "Wussten Sie",
        "search_completed":
        "Suche abgeschlossen",
        "loading_results":
        "Lade Ergebnisse",
        "no_ads_found":
        "📭 <b>Keine Anzeigen für '{query}' gefunden</b>",
        "custom_search_prompt":
        ("🔍 <b>Eigene Suche</b>\n\n"
         "📝 <b>Wie es funktioniert:</b>\n"
         "• Geben Sie eine Marke, ein Modell oder ein Schlüsselwort ein\n"
         "• Ich zeige Anzeigen der letzten 10 Tage\n"
         "• Eingabe auf Russisch oder Englisch möglich\n"
         "• Ich zeige Statistiken zu Ihrer Anfrage\n\n"
         "✨ <b>Beispielanfragen:</b>\n"
         "• <code>nike air max</code>\n"
         "• <code>iphone 13</code>\n"
         "• <code>дизель джинсы</code>\n\n"
         "⬇️ <b>Geben Sie unten Ihre Anfrage ein:</b>"),
        "stats_for_brand":
        "📊 Statistiken für {icon} {brand_name}",
        "no_data_30_days":
        "❌ Keine Daten für die letzten 30 Tage",
        "total_ads":
        "📦 <b>Anzeigen insgesamt:</b> {count}",
        "per_week":
        "📅 <b>Pro Woche:</b> {count}",
        "avg_price":
        "💰 <b>Durchschnittspreis:</b> {price} {currency}",
        "max_price":
        "🏆 <b>Teuerste:</b> {price} {currency}",
        "min_price":
        "🎁 <b>Günstigste:</b> {price} {currency}",
        "stats_period":
        "📊 <i>Statistiken der letzten 30 Tage</i>",
        "back_to_brand_list":
        "◀️ Zurück zur Markenliste",
        "main_menu":
        "🏠 Hauptmenü",
        "analysing_data":
        "📊 <b>Analysiere Daten für {icon} {brand_name}...</b>\n\n⏳ <i>Dies kann einige Sekunden dauern</i>",
        "error_occurred":
        "❌ <b>Ein Fehler ist aufgetreten</b>\n\nBitte versuchen Sie es später erneut.",
        "search_error":
        "❌ <b>Bei der Suche ist ein Fehler aufgetreten</b>\n\nBitte versuchen Sie es später erneut oder überprüfen Sie manuell."
    }
}


# Состояния для FSM
class SearchStates(StatesGroup):
    waiting_for_query = State()
    waiting_for_custom_days = State()


class PaginationStates(StatesGroup):
    browsing_results = State()


# Обновленные поисковые запросы (удален "redan")
SEARCH_QUERIES = {
    "hikikomori":
    ["hikikomori", "hikikomori kai", "хикикомори", "хикикомори кай"],
    "bladnes": ["bladnes"],
    "ryodan": ["ryodan", "редан"],  # Теперь Ryodan ищет и ryodan и редан
    "zxcursed": ["zxcursed"],
    "shadowraze": ["shadowraze"],
    "holy_sinner": ["holy sinner"],
    "neform": ["нефор"],
    "cvrsxdcrown": ["cvrsxdcrown"],
    "hatred888": ["hatred888"],
    "hikinight": ["hikinight"],
    "enemy_in_reflection": ["enemy in reflection"],
    "enemy": ["enemy"],
    "conjunctiva": ["conjunctiva"],
    "convulsive": ["convulsive"],
    "ethereal": ["ethereal"],
    "double_minded": ["double minded"],
    "kusakabe": ["kusakabe"],
    "sheydov": ["sheydov"]
}

# Отображение названий для кнопок (удален "redan")
BUTTON_NAMES = {
    "hikikomori": "Hikikomori Kai",
    "bladnes": "Bladnes",
    "ryodan": "Ryodan",  # Теперь Ryodan (без отдельной кнопки Редан)
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
    "ethereal": "Ethereal",
    "double_minded": "Double Minded",
    "kusakabe": "Kusakabe",
    "sheydov": "Sheydov"
}

# Кастомные обложки для брендов
BRAND_IMAGES = {
    "Hikikomori Kai": "🖤",
    "Bladnes": "🖤",
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

DEFAULT_DAYS_BACK = 10
LAST_24H_HOURS = 1
MAX_MESSAGE_LENGTH = 3500
ITEMS_PER_PAGE = 10

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

# Callback данные
stats_cb = CallbackData("stats", "query_key")
pagination_cb = CallbackData("page", "action", "page_num")
settings_cb = CallbackData("settings", "action")
depth_cb = CallbackData("depth", "value")
currency_cb = CallbackData("currency", "value")
language_cb = CallbackData("language", "value")

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

    def __init__(self, db_name: str = "users.db"):
        self.db_name = db_name
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    language TEXT DEFAULT 'ru',
                    currency TEXT DEFAULT 'BYN',
                    days_back INTEGER DEFAULT 10,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    query TEXT,
                    results_count INTEGER,
                    search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT language, currency, days_back FROM user_settings WHERE user_id = ?",
                (user_id, ))
            result = cursor.fetchone()

            if result:
                return {
                    "language": result[0],
                    "currency": result[1],
                    "days_back": result[2]
                }
            else:
                cursor.execute(
                    "INSERT INTO user_settings (user_id, language, currency, days_back) VALUES (?, ?, ?, ?)",
                    (user_id, "ru", "BYN", 10))
                conn.commit()
                return {"language": "ru", "currency": "BYN", "days_back": 10}

    def update_language(self, user_id: int, language: str):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET language = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (language, user_id))
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO user_settings (user_id, language) VALUES (?, ?)",
                    (user_id, language))
            conn.commit()

    def update_currency(self, user_id: int, currency: str):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET currency = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (currency, user_id))
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO user_settings (user_id, currency) VALUES (?, ?)",
                    (user_id, currency))
            conn.commit()

    def update_days_back(self, user_id: int, days_back: int):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET days_back = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (days_back, user_id))
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO user_settings (user_id, days_back) VALUES (?, ?)",
                    (user_id, days_back))
            conn.commit()

    def save_search_history(self, user_id: int, query: str,
                            results_count: int):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO search_history (user_id, query, results_count) VALUES (?, ?, ?)",
                (user_id, query, results_count))
            conn.commit()


db = Database()


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
                         search_queries: List[str],
                         days_back: int = 10) -> List[Dict[str, Any]]:
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
        cutoff_date = datetime.now() - timedelta(days=days_back)

        for search_query in search_queries:
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

                    async with self.session.get(url,
                                                params=params,
                                                headers=headers,
                                                timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            ads = self._parse_ads(data, search_query)

                            # Фильтруем по дате
                            for ad in ads:
                                if "date" in ad and ad["date"] >= cutoff_date:
                                    if ad not in all_ads:
                                        all_ads.append(ad)
                            break
                except Exception as e:
                    logger.warning(f"❌ Ошибка при запросе к {url}: {e}")

        # Сортируем по дате (новые сверху)
        all_ads.sort(key=lambda x: x.get("date", datetime.min), reverse=True)
        logger.info(f"✅ Всего получено {len(all_ads)} уникальных объявлений")
        return all_ads

    async def search_all_ads_recent(self) -> List[Dict[str, Any]]:
        all_results = []
        cutoff_date = datetime.now() - timedelta(days=LAST_24H_HOURS)

        for query_key, search_queries in SEARCH_QUERIES.items():
            try:
                ads = await self.search_ads(search_queries,
                                            days_back=LAST_24H_HOURS)
                for ad in ads:
                    if "date" in ad and ad["date"] >= cutoff_date:
                        ad["search_query_display"] = BUTTON_NAMES.get(
                            query_key, query_key)
                        if ad not in all_results:
                            all_results.append(ad)
            except Exception as e:
                logger.error(f"❌ Ошибка при поиске '{query_key}': {e}")

        all_results.sort(key=lambda x: x.get("date", datetime.min),
                         reverse=True)
        return all_results

    def _parse_ads(self, data: Dict[str, Any],
                   search_query: str) -> List[Dict[str, Any]]:
        ads = []
        try:
            products = data.get("ads", []) or data.get("products", [])

            for product in products:
                if not isinstance(product, dict):
                    continue

                title = product.get("subject", "") or product.get(
                    "title", "") or product.get("name", "")
                ad_id = str(product.get("ad_id", "")) or str(
                    product.get("id", "")) or str(product.get("item_id", ""))

                if not ad_id:
                    continue

                # Проверяем наличие поискового запроса ТОЛЬКО в заголовке
                if search_query.lower() not in title.lower():
                    continue

                ad_date = None
                if "list_time" in product:
                    list_time = product["list_time"]
                    if isinstance(list_time, str):
                        try:
                            list_time = list_time.replace('Z', '')
                            ad_date = datetime.fromisoformat(list_time)
                        except Exception:
                            pass

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

                # Проверяем уникальность по ID
                if not any(a["id"] == ad_id for a in ads):
                    ads.append(ad_data)

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")

        return ads


def format_price(price: float, currency: str = "BYN") -> str:
    """Форматирует цену с учетом валюты (ИСПРАВЛЕНО)"""
    if price == 0:
        return "💰 <b>Цена:</b> Договорная"

    # Цена в API всегда в BYN. Конвертируем BYN в выбранную валюту.
    # Например: курс USD = 0.32 (1 BYN = 0.32 USD). Значит 100 BYN = 100 * 0.32 = 32 USD.
    converted_price = price * CURRENCY_RATES[currency]

    return f"{converted_price:.2f} {currency}"


def get_brand_icon(brand_name: str) -> str:
    """Получить иконку для бренда"""
    return BRAND_IMAGES.get(brand_name, "🖤")


def get_main_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
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
            text=TRANSLATIONS[lang]["search"],
            callback_data=custom_search_cb.new(action="start")))
    keyboard.add(
        InlineKeyboardButton(text=TRANSLATIONS[lang]["recent"],
                             callback_data=recent_cb.new(action="show")))
    keyboard.add(
        InlineKeyboardButton(text=TRANSLATIONS[lang]["stats"],
                             callback_data=stats_cb.new(query_key="all")))
    keyboard.add(
        InlineKeyboardButton(text=TRANSLATIONS[lang]["settings"],
                             callback_data=settings_cb.new(action="main")))

    return keyboard


def get_settings_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Создает клавиатуру настроек"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        InlineKeyboardButton(text=TRANSLATIONS[lang]["depth"],
                             callback_data=settings_cb.new(action="depth")),
        InlineKeyboardButton(text=TRANSLATIONS[lang]["currency"],
                             callback_data=settings_cb.new(action="currency")),
        InlineKeyboardButton(text=TRANSLATIONS[lang]["language"],
                             callback_data=settings_cb.new(action="language")))
    keyboard.add(
        InlineKeyboardButton(text=TRANSLATIONS[lang]["back"],
                             callback_data="back_to_menu"))

    return keyboard


def get_depth_keyboard(lang: str = "ru",
                       current_days: int = 10) -> InlineKeyboardMarkup:
    """Создает клавиатуру выбора глубины поиска"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    depth_options = [(1, TRANSLATIONS[lang]["days_24h"]),
                     (3, TRANSLATIONS[lang]["days_3"]),
                     (7, TRANSLATIONS[lang]["days_7"]),
                     (14, TRANSLATIONS[lang]["days_14"]),
                     (30, TRANSLATIONS[lang]["days_30"]),
                     (0, TRANSLATIONS[lang]["custom"])]

    for days, text in depth_options:
        if days > 0:
            marker = " ✅" if days == current_days else ""
            callback = depth_cb.new(value=str(days))
        else:
            marker = ""
            callback = depth_cb.new(value="custom")

        keyboard.add(
            InlineKeyboardButton(text=f"{text}{marker}",
                                 callback_data=callback))

    keyboard.add(
        InlineKeyboardButton(text=TRANSLATIONS[lang]["back_to_settings"],
                             callback_data=settings_cb.new(action="main")))

    return keyboard


def get_currency_keyboard(
        lang: str = "ru",
        current_currency: str = "BYN") -> InlineKeyboardMarkup:
    """Создает клавиатуру выбора валюты"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    currencies = ["BYN", "USD", "EUR", "RUB", "UAH"]

    for curr in currencies:
        marker = " ✅" if curr == current_currency else ""
        keyboard.add(
            InlineKeyboardButton(text=f"{curr}{marker}",
                                 callback_data=currency_cb.new(value=curr)))

    keyboard.add(
        InlineKeyboardButton(text=TRANSLATIONS[lang]["back_to_settings"],
                             callback_data=settings_cb.new(action="main")))

    return keyboard


def get_language_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Создает клавиатуру выбора языка (исправлено)"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    languages = [("ru", "🇷🇺 Русский"), ("be", "🇧🇾 Беларуская"),
                 ("en", "🇬🇧 English"), ("uk", "🇺🇦 Українська"),
                 ("de", "🇩🇪 Deutsch")]

    for code, name in languages:
        marker = " ✅" if code == lang else ""
        keyboard.add(
            InlineKeyboardButton(text=f"{name}{marker}",
                                 callback_data=language_cb.new(value=code)))

    keyboard.add(
        InlineKeyboardButton(text=TRANSLATIONS[lang]["back_to_settings"],
                             callback_data=settings_cb.new(action="main")))

    return keyboard


def get_stats_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
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
        InlineKeyboardButton(text=TRANSLATIONS[lang]["back"],
                             callback_data="back_to_menu"))
    return keyboard


def get_pagination_keyboard(page_num: int,
                            total_pages: int,
                            lang: str = "ru") -> InlineKeyboardMarkup:
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
        InlineKeyboardButton(text=TRANSLATIONS[lang]["choose_other_brand"],
                             callback_data="back_to_menu"))
    return keyboard


def get_back_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой назад"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(text=TRANSLATIONS[lang]["back"],
                             callback_data="back_to_menu"))
    return keyboard


async def delete_previous_messages(chat_id: int,
                                   current_message_id: int,
                                   exclude_ids: List[int] = None):
    """Удаляет все предыдущие сообщения в чате, кроме указанных"""
    if exclude_ids is None:
        exclude_ids = []

    try:
        deleted_count = 0
        for msg_id in range(current_message_id - 20, current_message_id):
            if msg_id > 0 and msg_id not in exclude_ids:
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
                   show_source: bool = False,
                   currency: str = "BYN") -> str:
    """Форматирует текст объявления"""
    date_str = ""
    if "date" in ad:
        msk_date = ad["date"] + timedelta(hours=3)
        date_str = f"📅 {msk_date.strftime('%d.%m.%Y %H:%M')} МСК\n"

    source_str = ""
    if show_source and "search_query_display" in ad:
        source_str = f"🏷️ <b>Бренд:</b> {ad['search_query_display']}\n"

    price_text = format_price(ad['price'], currency)

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
                                      page: int = 1,
                                      currency: str = "BYN",
                                      days_back: int = 10):
    """Обновляет сообщение с результатами поиска"""

    user_id = message.chat.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    if not ads:
        await state.finish()
        # Используем перевод для сообщения об отсутствии объявлений
        no_ads_text = TRANSLATIONS[lang]["no_ads_found"].format(query=title)
        # Определяем текст для периода
        if days_back == 1:
            period_text = TRANSLATIONS[lang]["last_24h"]
        else:
            period_text = TRANSLATIONS[lang]["last_days"].format(
                days=days_back)

        await message.edit_text(f"{no_ads_text}\n\n{period_text}",
                                reply_markup=get_main_menu_keyboard(lang),
                                parse_mode=ParseMode.HTML)
        return

    total_pages = (len(ads) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if page > total_pages:
        page = total_pages
    if page < 1:
        page = 1

    async with state.proxy() as data:
        data['ads'] = ads
        data['title'] = title
        data['show_source'] = show_source
        data['total_pages'] = total_pages
        data['currency'] = currency
        data['days_back'] = days_back

    await PaginationStates.browsing_results.set()

    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, len(ads))
    current_page_ads = ads[start_idx:end_idx]

    # Определяем текст для периода
    if days_back == 1:
        period_text = TRANSLATIONS[lang]["last_24h"]
    else:
        period_text = TRANSLATIONS[lang]["last_days"].format(days=days_back)

    full_text = (
        f"{TRANSLATIONS[lang]['search_results'].format(title=title)}\n"
        f"{TRANSLATIONS[lang]['found_total'].format(count=len(ads))}\n"
        f"{TRANSLATIONS[lang]['page_info'].format(page=page, total=total_pages)}\n"
        f"{period_text}\n"
        f"{'═' * 30}\n\n")

    for i, ad in enumerate(current_page_ads, start=start_idx + 1):
        full_text += format_ad_text(ad, i, show_source, currency)

    full_text += f"{'═' * 30}\n◀️ <b>{TRANSLATIONS[lang]['choose_action']}</b>"

    await message.edit_text(full_text,
                            reply_markup=get_pagination_keyboard(
                                page, total_pages, lang),
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
        currency = data.get('currency', 'BYN')
        days_back = data.get('days_back', 10)

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
                                      page=page_num,
                                      currency=currency,
                                      days_back=days_back)


async def calculate_brand_statistics(search_queries: List[str],
                                     currency: str = "BYN") -> Dict[str, Any]:
    """Рассчитывает статистику по бренду"""
    async with KufarAPI() as api:
        ads = await api.search_ads(search_queries, days_back=30)

    if not ads:
        return {
            "total": 0,
            "week": 0,
            "avg_price": 0,
            "max_price": 0,
            "min_price": 0
        }

    week_ago = datetime.now() - timedelta(days=7)
    week_ads = [ad for ad in ads if ad.get("date", datetime.min) >= week_ago]

    prices = [ad["price"] for ad in ads if ad["price"] > 0]

    # Конвертируем цены для статистики (BYN -> выбранная валюта)
    if currency != "BYN":
        prices = [p * CURRENCY_RATES[currency] for p in prices]

    return {
        "total": len(ads),
        "week": len(week_ads),
        "avg_price": sum(prices) / len(prices) if prices else 0,
        "max_price": max(prices) if prices else 0,
        "min_price": min(prices) if prices else 0
    }


# ==================== НАСТРОЙКИ ====================


@dp.callback_query_handler(settings_cb.filter(action="main"))
async def settings_main(callback_query: CallbackQuery, state: FSMContext):
    """Главное меню настроек"""
    user_id = callback_query.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    await state.finish()
    await callback_query.answer()

    text = (f"{TRANSLATIONS[lang]['settings_title']}\n\n"
            f"{TRANSLATIONS[lang]['settings_desc']}")

    await callback_query.message.edit_text(
        text,
        reply_markup=get_settings_keyboard(lang),
        parse_mode=ParseMode.HTML)


@dp.callback_query_handler(settings_cb.filter(action="depth"))
async def settings_depth(callback_query: CallbackQuery, state: FSMContext):
    """Настройка глубины поиска"""
    user_id = callback_query.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    await callback_query.answer()

    text = (
        f"{TRANSLATIONS[lang]['settings_title']} › {TRANSLATIONS[lang]['depth']}\n\n"
        f"{TRANSLATIONS[lang]['current_settings']}:\n"
        f"📅 {TRANSLATIONS[lang]['search_depth']}: {settings['days_back']} дн.\n\n"
        f"{TRANSLATIONS[lang]['settings_desc']}")

    await callback_query.message.edit_text(text,
                                           reply_markup=get_depth_keyboard(
                                               lang, settings['days_back']),
                                           parse_mode=ParseMode.HTML)


@dp.callback_query_handler(settings_cb.filter(action="currency"))
async def settings_currency(callback_query: CallbackQuery, state: FSMContext):
    """Настройка валюты"""
    user_id = callback_query.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    await callback_query.answer()

    text = (
        f"{TRANSLATIONS[lang]['settings_title']} › {TRANSLATIONS[lang]['currency']}\n\n"
        f"{TRANSLATIONS[lang]['current_settings']}:\n"
        f"💰 Валюта: {settings['currency']}\n\n"
        f"{TRANSLATIONS[lang]['currency_title']}")

    await callback_query.message.edit_text(text,
                                           reply_markup=get_currency_keyboard(
                                               lang, settings['currency']),
                                           parse_mode=ParseMode.HTML)


@dp.callback_query_handler(settings_cb.filter(action="language"))
async def settings_language(callback_query: CallbackQuery, state: FSMContext):
    """Настройка языка"""
    user_id = callback_query.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    await callback_query.answer()

    text = (
        f"{TRANSLATIONS[lang]['settings_title']} › {TRANSLATIONS[lang]['language']}\n\n"
        f"{TRANSLATIONS[lang]['current_settings']}:\n"
        f"🌐 Язык: {lang.upper()}\n\n"
        f"{TRANSLATIONS[lang]['language_title']}")

    await callback_query.message.edit_text(
        text,
        reply_markup=get_language_keyboard(lang),
        parse_mode=ParseMode.HTML)


@dp.callback_query_handler(depth_cb.filter())
async def process_depth_selection(callback_query: CallbackQuery,
                                  callback_data: dict, state: FSMContext):
    """Обработка выбора глубины поиска"""
    user_id = callback_query.from_user.id
    value = callback_data["value"]

    if value == "custom":
        lang = db.get_user_settings(user_id)["language"]
        await callback_query.message.edit_text(
            TRANSLATIONS[lang]["enter_custom_days"], parse_mode=ParseMode.HTML)
        await SearchStates.waiting_for_custom_days.set()
        return

    days = int(value)
    db.update_days_back(user_id, days)

    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    # Остаемся в том же меню
    text = (
        f"{TRANSLATIONS[lang]['settings_title']} › {TRANSLATIONS[lang]['depth']}\n\n"
        f"{TRANSLATIONS[lang]['current_settings']}:\n"
        f"📅 {TRANSLATIONS[lang]['search_depth']}: {days} дн.\n\n"
        f"{TRANSLATIONS[lang]['settings_desc']}")

    await callback_query.message.edit_text(text,
                                           reply_markup=get_depth_keyboard(
                                               lang, days),
                                           parse_mode=ParseMode.HTML)


@dp.message_handler(state=SearchStates.waiting_for_custom_days)
async def process_custom_days(message: types.Message, state: FSMContext):
    """Обработка пользовательского значения дней"""
    user_id = message.from_user.id

    try:
        days = int(message.text.strip())
        if days < 1 or days > 365:
            raise ValueError
    except ValueError:
        lang = db.get_user_settings(user_id)["language"]
        await message.answer(TRANSLATIONS[lang]["invalid_days"])
        return

    db.update_days_back(user_id, days)
    await state.finish()

    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    # Возвращаемся в меню настроек
    text = (
        f"{TRANSLATIONS[lang]['settings_title']} › {TRANSLATIONS[lang]['depth']}\n\n"
        f"{TRANSLATIONS[lang]['current_settings']}:\n"
        f"📅 {TRANSLATIONS[lang]['search_depth']}: {days} дн.\n\n"
        f"{TRANSLATIONS[lang]['settings_desc']}")

    await message.answer(text,
                         reply_markup=get_depth_keyboard(lang, days),
                         parse_mode=ParseMode.HTML)


@dp.callback_query_handler(currency_cb.filter())
async def process_currency_selection(callback_query: CallbackQuery,
                                     callback_data: dict, state: FSMContext):
    """Обработка выбора валюты"""
    user_id = callback_query.from_user.id
    currency = callback_data["value"]

    db.update_currency(user_id, currency)

    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    # Остаемся в том же меню
    text = (
        f"{TRANSLATIONS[lang]['settings_title']} › {TRANSLATIONS[lang]['currency']}\n\n"
        f"{TRANSLATIONS[lang]['current_settings']}:\n"
        f"💰 Валюта: {currency}\n\n"
        f"{TRANSLATIONS[lang]['currency_title']}")

    await callback_query.message.edit_text(text,
                                           reply_markup=get_currency_keyboard(
                                               lang, currency),
                                           parse_mode=ParseMode.HTML)


@dp.callback_query_handler(language_cb.filter())
async def process_language_selection(callback_query: CallbackQuery,
                                     callback_data: dict, state: FSMContext):
    """Обработка выбора языка"""
    user_id = callback_query.from_user.id
    new_lang = callback_data["value"]

    db.update_language(user_id, new_lang)

    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    # Остаемся в том же меню с новым языком
    text = (
        f"{TRANSLATIONS[lang]['settings_title']} › {TRANSLATIONS[lang]['language']}\n\n"
        f"{TRANSLATIONS[lang]['current_settings']}:\n"
        f"🌐 Язык: {lang.upper()}\n\n"
        f"{TRANSLATIONS[lang]['language_title']}")

    await callback_query.message.edit_text(
        text,
        reply_markup=get_language_keyboard(lang),
        parse_mode=ParseMode.HTML)


# ==================== ОСНОВНЫЕ ОБРАБОТЧИКИ ====================


async def show_parallel_animation(message: types.Message, button_name: str,
                                  search_task, lang: str, days_back: int):
    """Улучшенная анимация с максимально частым обновлением (теперь с переводом и правильным отображением времени)"""
    start_time = time.time()
    last_fact_change = time.time()
    current_fact = random.choice(KUFAR_FACTS)
    update_count = 0

    while not search_task.done():
        current_time = time.time()
        elapsed = int(current_time - start_time)

        loading_emoji = LOADING_EMOJIS[update_count % len(LOADING_EMOJIS)]
        update_count += 1

        if current_time - last_fact_change > 7:
            current_fact = random.choice(KUFAR_FACTS)
            last_fact_change = current_time

        # Определяем текст для времени
        if days_back == 1:
            time_text = TRANSLATIONS[lang]["last_24h"]
        else:
            # Во время анимации показываем не дни, а секунды поиска, но используем тот же ключ для совместимости
            time_text = f"⏱️ {TRANSLATIONS[lang]['last_days'].format(days=elapsed)}"

        animation_text = (
            f"🔍 <b>{TRANSLATIONS[lang]['search_results'].format(title=button_name)}</b>\n\n"
            f"{loading_emoji} <i>{TRANSLATIONS[lang]['search_animation']}...</i>\n"
            f"{time_text}\n\n"
            f"📌 <b>{TRANSLATIONS[lang]['did_you_know']}?</b>\n"
            f"{current_fact}")

        try:
            await message.edit_text(animation_text, parse_mode=ParseMode.HTML)
        except Exception:
            pass

        await asyncio.sleep(0.5)

    elapsed = int(time.time() - start_time)
    await message.edit_text(
        f"🔍 <b>{TRANSLATIONS[lang]['search_results'].format(title=button_name)}</b>\n\n"
        f"✅ <b>{TRANSLATIONS[lang]['search_completed']} за {elapsed} сек.!</b>\n"
        f"⏳ {TRANSLATIONS[lang]['loading_results']}...",
        parse_mode=ParseMode.HTML)


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    """Главное меню при старте (убрано декоративное сообщение)"""
    user_id = message.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    welcome_text = (f"✨ <b>{TRANSLATIONS[lang]['welcome']}</b> ✨\n\n"
                    f"📌 <b>{TRANSLATIONS[lang]['features']}</b>\n"
                    f"{TRANSLATIONS[lang]['feature1']}\n"
                    f"{TRANSLATIONS[lang]['feature2']}\n"
                    f"{TRANSLATIONS[lang]['feature3']}\n\n"
                    f"⚡️ {TRANSLATIONS[lang]['choose_action']}")

    main_msg = await message.answer(welcome_text,
                                    reply_markup=get_main_menu_keyboard(lang),
                                    parse_mode=ParseMode.HTML)

    await delete_previous_messages(message.chat.id, main_msg.message_id,
                                   [main_msg.message_id])


@dp.message_handler(commands=["menu"])
async def cmd_menu(message: types.Message):
    """Показывает главное меню"""
    user_id = message.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    main_msg = await message.answer(TRANSLATIONS[lang]["choose_action"],
                                    reply_markup=get_main_menu_keyboard(lang),
                                    parse_mode=ParseMode.HTML)

    await delete_previous_messages(message.chat.id, main_msg.message_id,
                                   [main_msg.message_id])


@dp.callback_query_handler(text="back_to_menu", state="*")
async def process_back_to_menu(callback_query: CallbackQuery,
                               state: FSMContext):
    """Возвращает пользователя в главное меню"""
    await state.finish()
    user_id = callback_query.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    welcome_text = (f"✨ <b>{TRANSLATIONS[lang]['welcome']}</b> ✨\n\n"
                    f"📌 <b>{TRANSLATIONS[lang]['features']}</b>\n"
                    f"{TRANSLATIONS[lang]['feature1']}\n"
                    f"{TRANSLATIONS[lang]['feature2']}\n"
                    f"{TRANSLATIONS[lang]['feature3']}\n\n"
                    f"⚡️ {TRANSLATIONS[lang]['choose_action']}")

    await callback_query.message.edit_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard(lang),
        parse_mode=ParseMode.HTML)


@dp.callback_query_handler(search_cb.filter())
async def process_search_callback(callback_query: CallbackQuery,
                                  callback_data: dict, state: FSMContext):
    query_key = callback_data["query_key"]
    search_queries = SEARCH_QUERIES.get(query_key, [query_key])
    button_name = BUTTON_NAMES.get(query_key, query_key)

    user_id = callback_query.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]
    currency = settings["currency"]
    days_back = settings["days_back"]

    await callback_query.answer()

    await callback_query.message.edit_text(
        f"🔍 <b>{TRANSLATIONS[lang]['search_results'].format(title=button_name)}</b>\n\n"
        f"⏳ <i>{TRANSLATIONS[lang]['search_animation']}...</i>",
        parse_mode=ParseMode.HTML)

    try:
        api = KufarAPI()
        await api.__aenter__()
        search_task = asyncio.create_task(
            api.search_ads(search_queries, days_back))

        # Передаем days_back в анимацию
        await show_parallel_animation(callback_query.message, button_name,
                                      search_task, lang, days_back)

        ads = await search_task
        await api.__aexit__(None, None, None)

        db.save_search_history(user_id, button_name, len(ads))

        await update_message_with_results(callback_query.message,
                                          state,
                                          ads,
                                          button_name,
                                          show_source=False,
                                          page=1,
                                          currency=currency,
                                          days_back=days_back)

    except Exception as e:
        logger.error(f"❌ Общая ошибка: {e}", exc_info=True)
        await callback_query.message.edit_text(
            f"{TRANSLATIONS[lang]['search_error']}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 {TRANSLATIONS[lang]['choose_action']}",
            reply_markup=get_main_menu_keyboard(lang),
            parse_mode=ParseMode.HTML)


@dp.callback_query_handler(recent_cb.filter(action="show"))
async def process_recent_callback(callback_query: CallbackQuery,
                                  state: FSMContext):
    user_id = callback_query.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]
    currency = settings["currency"]

    await callback_query.answer()

    await callback_query.message.edit_text(
        f"🔍 <b>{TRANSLATIONS[lang]['recent']}</b>\n\n"
        f"⏳ <i>{TRANSLATIONS[lang]['search_animation']}...</i>",
        parse_mode=ParseMode.HTML)

    try:
        api = KufarAPI()
        await api.__aenter__()
        search_task = asyncio.create_task(api.search_all_ads_recent())

        # Передаем days_back=1 в анимацию
        await show_parallel_animation(callback_query.message,
                                      TRANSLATIONS[lang]["recent"],
                                      search_task, lang, 1)

        ads = await search_task
        await api.__aexit__(None, None, None)

        await update_message_with_results(callback_query.message,
                                          state,
                                          ads,
                                          TRANSLATIONS[lang]["recent"],
                                          show_source=True,
                                          page=1,
                                          currency=currency,
                                          days_back=1)

    except Exception as e:
        logger.error(f"❌ Ошибка при поиске всех объявлений: {e}",
                     exc_info=True)
        await callback_query.message.edit_text(
            f"{TRANSLATIONS[lang]['search_error']}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 {TRANSLATIONS[lang]['choose_action']}",
            reply_markup=get_main_menu_keyboard(lang),
            parse_mode=ParseMode.HTML)


@dp.callback_query_handler(custom_search_cb.filter(action="start"))
async def process_custom_search_start(callback_query: CallbackQuery,
                                      state: FSMContext):
    """Начало кастомного поиска"""
    user_id = callback_query.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    await callback_query.answer()
    logger.info("🔍 Начало кастомного поиска")

    await SearchStates.waiting_for_query.set()

    async with state.proxy() as data:
        data['message_id'] = callback_query.message.message_id
        data['chat_id'] = callback_query.message.chat.id

    # Используем перевод для подсказки поиска
    await callback_query.message.edit_text(
        TRANSLATIONS[lang]["custom_search_prompt"],
        reply_markup=get_back_keyboard(lang),
        parse_mode=ParseMode.HTML)


@dp.message_handler(state=SearchStates.waiting_for_query,
                    content_types=types.ContentTypes.TEXT)
async def process_custom_search_query(message: types.Message,
                                      state: FSMContext):
    """Обработка введенного запроса"""
    user_id = message.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]
    currency = settings["currency"]
    days_back = settings["days_back"]

    search_query = message.text.strip()
    logger.info(f"📝 Получен запрос от пользователя: '{search_query}'")

    if not search_query:
        await message.answer(f"❌ <b>{TRANSLATIONS[lang]['invalid_days']}</b>",
                             reply_markup=get_back_keyboard(lang),
                             parse_mode=ParseMode.HTML)
        return

    async with state.proxy() as data:
        original_message_id = data.get('message_id')
        chat_id = data.get('chat_id')

    logger.info(
        f"📦 Оригинальное сообщение ID: {original_message_id}, Chat ID: {chat_id}"
    )

    await state.finish()
    await message.delete()

    try:
        original_message = await bot.edit_message_text(
            chat_id=chat_id,
            message_id=original_message_id,
            text=
            f"🔍 <b>{TRANSLATIONS[lang]['search_results'].format(title=search_query)}</b>\n\n"
            f"⏳ <i>{TRANSLATIONS[lang]['search_animation']}...</i>",
            parse_mode=ParseMode.HTML)
        logger.info("✅ Оригинальное сообщение обновлено")
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении сообщения: {e}")
        original_message = await bot.send_message(
            chat_id,
            f"🔍 <b>{TRANSLATIONS[lang]['search_results'].format(title=search_query)}</b>\n\n"
            f"⏳ <i>{TRANSLATIONS[lang]['search_animation']}...</i>",
            parse_mode=ParseMode.HTML)
        logger.info("✅ Отправлено новое сообщение")

    try:
        api = KufarAPI()
        await api.__aenter__()
        search_task = asyncio.create_task(
            api.search_ads([search_query], days_back))

        # Передаем days_back в анимацию
        await show_parallel_animation(original_message, f"'{search_query}'",
                                      search_task, lang, days_back)

        ads = await search_task
        await api.__aexit__(None, None, None)

        logger.info(f"📊 Найдено {len(ads)} объявлений")

        db.save_search_history(user_id, search_query, len(ads))

        await update_message_with_results(original_message,
                                          state,
                                          ads,
                                          search_query,
                                          show_source=False,
                                          page=1,
                                          currency=currency,
                                          days_back=days_back)

    except Exception as e:
        logger.error(f"❌ Ошибка при кастомном поиске: {e}", exc_info=True)
        await original_message.edit_text(
            f"{TRANSLATIONS[lang]['search_error']}",
            reply_markup=get_main_menu_keyboard(lang),
            parse_mode=ParseMode.HTML)


@dp.callback_query_handler(stats_cb.filter())
async def process_stats_callback(callback_query: CallbackQuery,
                                 callback_data: dict):
    """Обработчик статистики"""
    query_key = callback_data["query_key"]
    user_id = callback_query.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]
    currency = settings["currency"]

    await callback_query.answer()

    if query_key == "all":
        await callback_query.message.edit_text(
            f"📊 <b>{TRANSLATIONS[lang]['stats']}</b>\n\n"
            f"Нажмите на любой бренд, чтобы увидеть детальную информацию.",
            reply_markup=get_stats_keyboard(lang),
            parse_mode=ParseMode.HTML)
        return

    search_queries = SEARCH_QUERIES.get(query_key, [query_key])
    button_name = BUTTON_NAMES.get(query_key, query_key)
    icon = get_brand_icon(button_name)

    await callback_query.message.edit_text(
        TRANSLATIONS[lang]["analysing_data"].format(icon=icon,
                                                    brand_name=button_name),
        parse_mode=ParseMode.HTML)

    try:
        stats = await calculate_brand_statistics(search_queries, currency)

        if stats["total"] == 0:
            stats_text = (
                f"{TRANSLATIONS[lang]['stats_for_brand'].format(icon=icon, brand_name=button_name)}\n\n"
                f"{TRANSLATIONS[lang]['no_data_30_days']}")
        else:
            stats_text = (
                f"{TRANSLATIONS[lang]['stats_for_brand'].format(icon=icon, brand_name=button_name)}\n\n"
                f"{TRANSLATIONS[lang]['total_ads'].format(count=stats['total'])}\n"
                f"{TRANSLATIONS[lang]['per_week'].format(count=stats['week'])}\n"
                f"{TRANSLATIONS[lang]['avg_price'].format(price=format(stats['avg_price'], '.2f'), currency=currency)}\n"
                f"{TRANSLATIONS[lang]['max_price'].format(price=format(stats['max_price'], '.2f'), currency=currency)}\n"
                f"{TRANSLATIONS[lang]['min_price'].format(price=format(stats['min_price'], '.2f'), currency=currency)}\n\n"
                f"{TRANSLATIONS[lang]['stats_period']}")

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton(text=TRANSLATIONS[lang]["back_to_brand_list"],
                                 callback_data=stats_cb.new(query_key="all")))
        keyboard.add(
            InlineKeyboardButton(text=TRANSLATIONS[lang]["main_menu"],
                                 callback_data="back_to_menu"))

        await callback_query.message.edit_text(stats_text,
                                               reply_markup=keyboard,
                                               parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"❌ Ошибка при расчете статистики: {e}", exc_info=True)
        await callback_query.message.edit_text(
            TRANSLATIONS[lang]["error_occurred"],
            reply_markup=get_main_menu_keyboard(lang),
            parse_mode=ParseMode.HTML)


@dp.callback_query_handler()
async def debug_all_callbacks(callback_query: CallbackQuery):
    """Отлавливает все callback запросы для отладки"""
    await callback_query.answer()
    logger.info(f"🔍 ПОЛУЧЕН CALLBACK: data = '{callback_query.data}'")

    if callback_query.data == "noop":
        await callback_query.answer("Вы здесь", show_alert=False)
    else:
        logger.info(f"⚠️ Неизвестный callback: {callback_query.data}")


@dp.message_handler()
async def handle_unknown(message: types.Message):
    """Обработчик неизвестных команд"""
    user_id = message.from_user.id
    settings = db.get_user_settings(user_id)
    lang = settings["language"]

    sent_message = await message.answer(
        f"❓ <b>{TRANSLATIONS[lang]['unknown']}</b>",
        reply_markup=get_main_menu_keyboard(lang),
        parse_mode=ParseMode.HTML)
    await delete_previous_messages(message.chat.id, sent_message.message_id)


if __name__ == "__main__":
    print("=" * 70)
    print("🚀 KUFAR SEARCH BOT С НАСТРОЙКАМИ (ФИНАЛЬНАЯ ВЕРСИЯ)")
    print("=" * 70)
    print(f"📅 Поиск за последние {DEFAULT_DAYS_BACK} дней")
    print("⏰ Время: МСК (UTC+3)")
    print("💰 Мультивалютность: BYN/USD/EUR/RUB/UAH")
    print("🌐 Поддержка языков: RU/BE/EN/UK/DE")
    print(f"🔍 Кнопок в меню: {len(SEARCH_QUERIES)} + 4 доп. кнопки")
    print("🎨 Кастомные обложки для брендов")
    print("📊 Статистика по каждому бренду")
    print("📄 Пагинация результатов")
    print("⚡ Улучшенная анимация с переводом")
    print(f"📚 {len(KUFAR_FACTS)} фактов о Kufar")
    print("=" * 70)
    executor.start_polling(dp, skip_updates=True)
