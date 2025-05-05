import logging
import sys
import sqlite3
import hashlib
from aiohttp import web, ClientSession
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
BOT_TOKEN = "7669060547:AAF1zdVIBcmmFKQGhQ7UGUT8foFKW4EBVxs"  # Токен бота (@NewMiraPayBot)
YOOMONEY_WALLET = "4100118178122985"  # Номер кошелька YooMoney (41001...)
NOTIFICATION_SECRET = "CoqQlgE3E5cTzyAKY1LSiLU1"  # Секрет YooMoney
WEBHOOK_HOST = "https://favourite-brinna-createthisshit-eca5920c.koyeb.app"  # URL Koyeb
YOOMONEY_NOTIFY_PATH = "/yoomoney_notify"
SAVE_PAYMENT_PATH = "/save_payment"

# Инициализация SQLite
def init_db():
    conn = sqlite3.connect("payments.db")
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

# Отправка сообщения через Telegram API
async def send_telegram_message(user_id, text):
    async with ClientSession() as session:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": user_id,
            "text": text
        }
        try:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    logger.info(f"Сообщение отправлено user_id={user_id}")
                else:
                    logger.error(f"Ошибка отправки сообщения: {await response.text()}")
        except Exception as e:
            logger.error(f"Ошибка Telegram API: {e}")

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
        
        if data.get("notification_type") == "p2p-incoming" and data.get("status") == "success":
            conn = sqlite3.connect("payments.db")
            c = conn.cursor()
            c.execute("SELECT user_id FROM payments WHERE label = ?", (label,))
            result = c.fetchone()
            if result:
                user_id = result[0]
                c.execute("UPDATE payments SET status = ? WHERE label = ?", ("success", label))
                conn.commit()
                await send_telegram_message(user_id, "Оплата успешно получена! Доступ к каналу активирован.")
                logger.info(f"Успешная транзакция для label={label}, user_id={user_id}")
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
        
        conn = sqlite3.connect("payments.db")
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO payments (label, user_id, status) VALUES (?, ?, ?)",
                  (label, user_id, "pending"))
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
