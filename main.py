import os
import json
import logging
import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from threading import Thread

# Flask app for Render.com
app = Flask(__name__)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# CoinDCX API endpoint
COINDCX_API = "https://api.coindcx.com/exchange/ticker"

# File to store alerts
ALERTS_FILE = "alerts.json"

# Load alerts from file or initialize empty
def load_alerts():
    try:
        if os.path.exists(ALERTS_FILE):
            with open(ALERTS_FILE, "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading alerts from {ALERTS_FILE}: {e}")
        return {}

# Save alerts to file
def save_alerts(alerts):
    try:
        with open(ALERTS_FILE, "w") as f:
            json.dump(alerts, f, indent=4)
        logger.info(f"Alerts saved to {ALERTS_FILE}")
    except Exception as e:
        logger.error(f"Error saving alerts to {ALERTS_FILE}: {e}")

# Fetch coin prices from CoinDCX
def get_coin_prices():
    try:
        response = requests.get(COINDCX_API, timeout=10)
        response.raise_for_status()
        data = response.json()
        # Filter INR pairs and sort by symbol
        inr_pairs = [
            {
                "symbol": item["market"].replace("INR", ""),
                "price": float(item["last_price"]),
            }
            for item in data
            if item["market"].endswith("INR")
        ]
        return sorted(inr_pairs, key=lambda x: x["symbol"])
    except requests.RequestException as e:
        logger.error(f"Error fetching prices from CoinDCX: {e}")
        return []

# Get price for a single coin
def get_single_coin_price(symbol):
    symbol = symbol.upper() + "INR"
    prices = get_coin_prices()
    for coin in prices:
        if coin["symbol"].upper() == symbol.replace("INR", ""):
            return coin["price"]
    return None

# Main menu
def build_main_menu():
    keyboard = [
        [InlineKeyboardButton("Get All Coin Prices", callback_data="all_prices")],
        [InlineKeyboardButton("Get Single Coin Price", callback_data="single_price")],
        [InlineKeyboardButton("Set Price Alert", callback_data="set_alert")],
        [InlineKeyboardButton("View My Alerts", callback_data="view_alerts")],
        [InlineKeyboardButton("Delete Alert", callback_data="delete_alert")],
    ]
    return InlineKeyboardMarkup(keyboard)

# Build coin selection menu
def build_coin_menu():
    prices = get_coin_prices()
    if not prices:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel")]])
    keyboard = [
        [InlineKeyboardButton(coin["symbol"], callback_data=f"coin_{coin['symbol']}")]
        for coin in prices[:50]  # Limit to 50 coins for Telegram button limits
    ]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.reply_text(
            "Welcome to the CoinDCX Price Tracker Bot! Choose an option:",
            reply_markup=build_main_menu(),
        )
        logger.info(f"User {update.effective_user.id} started the bot")
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

