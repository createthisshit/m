import logging
import sys
import uuid
import psycopg2
import hashlib
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web, ClientSession
from urllib.parse import urlencode
import traceback
import asyncio
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)
logger.info("Начало выполнения скрипта")

# Настройки для каждого бота
BOTS = {
    "bot1": {
        "TOKEN": "7669060547:AAF1zdVIBcmmFKQGhQ7UGUT8foFKW4EBVxs",
        "YOOMONEY_WALLET": "4100118178122985",
        "NOTIFICATION_SECRET": "CoqQlgE3E5cTzyAKY1LSiLU1",
        "PRIVATE_CHANNEL_ID": -1002640947060
    },
    "bot2": {
        "TOKEN": "8173622705:AAE88BPX5k1mHuwFFBlWJS8ixxa36EmuCC0",  # Замени на реальный токен
        "YOOMONEY_WALLET": "4100118178122985",
        "NOTIFICATION_SECRET": "CoqQlgE3E5cTzyAKY1LSiLU1",
        "PRIVATE_CHANNEL_ID": -1002609563244
    }
}

SAVE_PAYMENT_PATH = "/save_payment"
YOOMONEY_NOTIFY_PATH = "/yoomoney_notify"
DB_CONNECTION = "postgresql://postgres.bdjjtisuhtbrogvotves:Alex4382!@aws-0-eu-north-1.pooler.supabase.com:6543/postgres"
HOST_URL = "https://favourite-brinna-createthisshit-eca5920c.koyeb.app"  # Замени на реальный домен Koyeb, например, https://<your-service-name>.koyeb.app

# Инициализация ботов
bots = {}
dispatchers = {}
for bot_id, config in BOTS.items():
    try:
        logger.info(f"Попытка инициализации бота {bot_id}")
        bots[bot_id] = Bot(token=config["TOKEN"])
        storage = MemoryStorage()
        dispatchers[bot_id] = Dispatcher(bots[bot_id], storage=storage)
        logger.info(f"Бот {bot_id} и диспетчер успешно инициализированы")
    except Exception as e:
        logger.error(f"Ошибка инициализации бота {bot_id}: {e}")
        sys.exit(1)

# Инициализация PostgreSQL
def init_postgres_db():
    try:
        conn = psycopg2.connect(DB_CONNECTION)
        c = conn.cursor()
        for bot_id in BOTS:
            c.execute(f'''CREATE TABLE IF NOT EXISTS payments_{bot_id}
                         (label TEXT PRIMARY KEY, user_id TEXT, status TEXT)''')
        conn.commit()
        conn.close()
        logger.info("PostgreSQL база данных успешно инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации PostgreSQL: {e}")
        sys.exit(1)

init_postgres_db()

