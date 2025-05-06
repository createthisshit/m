import logging
import sys
import psycopg2
import hashlib
from aiohttp import web
from aiogram import Bot
import traceback

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)
logger.info("Начало выполнения скрипта")

# Настройки
BOT_TOKEN = "7669060547:AAF1zdVIBcmmFKQGhQ7UGUT8foFKW4EBVxs"
YOOMONEY_WALLET = "4100118178122985"
NOTIFICATION_SECRET = "CoqQlgE3E5cTzyAKY1LSiLU1"
WEBHOOK_HOST = "https://favourite-brinna-createthisshit-eca5920c.koyeb.app"
YOOMONEY_NOTIFY_PATH = "/yoomoney_notify"
SAVE_PAYMENT_PATH = "/save_payment"
DB_CONNECTION = "postgresql://postgres.bdjjtisuhtbrogvotves:Alex4382!@aws-0-eu-north-1.pooler.supabase.com:6543/postgres"
PRIVATE_CHANNEL_ID = -1002640947060  # ID твоего канала

# Инициализация бота
bot = Bot(token=BOT_TOKEN)

# Инициализация PostgreSQL
def init_db():
    conn = psycopg2.connect(DB_CONNECTION)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS payments
                 (label TEXT PRIMARY KEY, user_id TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# Проверка подлинности YooMoney уведомления
def verify_yoomoney_notification(data):
    params = [
        data.get("notification_type", ""),
        data.get("operation_id", ""),
        str(data.get("amount", "")),
        data.get("currency", ""),
        data.get("datetime", ""),
        data.get("sender", ""),
        data.get("codepro", ""),
        NOTIFICATION_SECRET,
        data.get("label", "")
    ]
    sha1_hash = hashlib.sha1("&".join(params).encode()).hexdigest()
    return sha1_hash == data.get("sha1_hash", "")

# Создание уникальной одноразовой инвайт-ссылки
async def create_unique_invite_link(user_id):
    try:
        invite_link = await bot.create_chat_invite_link(
            chat_id=PRIVATE_CHANNEL_ID,
            member_limit=1,  # Ограничение на 1 пользователя
            name=f"Invite for user_{user_id}"
        )
        return invite_link.invite_link
    except Exception as e:
        logger.error(f"Ошибка создания инвайт-ссылки: {e}")
        return None

# Обработчик YooMoney уведомлений
async def handle_yoomoney_notify(request):
    try:
        data = await request.post()
        logger.info(f"Получено YooMoney уведомление: {data}")
       
        if not verify_yoomoney_notification(data):
            logger.error("Неверный sha1_hash в YooMoney уведомлении")
            return web.Response(status=400, text="Invalid hash")
       
        label = data.get("label")
        if not label:
            logger.error("Отсутствует label в YooMoney уведомлении")
            return web.Response(status=400, text="Missing label")
       
        # Поддержка p2p-incoming и card-incoming
        if data.get("notification_type") in ["p2p-incoming", "card-incoming"]:
            conn = psycopg2.connect(DB_CONNECTION)
            c = conn.cursor()
            c.execute("SELECT user_id FROM payments WHERE label = %s", (label,))
            result = c.fetchone()
            if result:
                user_id = result[0]
                c.execute("UPDATE payments SET status = %s WHERE label = %s", ("success", label))
                conn.commit()
                await bot.send_message(user_id, "Оплата успешно получена! Доступ к каналу активирован.")
                invite_link = await create_unique_invite_link(user_id)
                if invite_link:
                    await bot.send_message(user_id, f"Присоединяйтесь к приватному каналу: {invite_link}")
                    logger.info(f"Успешная транзакция и отправка инвайт-ссылки для label={label}, user_id={user_id}")
                else:
                    await bot.send_message(user_id, "Ошибка создания ссылки на канал. Свяжитесь с поддержкой.")
                    logger.error(f"Не удалось создать инвайт-ссылку для user_id={user_id}")
            else:
                logger.error(f"Label {label} не найден в базе")
            conn.close()
       
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка обработки YooMoney уведомления: {e}\n{traceback.format_exc()}")
        return web.Response(status=500)

# Обработчик сохранения label:user_id
async def handle_save_payment(request):
    try:
        data = await request.json()
        label = data.get("label")
        user_id = data.get("user_id")
        if not label or not user_id:
            logger.error("Отсутствует label или user_id в запросе")
            return web.Response(status=400, text="Missing label or user_id")
       
        conn = psycopg2.connect(DB_CONNECTION)
        c = conn.cursor()
        c.execute("INSERT INTO payments (label, user_id, status) VALUES (%s, %s, %s) ON CONFLICT (label) DO UPDATE SET user_id = %s, status = %s",
                  (label, user_id, "pending", user_id, "pending"))
        conn.commit()
        conn.close()
        logger.info(f"Сохранено: label={label}, user_id={user_id}")
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка сохранения payment: {e}\n{traceback.format_exc()}")
        return web.Response(status=500)

# Настройка веб-сервера
app = web.Application()
app.router.add_post(YOOMONEY_NOTIFY_PATH, handle_yoomoney_notify)
app.router.add_post(SAVE_PAYMENT_PATH, handle_save_payment)

# Запуск
if __name__ == "__main__":
    logger.info("Инициализация веб-сервера")
    try:
        init_db()
        web.run_app(app, host="0.0.0.0", port=8000)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {e}\n{traceback.format_exc()}")
        sys.exit(1)
