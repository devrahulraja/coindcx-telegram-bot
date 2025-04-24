import json, os, requests
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackContext, filters, CallbackQueryHandler

TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "alerts.json"

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({}, f)

def load_alerts():
    with open(DATA_FILE) as f:
        return json.load(f)

def save_alerts(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_live_price(symbol):
    try:
        data = requests.get("https://api.coindcx.com/exchange/ticker").json()
        for entry in data:
            if entry["market"] == symbol:
                return float(entry["last_price"])
    except Exception:
        return None

async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("📈 Track a Coin", callback_data="track")],
        [InlineKeyboardButton("📋 My Alerts", callback_data="alerts")]
    ]
    await update.message.reply_text("Welcome to CoinDCX INR Alert Bot!", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data == "track":
        await query.message.reply_text("Send coin symbol (e.g., BTCINR):")
        context.user_data["step"] = "awaiting_coin"
    elif query.data == "alerts":
        alerts = load_alerts().get(str(query.from_user.id), [])
        if alerts:
            text = "\n".join([f'{a["coin"]} {a["condition"]} {a["target"]}' for a in alerts])
        else:
            text = "No alerts set."
        await query.message.reply_text(text)

async def handle_text(update: Update, context: CallbackContext):
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip().upper()
    step = context.user_data.get("step")

    if step == "awaiting_coin":
        context.user_data["coin"] = text
        context.user_data["step"] = "awaiting_condition"
        keyboard = [
            [InlineKeyboardButton(">= (Above)", callback_data=">=")],
            [InlineKeyboardButton("<= (Below)", callback_data="<=")]
        ]
        await update.message.reply_text(f"Selected {text}. Choose condition:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif step == "awaiting_target":
        try:
            target = float(text)
            alert = {
                "coin": context.user_data["coin"],
                "condition": context.user_data["condition"],
                "target": target
            }
            data = load_alerts()
            data.setdefault(user_id, []).append(alert)
            save_alerts(data)
            await update.message.reply_text("✅ Alert saved.")
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Try again.")
        context.user_data.clear()

async def condition_choice(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["condition"] = query.data
    context.user_data["step"] = "awaiting_target"
    await query.message.reply_text("Enter your target price:")

def check_alerts(app):
    data = load_alerts()
    for user_id, alerts in data.items():
        to_notify = []
        for alert in alerts:
            price = get_live_price(alert["coin"])
            if price is None:
                continue
            if alert["condition"] == ">=" and price >= alert["target"]:
                to_notify.append((alert, price))
            elif alert["condition"] == "<=" and price <= alert["target"]:
                to_notify.append((alert, price))
        for alert, price in to_notify:
            app.bot.send_message(chat_id=user_id,
                text=f"🔔 {alert['coin']} is now {price:.2f} (matched {alert['condition']} {alert['target']})")

def run():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(track|alerts)$"))
    app.add_handler(CallbackQueryHandler(condition_choice, pattern="^(>=|<=)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: check_alerts(app), 'interval', seconds=30)
    scheduler.start()

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    run()
