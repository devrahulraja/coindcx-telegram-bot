from flask import Flask
from threading import Thread
import time
import requests
from telegram import Bot, Update
from telegram.ext import CommandHandler, Updater, CallbackContext

TELEGRAM_TOKEN = 'YOUR_BOT_TOKEN'  # Replace with your real bot token
bot = Bot(token=TELEGRAM_TOKEN)
updater = Updater(token=TELEGRAM_TOKEN)
dispatcher = updater.dispatcher

alerts = []  # [{chat_id, symbol, condition, target}]

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Welcome to CoinDCX INR Alert Bot!\n\nCommands:\n/set SYMBOL >=|<= PRICE\n/price SYMBOLINR\nExample: /set VIBINR >= 2")

def set_alert(update: Update, context: CallbackContext):
    try:
        symbol = context.args[0].upper()
        cond = context.args[1]
        price = float(context.args[2])
        if cond not in ['>=', '<=']:
            update.message.reply_text("❌ Invalid operator. Use >= or <=")
            return
        alerts.append({
            "chat_id": update.message.chat_id,
            "symbol": symbol,
            "condition": cond,
            "target": price
        })
        update.message.reply_text(f"✅ Alert set: {symbol} {cond} ₹{price}")
    except Exception as e:
        update.message.reply_text("❌ Usage: /set SYMBOL >=|<= PRICE\nExample: /set VIBINR >= 2")

def get_price(update: Update, context: CallbackContext):
    try:
        symbol = context.args[0].upper()
        res = requests.get("https://public.coindcx.com/market_data/ticker").json()
        data = next((x for x in res if x["market"] == symbol), None)
        if data:
            update.message.reply_text(f"📊 {symbol} price: ₹{data['last_price']}")
        else:
            update.message.reply_text(f"❌ Symbol {symbol} not found.")
    except Exception as e:
        update.message.reply_text("❌ Usage: /price SYMBOLINR\nExample: /price VIBINR")

def check_alerts():
    while True:
        try:
            res = requests.get("https://public.coindcx.com/market_data/ticker").json()
            for alert in alerts:
                data = next((x for x in res if x["market"] == alert["symbol"]), None)
                if not data:
                    continue
                price = float(data["last_price"])
                if alert["condition"] == "<=" and price <= alert["target"]:
                    bot.send_message(chat_id=alert["chat_id"], text=f"📉 {alert['symbol']} = ₹{price} (<= ₹{alert['target']})")
                    alerts.remove(alert)
                elif alert["condition"] == ">=" and price >= alert["target"]:
                    bot.send_message(chat_id=alert["chat_id"], text=f"📈 {alert['symbol']} = ₹{price} (>= ₹{alert['target']})")
                    alerts.remove(alert)
        except Exception as e:
            print("Error in alert check:", e)
        time.sleep(30)

# Flask app to keep Render alive
app = Flask(__name__)
@app.route('/')
def home():
    return "✅ Bot is running!", 200

def run_bot():
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("set", set_alert))
    dispatcher.add_handler(CommandHandler("price", get_price))
    updater.start_polling()
    check_alerts()  # Keeps checking in this thread

# Start everything
Thread(target=run_bot).start()
