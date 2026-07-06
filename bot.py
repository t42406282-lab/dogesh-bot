import os
import logging
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful, friendly AI assistant. You speak in a mix of Hindi/Urdu and English (Hinglish) naturally. 
You are casual, fun, and helpful. Keep responses concise unless asked for detail.
Your name is Dogesh Bot. 🦀"""

# Flask app for health checks
app = Flask(__name__)

@app.route("/")
def health():
    return "Dogesh Bot is running! 🦀", 200

@app.route("/health")
def health_check():
    return {"status": "ok", "bot": "running"}, 200


def ask_nvidia(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1024
    }
    try:
        resp = requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"NVIDIA API error: {e}")
        return f"API Error: {str(e)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Dogesh Bot active hai bhai!\n\nKuch bhi puchho — jawab milega!\n\nPowered by NVIDIA Nemotron"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    user_name = update.message.from_user.first_name
    logger.info(f"[{user_name}]: {user_msg}")
    
    await update.message.chat.send_action("typing")
    
    reply = ask_nvidia(user_msg)
    logger.info(f"[Bot]: {reply[:100]}...")
    await update.message.reply_text(reply)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.message:
        await update.message.reply_text("Kuch gadbad ho gaya. Dobara try karo.")


def run_telegram_bot():
    """Run Telegram bot in background thread"""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def start_bot():
        bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        bot_app.add_handler(CommandHandler("start", start))
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        bot_app.add_error_handler(error_handler)
        
        logger.info("Telegram bot starting...")
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        
        # Keep running
        while True:
            await asyncio.sleep(3600)
    
    loop.run_until_complete(start_bot())


# Start Telegram bot when module loads (for gunicorn)
if TELEGRAM_TOKEN and NVIDIA_API_KEY:
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    logger.info("Telegram bot thread started")
else:
    logger.warning("Missing TELEGRAM_TOKEN or NVIDIA_API_KEY - bot not started")
