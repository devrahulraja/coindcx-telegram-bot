import os
import time
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

BOT_TOKEN = os.getenv('BOT_TOKEN')  # Set this in Render environment

if not BOT_TOKEN:
    raise EnvironmentError("BOT_TOKEN environment variable not set")

app = Flask(__name__)
alerts = {}  # {chat_id: [(symbol, operator, target_price)]}
COINDCX_API_URL = "https://api.coindcx.com/exchange/ticker"

def get_live_price(symbol: str):
    try:
        response = requests.get(COINDCX_API_URL)
        data = response.json()
        for item in data:
            if item["market"] == f"{symbol.upper()}INR":
                return float(item["last_price"])
        return None
    except Exception as e:
        print(f"Error fetching price: {e}")
        return None

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Welcome to the CoinDCX Alert Bot!\n"
        "• Use /set VIBINR >= 2 to set an alert\n"
        "• Use /price VIBINR to check price"
    )

def set_alert(update: Update, context: CallbackContext):
    try:
        symbol = context.args[0].upper()
        operator = context.args[1]
        value = float(context.args[2])
        if operator not in ('>=', '<='):
            raise ValueError("Invalid operator")

        chat_id = update.message.chat_id
        if chat_id not in alerts:
            alerts[chat_id] = []
        alerts[chat_id].append((symbol, operator, value))
        update.message.reply_text(f"✅ Alert set for {symbol} {operator} ₹{value}")
    except:
        update.message.reply_text("❌ Usage: /set SYMBOL >=|<= PRICE")

def get_price(update: Update, context: CallbackContext):
    try:
        symbol = context.args[0].upper()
        price = get_live_price(symbol)
        if price is not None:
            update.message.reply_text(f"💹 {symbol}INR = ₹{price}")
        else:
            update.message.reply_text("❌ Invalid symbol or unable to fetch price.")
    except:
        update.message.reply_text("❌ Usage: /price SYMBOL")

def check_alerts(bot):
    while True:
        for chat_id, user_alerts in list(alerts.items()):
            for alert in user_alerts[:]:
                symbol, operator, target = alert
                price = get_live_price(symbol)
                if price is None:
                    continue
                if (operator == '>=' and price >= target) or (operator == '<=' and price <= target):
                    bot.send_message(chat_id=chat_id, text=f"🚨 {symbol} has hit {operator} ₹{target} (Now ₹{price})")
                    alerts[chat_id].remove(alert)
        time.sleep(30)

def run_bot():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("set", set_alert))
    dp.add_handler(CommandHandler("price", get_price))

    alert_thread = threading.Thread(target=check_alerts, args=(updater.bot,), daemon=True)
    alert_thread.start()

    updater.start_polling()

@app.route('/')
def home():
    return "✅ CoinDCX Alert Bot is running!"

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=5000)
