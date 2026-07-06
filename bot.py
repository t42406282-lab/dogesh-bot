import os
import logging
import asyncio
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Config
TELEGRAM_TOKEN = ***"TELEGRAM_TOKEN")
NVIDIA_API_KEY = ***"NVIDIA_API_KEY")
NVIDIA_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful, friendly AI assistant. You speak in a mix of Hindi/Urdu and English (Hinglish) naturally. 
You are casual, fun, and helpful. Keep responses concise unless asked for detail.
Your name is Dogesh Bot. 🦀"""

# Flask app for Render health checks
flask_app = Flask(__name__)

@flask_app.route("/")
def health():
    return "Dogesh Bot is running! 🦀", 200

@flask_app.route("/health")
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
        "🐕 Dogesh Bot active hai bhai!\n\nKuch bhi puchho — jawab milega!\n\nPowered by NVIDIA Nemotron 🚀"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    user_name = update.message.from_user.first_name
    logger.info(f"[{user_name}]: {user_msg}")
    
    try:
        await update.message.chat.send_action("typing")
        reply = ask_nvidia(user_msg)
        logger.info(f"[Bot]: {reply[:100]}...")
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Handle message error: {e}")
        await update.message.reply_text("❌ Kuch gadbad ho gaya. Dobara try karo.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.message:
        try:
            await update.message.reply_text("❌ Error aaya hai. Dobara try karo.")
        except:
            pass


def run_bot():
    """Run the Telegram bot with its own event loop in a separate thread"""
    logger.info("🤖 Telegram bot thread starting...")
    logger.info(f"Token present: {bool(TELEGRAM_TOKEN)}")
    logger.info(f"NVIDIA key present: {bool(NVIDIA_API_KEY)}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_error_handler(error_handler)
        
        logger.info("🤖 Bot polling starting...")
        app.run_polling(
            drop_pending_updates=True,
            close_loop=False,
            stop_signals=None  # Don't register signal handlers in thread
        )
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        import traceback
        traceback.print_exc()


# Start bot thread at import time
logger.info("🚀 Module loaded. Starting bot thread...")
if TELEGRAM_TOKEN and NVIDIA_API_KEY:
    t = threading.Thread(target=run_bot, daemon=True, name="telegram-bot")
    t.start()
    logger.info("✅ Bot thread started")
else:
    logger.error(f"❌ Missing env vars - TOKEN: {bool(TELEGRAM_TOKEN)}, NVIDIA: {bool(NVIDIA_API_KEY)}")
