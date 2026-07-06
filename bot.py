import os
import logging
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful, friendly AI assistant. You speak in a mix of Hindi/Urdu and English (Hinglish) naturally. 
You are casual, fun, and helpful. Keep responses concise unless asked for detail.
Your name is Dogesh Bot. 🦀"""


# Health check web server
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Dogesh Bot is running! \xf0\x9f\xa6\x80")
    
    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


def start_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"Health server on port {PORT}")
    server.serve_forever()


def ask_nvidia(prompt: str) -> str:
    """Call NVIDIA Nemotron API"""
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


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set!")
    if not NVIDIA_API_KEY:
        raise ValueError("NVIDIA_API_KEY not set!")
    
    # Start health check server in background
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    
    logger.info("Starting Dogesh Bot...")
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    logger.info("Bot is polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
