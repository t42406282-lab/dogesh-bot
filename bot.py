import os
import logging
import asyncio
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "You are Mimoclaw, a powerful AI agent. You speak Hinglish. Tools: execute_python(code), run_command(cmd), web_search(query), read_file(path), write_file(path|content). Use <tool_call>TOOL|PARAMS</tool_call> format. Reply normally if no tool needed. Be helpful and fun!"

flask_app = Flask(__name__)

@flask_app.route("/")
def health():
    return "Mimoclaw Agent running!", 200

@flask_app.route("/health")
def health_check():
    return {"status": "ok"}, 200

def ask_nvidia(prompt):
    headers = {"Authorization": "Bearer " + NVIDIA_API_KEY, "Content-Type": "application/json"}
    payload = {"model": NVIDIA_MODEL, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 2048}
    try:
        resp = requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("NVIDIA error: " + str(e))
        return "API Error: " + str(e)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Mimoclaw Agent active hai! Kuch bhi pucho!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    user_name = update.message.from_user.first_name
    logger.info("[" + user_name + "]: " + user_msg)
    try:
        await update.message.chat.send_action("typing")
        reply = ask_nvidia(user_msg)
        logger.info("[Bot]: " + reply[:80])
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error("Error: " + str(e))
        await update.message.reply_text("Error aaya hai!")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Bot error: " + str(context.error))

async def run_bot_async():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot polling started!")
    await asyncio.Event().wait()

def run_telegram_bot():
    logger.info("Starting bot thread...")
    asyncio.run(run_bot_async())

logger.info("TOKEN: " + str(bool(TELEGRAM_TOKEN)) + " NVIDIA: " + str(bool(NVIDIA_API_KEY)))
if TELEGRAM_TOKEN and NVIDIA_API_KEY:
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True, name="tg-bot")
    bot_thread.start()
    logger.info("Bot thread started!")