# Обработчики команд для каждого бота
for bot_id, dp in dispatchers.items():
    @dp.message_handler(commands=['start'])
    async def start_command(message: types.Message, bot_id=bot_id):
        try:
            user_id = str(message.from_user.id)
            logger.info(f"[{bot_id}] Получена команда /start от user_id={user_id}")
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton(text="Пополнить", callback_data=f"pay_{bot_id}"))
            welcome_text = (
                "Тариф: фулл\n"
                "Стоимость: 2.00 🇷🇺RUB\n"
                "Срок действия: 1 месяц\n\n"
                "Вы получите доступ к следующим ресурсам:\n"
                "• Мой кайф (канал)"
            )
            await message.answer(welcome_text, reply_markup=keyboard)
            logger.info(f"[{bot_id}] Отправлен ответ на /start для user_id={user_id}")
        except Exception as e:
            logger.error(f"[{bot_id}] Ошибка в обработчике /start: {e}")
            await message.answer("Произошла ошибка, попробуйте позже.")

    @dp.message_handler(commands=['pay'])
    @dp.callback_query_handler(lambda c: c.data == f"pay_{bot_id}")
    async def pay_command(message_or_callback: types.Message | types.CallbackQuery, bot_id=bot_id):
        try:
            if isinstance(message_or_callback, types.Message):
                user_id = str(message_or_callback.from_user.id)
                chat_id = message_or_callback.chat.id
            else:
                user_id = str(message_or_callback.from_user.id)
                chat_id = message_or_callback.message.chat.id

            logger.info(f"[{bot_id}] Получена команда /pay от user_id={user_id}")

            # Создание платёжной ссылки
            payment_label = str(uuid.uuid4())
            config = BOTS[bot_id]
            payment_params = {
                "quickpay-form": "shop",
                "paymentType": "AC",
                "targets": f"Оплата подписки для user_id={user_id}",
                "sum": 2.00,
                "label": payment_label,
                "receiver": config["YOOMONEY_WALLET"],
                "successURL": f"https://t.me/{(await bots[bot_id].get_me()).username}"
            }
            payment_url = f"https://yoomoney.ru/quickpay/confirm.xml?{urlencode(payment_params)}"
            
            # Сохранение label:user_id в PostgreSQL
            conn = psycopg2.connect(DB_CONNECTION)
            c = conn.cursor()
            c.execute(f"INSERT INTO payments_{bot_id} (label, user_id, status) VALUES (%s, %s, %s)",
                      (payment_label, user_id, "pending"))
            conn.commit()
            conn.close()
            logger.info(f"[{bot_id}] Сохранено в PostgreSQL: label={payment_label}, user_id={user_id}")
            
            # Отправка label:user_id на /save_payment
            async with ClientSession() as session:
                try:
                    save_payment_url = f"{HOST_URL}{SAVE_PAYMENT_PATH}/{bot_id}"
                    logger.info(f"[{bot_id}] Отправка запроса на {save_payment_url} для label={payment_label}, user_id={user_id}")
                    async with session.post(save_payment_url, json={"label": payment_label, "user_id": user_id}) as response:
                        response_text = await response.text()
                        logger.info(f"[{bot_id}] Ответ от /save_payment: status={response.status}, text={response_text}")
                        if response.status == 200:
                            logger.info(f"[{bot_id}] label={payment_label} сохранён на /save_payment для user_id={user_id}")
                        else:
                            logger.error(f"[{bot_id}] Ошибка сохранения на /save_payment: status={response.status}, text={response_text}")
                            await bots[bot_id].send_message(chat_id, "Ошибка сервера, попробуйте позже.")
                            return
                except Exception as e:
                    logger.error(f"[{bot_id}] Ошибка связи с /save_payment: {e}")
                    await bots[bot_id].send_message(chat_id, "Ошибка сервера, попробуйте позже.")
                    return
            
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton(text="Оплатить", url=payment_url))
            await bots[bot_id].send_message(chat_id, "Перейдите по ссылке для оплаты 2 рублей:", reply_markup=keyboard)
            logger.info(f"[{bot_id}] Отправлена ссылка на оплату для user_id={user_id}, label={payment_label}")
        except Exception as e:
            logger.error(f"[{bot_id}] Ошибка в обработчике /pay: {e}\n{traceback.format_exc()}")
            await bots[bot_id].send_message(chat_id, "Произошла ошибка при создании платежа, попробуйте позже.")

# Проверка подлинности YooMoney уведомления
def verify_yoomoney_notification(data, bot_id):
    config = BOTS[bot_id]
    params = [
        data.get("notification_type", ""),
        data.get("operation_id", ""),
        str(data.get("amount", "")),
        data.get("currency", ""),
        data.get("datetime", ""),
        data.get("sender", ""),
        data.get("codepro", ""),
        config["NOTIFICATION_SECRET"],
        data.get("label", "")
    ]
    sha1_hash = hashlib.sha1("&".join(params).encode()).hexdigest()
    return sha1_hash == data.get("sha1_hash", "")

# Создание уникальной одноразовой инвайт-ссылки
async def create_unique_invite_link(bot_id, user_id):
    try:
        config = BOTS[bot_id]
        invite_link = await bots[bot_id].create_chat_invite_link(
            chat_id=config["PRIVATE_CHANNEL_ID"],
            member_limit=1,
            name=f"Invite for user_{user_id}"
        )
        logger.info(f"[{bot_id}] Создана инвайт-ссылка для user_id={user_id}")
        return invite_link.invite_link
    except Exception as e:
        logger.error(f"[{bot_id}] Ошибка создания инвайт-ссылки: {e}")
        return None

