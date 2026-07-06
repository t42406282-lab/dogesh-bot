import os
import json
import logging
import requests
import subprocess
import re
import threading
from flask import Flask, request

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
WORKSPACE = "/tmp/workspace"

os.makedirs(WORKSPACE, exist_ok=True)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

SYSTEM_PROMPT = "You are Mimoclaw, a powerful AI agent. Tools: execute_python(code), run_command(cmd), web_search(query), read_file(path), write_file(path|content). Use <tool_call>TOOL|PARAMS</tool_call> format. Reply normally if no tool. Be helpful!"

def call_nvidia(prompt, history=[]):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.extend(history[-10:])
    msgs.append({"role": "user", "content": prompt})
    h = {"Authorization": "Bearer " + NVIDIA_API_KEY, "Content-Type": "application/json"}
    try:
        r = requests.post(NVIDIA_URL, headers=h, json={"model": NVIDIA_MODEL, "messages": msgs, "temperature": 0.7, "max_tokens": 2048}, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return "Error: " + str(e)

def run_tool(tool, params):
    try:
        if tool == "execute_python":
            r = subprocess.run(["python3", "-c", params], capture_output=True, text=True, timeout=30, cwd=WORKSPACE)
            return (r.stdout + r.stderr)[:2000] or "No output"
        elif tool == "run_command":
            r = subprocess.run(params, shell=True, capture_output=True, text=True, timeout=30, cwd=WORKSPACE)
            return (r.stdout + r.stderr)[:2000] or "No output"
        elif tool == "web_search":
            r = requests.get("https://api.duckduckgo.com/", params={"q": params, "format": "json"}, timeout=10)
            d = r.json()
            res = []
            if d.get("Abstract"): res.append(d["Abstract"])
            for x in d.get("RelatedTopics", [])[:5]:
                if x.get("Text"): res.append("* " + x["Text"])
            return chr(10).join(res[:10]) or "No results"
        elif tool == "read_file":
            with open(params) as f: return f.read()[:3000] or "Empty"
        elif tool == "write_file":
            p = params.split("|", 1)
            os.makedirs(os.path.dirname(p[0]), exist_ok=True)
            with open(p[0].strip(), "w") as f: f.write(p[1].strip())
            return "Written: " + p[0]
        else:
            return "Unknown: " + tool
    except Exception as e:
        return "Error: " + str(e)

def process_tools(resp):
    pat = r"<tool_call>(.*?)</tool_call>"
    matches = re.findall(pat, resp, re.DOTALL)
    if not matches: return resp
    results = []
    for m in matches:
        parts = m.split("|", 1)
        tool = parts[0].strip()
        p = parts[1].strip() if len(parts) > 1 else ""
        logger.info("Tool: " + tool)
        results.append("[" + tool + "]: " + run_tool(tool, p))
    clean = re.sub(pat, "", resp).strip()
    if results: clean += chr(10) + chr(10) + chr(10).join(results)
    return clean

user_history = {}

def send_msg(chat_id, text):
    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": text[:4000]}, timeout=15)
        result = r.json()
        logger.info("Send result: " + str(result))
        return result
    except Exception as e:
        logger.error("Send error: " + str(e))
        return {"error": str(e)}

def handle_update(update):
    try:
        msg = update.get("message", {})
        if not msg or not msg.get("text"): return
        chat_id = msg["chat"]["id"]
        text = msg["text"]
        uid = str(msg["from"]["id"])
        name = msg["from"].get("first_name", "?")
        logger.info("[" + name + "]: " + text)
        
        if text == "/start":
            send_msg(chat_id, "Mimoclaw Agent active!\nCode, search, files sab kar sakta hoon!\nBas bolo!")
            return
        
        history = user_history.get(uid, [])
        ai_resp = call_nvidia(text, history)
        logger.info("AI: " + ai_resp[:60])
        final = process_tools(ai_resp)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": final})
        user_history[uid] = history[-20:]
        send_msg(chat_id, final)
        logger.info("Reply sent!")
    except Exception as e:
        logger.error("Handler error: " + str(e))

TG_WEBHOOK = "/webhook/" + TELEGRAM_TOKEN

@app.route(TG_WEBHOOK, methods=["POST"])
def webhook():
    try:
        update = request.get_json(force=True)
        logger.info("Webhook: " + str(update.get("update_id")))
        threading.Thread(target=handle_update, args=(update,), daemon=True).start()
        return "OK", 200
    except Exception as e:
        logger.error("Webhook error: " + str(e))
        return "Error", 500

@app.route("/")
def health():
    return "Agent running!", 200

@app.route("/health")
def health2():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    logger.info("=== MIMOCLAW AGENT ===")
    logger.info("TOKEN: " + str(bool(TELEGRAM_TOKEN)) + " len=" + str(len(TELEGRAM_TOKEN)))
    logger.info("NVIDIA: " + str(bool(NVIDIA_API_KEY)))
    
    port = int(os.environ.get("PORT", "10000"))
    logger.info("Flask on port " + str(port))
    app.run(host="0.0.0.0", port=port)