# Handle button clicks
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        await query.answer()
        data = query.data
        user_id = str(query.from_user.id)
        logger.info(f"User {user_id} clicked button: {data}")

        if data == "all_prices":
            prices = get_coin_prices()
            if prices:
                message = "Current Coin Prices (INR):\n" + "\n".join(
                    f"{coin['symbol']}: ₹{coin['price']:.2f}" for coin in prices
                )
            else:
                message = "Failed to fetch prices. Try again later."
            await query.message.reply_text(message, reply_markup=build_main_menu())

        elif data == "single_price":
            await query.message.reply_text(
                "Select a coin:", reply_markup=build_coin_menu()
            )

        elif data.startswith("coin_"):
            symbol = data.replace("coin_", "")
            price = get_single_coin_price(symbol)
            if price is not None:
                await query.message.reply_text(
                    f"Current price of {symbol}INR: ₹{price:.2f}",
                    reply_markup=build_main_menu(),
                )
            else:
                await query.message.reply_text(
                    f"Could not find price for {symbol}INR.",
                    reply_markup=build_main_menu(),
                )

        elif data == "set_alert":
            await query.message.reply_text(
                "Select a coin for the alert:", reply_markup=build_coin_menu()
            )
            context.user_data["state"] = "select_coin_alert"

        elif data == "view_alerts":
            alerts = load_alerts()
            user_alerts = alerts.get(user_id, [])
            if user_alerts:
                message = "Your Alerts:\n" + "\n".join(
                    f"{i+1}. {alert['symbol']} {alert['condition']} ₹{alert['price']}"
                    for i, alert in enumerate(user_alerts)
                )
            else:
                message = "You have no alerts set."
            await query.message.reply_text(message, reply_markup=build_main_menu())

        elif data == "delete_alert":
            alerts = load_alerts()
            user_alerts = alerts.get(user_id, [])
            if user_alerts:
                keyboard = [
                    [
                        InlineKeyboardButton(
                            f"{alert['symbol']} {alert['condition']} ₹{alert['price']}",
                            callback_data=f"delete_{i}",
                        )
                    ]
                    for i, alert in enumerate(user_alerts)
                ]
                keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
                await query.message.reply_text(
                    "Select an alert to delete:", reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.message.reply_text(
                    "You have no alerts to delete.", reply_markup=build_main_menu()
                )

        elif data.startswith("delete_"):
            index = int(data.replace("delete_", ""))
            alerts = load_alerts()
            user_alerts = alerts.get(user_id, [])
            if 0 <= index < len(user_alerts):
                deleted_alert = user_alerts.pop(index)
                alerts[user_id] = user_alerts
                save_alerts(alerts)
                await query.message.reply_text(
                    f"Deleted alert: {deleted_alert['symbol']} {deleted_alert['condition']} ₹{deleted_alert['price']}",
                    reply_markup=build_main_menu(),
                )
            else:
                await query.message.reply_text(
                    "Invalid alert selection.", reply_markup=build_main_menu()
                )

        elif data == "cancel":
            await query.message.reply_text(
                "Action cancelled.", reply_markup=build_main_menu()
            )

    except Exception as e:
        logger.error(f"Error in button handler: {e}")
        await query.message.reply_text(
            "An error occurred. Please try again.", reply_markup=build_main_menu()
        )

# Handle text messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    state = context.user_data.get("state")
    logger.info(f"User {user_id} sent message: {text} (state: {state})")

    try:
        if state == "select_coin_alert":
            prices = get_coin_prices()
            symbols = [coin["symbol"].upper() + "INR" for coin in prices]
            if text.upper() in symbols:
                context.user_data["alert_symbol"] = text.upper()
                context.user_data["state"] = "set_alert_condition"
                await update.message.reply_text(
                    f"Enter alert condition for {text} (e.g., >= 2 or <= 3000000):"
                )
            else:
                await update.message.reply_text(
                    "Invalid coin symbol. Select a coin:", reply_markup=build_coin_menu()
                )

        elif state == "set_alert_condition":
            parts = text.split()
            if len(parts) != 2 or parts[0] not in [">=", "<="]:
                raise ValueError("Invalid format")
            condition = parts[0]
            price = float(parts[1])
            symbol = context.user_data["alert_symbol"]
            alerts = load_alerts()
            if user_id not in alerts:
                alerts[user_id] = []
            alerts[user_id].append(
                {"symbol": symbol, "condition": condition, "price": price}
            )
            save_alerts(alerts)
            await update.message.reply_text(
                f"Alert set: {symbol} {condition} ₹{price}",
                reply_markup=build_main_menu(),
            )
            context.user_data.clear()
        else:
            await update.message.reply_text(
                "Please use /start to begin.", reply_markup=build_main_menu()
            )

    except Exception as e:
        logger.error(f"Error in message handler: {e}")
        await update.message.reply_text(
            "Invalid input. Use format: >= 2 or <= 3000000" if state == "set_alert_condition" else "An error occurred."
        )

# Check alerts every minute
async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    try:
        alerts = load_alerts()
        prices = get_coin_prices()
        price_map = {coin["symbol"].upper() + "INR": coin["price"] for coin in prices}
        logger.info("Checking alerts...")

        for user_id, user_alerts in alerts.items():
            for alert in user_alerts:
                symbol = alert["symbol"]
                condition = alert["condition"]
                target_price = alert["price"]
                current_price = price_map.get(symbol)

                if current_price is None:
                    logger.warning(f"No price data for {symbol}")
                    continue

                triggered = False
                if condition == ">=" and current_price >= target_price:
                    triggered = True
                elif condition == "<=" and current_price <= target_price:
                    triggered = True

                if triggered:
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"🚨 Alert: {symbol} is {condition} ₹{target_price}. Current price: ₹{current_price:.2f}",
                        )
                        logger.info(f"Alert triggered for user {user_id}: {symbol} {condition} ₹{target_price}")
                    except Exception as e:
                        logger.error(f"Error sending alert to {user_id}: {e}")
    except Exception as e:
        logger.error(f"Error in check_alerts: {e}")

# Flask route for uptime pings
@app.route("/ping")
def ping():
    logger.info("Ping route accessed")
    return "Bot is alive!", 200

# Run Flask server in a separate thread
def run_flask():
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
        logger.info(f"Flask server running on port {port}")
    except Exception as e:
        logger.error(f"Error running Flask server: {e}")

# Main function
def main():
    try:
        # Start Flask server in a thread
        flask_thread = Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()

        # Telegram bot setup
        token = os.environ.get("BOT_TOKEN")
        if not token:
            logger.error("TELEGRAM_BOT_TOKEN environment variable not set")
            raise ValueError("TELEGRAM_BOT_TOKEN not set")

        # Initialize application
        application = ApplicationBuilder().token(token).build()

        # Verify job queue
        if application.job_queue is None:
            logger.error("Job queue not initialized. Ensure python-telegram-bot[job-queue] is installed")
            raise RuntimeError("Job queue not initialized")
        logger.info("Job queue successfully initialized")

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Schedule alert checks
        application.job_queue.run_repeating(check_alerts, interval=60, first=10)
        logger.info("Alert checking scheduled every 60 seconds")

        # Start bot
        application.run_polling()
        logger.info("Telegram bot polling started")

    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    main()