# Обработчик YooMoney уведомлений
async def handle_yoomoney_notify(request, bot_id):
    try:
        data = await request.post()
        logger.info(f"[{bot_id}] Получено YooMoney уведомление: {dict(data)}")
        
        if not verify_yoomoney_notification(data, bot_id):
            logger.error(f"[{bot_id}] Неверный sha1_hash в YooMoney уведомлении")
            return web.Response(status=400, text="Invalid hash")
        
        label = data.get("label")
        if not label:
            logger.error(f"[{bot_id}] Отсутствует label в YooMoney уведомлении")
            return web.Response(status=400, text="Missing label")
        
        if data.get("notification_type") in ["p2p-incoming", "card-incoming"]:
            conn = psycopg2.connect(DB_CONNECTION)
            c = conn.cursor()
            c.execute(f"SELECT user_id FROM payments_{bot_id} WHERE label = %s", (label,))
            result = c.fetchone()
            if result:
                user_id = result[0]
                c.execute(f"UPDATE payments_{bot_id} SET status = %s WHERE label = %s", ("success", label))
                conn.commit()
                await bots[bot_id].send_message(user_id, "Оплата успешно получена! Доступ к каналу активирован.")
                invite_link = await create_unique_invite_link(bot_id, user_id)
                if invite_link:
                    await bots[bot_id].send_message(user_id, f"Присоединяйтесь к приватному каналу: {invite_link}")
                    logger.info(f"[{bot_id}] Успешная транзакция и отправка инвайт-ссылки для label={label}, user_id={user_id}")
                else:
                    await bots[bot_id].send_message(user_id, "Ошибка создания ссылки на канал. Свяжитесь с поддержкой.")
                    logger.error(f"[{bot_id}] Не удалось создать инвайт-ссылку для user_id={user_id}")
            else:
                logger.error(f"[{bot_id}] Label {label} не найден в базе")
            conn.close()
        
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"[{bot_id}] Ошибка обработки YooMoney уведомления: {e}\n{traceback.format_exc()}")
        return web.Response(status=500)

# Обработчик сохранения label:user_id
async def handle_save_payment(request, bot_id):
    try:
        data = await request.json()
        label = data.get("label")
        user_id = data.get("user_id")
        logger.info(f"[{bot_id}] Получен запрос на /save_payment: label={label}, user_id={user_id}")
        if not label or not user_id:
            logger.error(f"[{bot_id}] Отсутствует label или user_id в запросе")
            return web.Response(status=400, text="Missing label or user_id")
        
        conn = psycopg2.connect(DB_CONNECTION)
        c = conn.cursor()
        c.execute(f"INSERT INTO payments_{bot_id} (label, user_id, status) VALUES (%s, %s, %s) ON CONFLICT (label) DO UPDATE SET user_id = %s, status = %s",
                  (label, user_id, "pending", user_id, "pending"))
        conn.commit()
        conn.close()
        logger.info(f"[{bot_id}] Сохранено: label={label}, user_id={user_id}")
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"[{bot_id}] Ошибка сохранения payment: {e}\n{traceback.format_exc()}")
        return web.Response(status=500)

# Настройка веб-сервера
app = web.Application()
for bot_id in BOTS:
    app.router.add_post(f"{YOOMONEY_NOTIFY_PATH}/{bot_id}", lambda request, bot_id=bot_id: handle_yoomoney_notify(request, bot_id))
    app.router.add_post(f"{SAVE_PAYMENT_PATH}/{bot_id}", lambda request, bot_id=bot_id: handle_save_payment(request, bot_id))

# Запуск polling для всех ботов
async def start_polling():
    logger.info("Запуск polling для всех ботов")
    tasks = []
    for bot_id, dp in dispatchers.items():
        async def poll(dp, bot_id):
            attempt = 1
            while True:
                try:
                    logger.info(f"[{bot_id}] Попытка {attempt}: Очистка сессии и пропуск старых обновлений")
                    await bots[bot_id].delete_webhook()  # Очистка вебхуков
                    await dp.skip_updates()
                    logger.info(f"[{bot_id}] Попытка {attempt}: Запуск polling")
                    await dp.start_polling(timeout=20)
                    logger.info(f"[{bot_id}] Polling успешно запущен")
                    break
                except Exception as e:
                    if "Terminated by other getupdates request" in str(e):
                        logger.warning(f"[{bot_id}] Обнаружен конфликт getUpdates, попытка очистки сессии")
                        await bots[bot_id].delete_webhook()
                        await asyncio.sleep(2)
                    else:
                        logger.error(f"[{bot_id}] Попытка {attempt}: Ошибка запуска polling: {e}\n{traceback.format_exc()}")
                    logger.info(f"[{bot_id}] Повторная попытка через 5 секунд...")
                    await asyncio.sleep(5)
                    attempt += 1
                    if attempt > 5:
                        logger.error(f"[{bot_id}] Превышено количество попыток запуска polling")
                        raise Exception(f"[{bot_id}] Не удалось запустить polling")
        tasks.append(asyncio.create_task(poll(dp, bot_id)))
    await asyncio.gather(*tasks)

# Запуск polling и веб-сервера
async def main():
    try:
        # Запускаем polling в отдельной задаче
        asyncio.create_task(start_polling())
        # Запускаем веб-сервер
        logger.info("Инициализация веб-сервера")
        port = int(os.getenv("PORT", 8000))  # Koyeb использует 8000
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"Веб-сервер запущен на порту {port}")
        # Держим приложение работающим
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {e}\n{traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
