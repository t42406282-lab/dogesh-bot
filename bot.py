import os
import logging
import asyncio
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Config
TELEGRAM_TOKEN = ***"TELEGRAM_TOKEN")
NVIDIA_API_KEY = ***"NVIDIA_API_KEY")
NVIDIA_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
PORT = int(***("PORT", "10000"))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful, friendly AI assistant called Dogesh Bot. 
You speak in Hinglish (mix of Hindi/Urdu and English). 
You are casual, fun, and helpful. Keep responses concise unless asked for detail."""


# Simple HTTP health server
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Dogesh Bot running! \xf0\x9f\x90\x95")
    
    def log_message(self, format, *args):
        pass


def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"Health server on port {PORT}")
    server.serve_forever()


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


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Dogesh Bot active hai!\nKuch bhi puchho - jawab milega!\nPowered by NVIDIA Nemotron"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    user_name = update.message.from_user.first_name
    logger.info(f"[{user_name}]: {user_msg}")
    
    try:
        await update.message.chat.send_action("typing")
        reply = ask_nvidia(user_msg)
        logger.info(f"[Bot reply]: {reply[:80]}...")
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Message handler error: {e}")
        try:
            await update.message.reply_text("Error aaya hai. Dobara try karo.")
        except:
            pass


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Bot error: {context.error}")
    if update and update.message:
        try:
            await update.message.reply_text("Error aaya hai.")
        except:
            pass


def run_telegram_bot():
    logger.info("Starting Telegram bot...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    logger.info("Bot polling started!")
    app.run_polling(drop_pending_updates=True, stop_signals=None)


if __name__ == "__main__":
    logger.info(f"TOKEN present: {bool(TELEGRAM_TOKEN)}")
    logger.info(f"NVIDIA key present: {bool(NVIDIA_API_KEY)}")
    
    # Start health server
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # Run bot (blocking)
    run_telegram_bot()
