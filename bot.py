import os
import json
import logging
import requests
import subprocess
import re
import time
import threading
import uuid
from datetime import datetime
from flask import Flask, request, send_file

# Config
_environ = os.environ
TELEGRAM_TOKEN = _environ.get("TELEGRAM_TOKEN", "")
NVIDIA_API_KEY = _environ.get("NVIDIA_API_KEY", "")
HF_TOKEN = _environ.get("HF_TOKEN", "")
NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
WORKSPACE = "/tmp/workspace"
MEMORY_DIR = "/tmp/memory"
IMAGE_DIR = "/tmp/images"

for d in [WORKSPACE, MEMORY_DIR, IMAGE_DIR]:
    os.makedirs(d, exist_ok=True)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

SYSTEM_PROMPT = """You are Mimoclaw, a powerful AI agent.

AVAILABLE TOOLS (use format: <tool_call>TOOL_NAME|PARAMS</tool_call>):

1. execute_python(code) - Run Python code
2. run_command(cmd) - Run shell commands
3. web_search(query) - Search the web
4. read_file(path) - Read file contents
5. write_file(path|content) - Write to file
6. generate_image(prompt) - Generate image from text
7. save_memory(key|value) - Save info to persistent memory
8. get_memory(key) - Retrieve saved memory

RULES:
- Use tools when needed, reply normally otherwise
- Speak in Hinglish (Hindi/Urdu + English mix)
- Be helpful, smart, witty
- Remember conversations using memory tools
- For images use generate_image tool"""

# === MEMORY SYSTEM ===
def get_memory_file(user_id):
    return os.path.join(MEMORY_DIR, user_id + ".json")

def load_memory(user_id):
    path = get_memory_file(user_id)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except:
            pass
    return {"history": [], "data": {}}

def save_memory_data(user_id, memory):
    with open(get_memory_file(user_id), "w") as f:
        json.dump(memory, f, indent=2)

def add_to_history(user_id, role, content):
    memory = load_memory(user_id)
    memory["history"].append({"role": role, "content": content, "time": datetime.now().isoformat()})
    memory["history"] = memory["history"][-50:]
    save_memory_data(user_id, memory)

def get_history(user_id):
    return load_memory(user_id)["history"]

# === NVIDIA LLM ===
def call_nvidia(prompt, user_id):
    history = get_history(user_id)
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history[-20:]:
        msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": prompt})
    headers = {"Authorization": "Bearer " + NVIDIA_API_KEY, "Content-Type": "application/json"}
    payload = {"model": NVIDIA_MODEL, "messages": msgs, "temperature": 0.7, "max_tokens": 2048}
    try:
        r = requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("NVIDIA error: " + str(e))
        return "API Error: " + str(e)

# === IMAGE GENERATION ===
def generate_image(prompt):
    if not HF_TOKEN:
        return None, "HF_TOKEN not set"
    try:
        logger.info("Generating image: " + prompt[:50])
        headers = {"Authorization": "Bearer " + HF_TOKEN}
        payload = {"inputs": prompt}
        r = requests.post(
            "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0",
            headers=headers, json=payload, timeout=120
        )
        if r.status_code == 200:
            img_name = "img_" + str(uuid.uuid4())[:8] + ".png"
            img_path = os.path.join(IMAGE_DIR, img_name)
            with open(img_path, "wb") as f:
                f.write(r.content)
            logger.info("Image saved: " + img_path)
            return img_path, None
        else:
            return None, "Image gen failed: " + str(r.status_code)
    except Exception as e:
        return None, "Image error: " + str(e)

# === TOOLS ===
def execute_python(code):
    try:
        r = subprocess.run(["python3", "-c", code], capture_output=True, text=True, timeout=30, cwd=WORKSPACE)
        return (r.stdout + r.stderr)[:2000] or "No output"
    except Exception as e:
        return "Error: " + str(e)

def run_command(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=WORKSPACE)
        return (r.stdout + r.stderr)[:2000] or "No output"
    except Exception as e:
        return "Error: " + str(e)

def web_search(query):
    try:
        r = requests.get("https://api.duckduckgo.com/", params={"q": query, "format": "json"}, timeout=10)
        d = r.json()
        results = []
        if d.get("Abstract"):
            results.append(d["Abstract"])
        for x in d.get("RelatedTopics", [])[:5]:
            if x.get("Text"):
                results.append("* " + x["Text"])
        return chr(10).join(results[:10]) or "No results"
    except Exception as e:
        return "Search error: " + str(e)

def read_file(path):
    try:
        with open(path) as f:
            return f.read()[:3000] or "Empty"
    except Exception as e:
        return "Error: " + str(e)

def write_file(path, content):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return "Written: " + path
    except Exception as e:
        return "Error: " + str(e)

# === TOOL PROCESSING ===
def process_tools(response, user_id):
    pat = r"<tool_call>(.*?)</tool_call>"
    matches = re.findall(pat, response, re.DOTALL)
    if not matches:
        return response, None
    
    results = []
    img_path = None
    
    for m in matches:
        parts = m.split("|", 1)
        tool = parts[0].strip()
        params = parts[1].strip() if len(parts) > 1 else ""
        logger.info("Tool: " + tool)
        
        if tool == "execute_python":
            results.append("[execute_python]: " + execute_python(params))
        elif tool == "run_command":
            results.append("[run_command]: " + run_command(params))
        elif tool == "web_search":
            results.append("[web_search]: " + web_search(params))
        elif tool == "read_file":
            results.append("[read_file]: " + read_file(params))
        elif tool == "write_file":
            p = params.split("|", 1)
            results.append("[write_file]: " + (write_file(p[0].strip(), p[1].strip()) if len(p) == 2 else "Need path|content"))
        elif tool == "generate_image":
            path, err = generate_image(params)
            if path:
                img_path = path
                results.append("[generate_image]: Image generated!")
            else:
                results.append("[generate_image]: " + (err or "Failed"))
        elif tool == "save_memory":
            p = params.split("|", 1)
            if len(p) == 2:
                memory = load_memory(user_id)
                memory["data"][p[0].strip()] = p[1].strip()
                save_memory_data(user_id, memory)
                results.append("[save_memory]: Saved " + p[0].strip())
        elif tool == "get_memory":
            val = load_memory(user_id)["data"].get(params.strip(), "Not found")
            results.append("[get_memory] " + params + ": " + val)
        else:
            results.append("[unknown]: " + tool)
    
    clean = re.sub(pat, "", response).strip()
    if results:
        clean += chr(10) + chr(10) + chr(10).join(results)
    return clean, img_path

# === TELEGRAM ===
BOT_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

def send_message(chat_id, text, img_path=None):
    try:
        if img_path:
            with open(img_path, "rb") as img:
                r = requests.post(BOT_API + "/sendPhoto", data={"chat_id": chat_id, "caption": text[:1024]}, files={"photo": img}, timeout=30)
        else:
            r = requests.post(BOT_API + "/sendMessage", json={"chat_id": chat_id, "text": text[:4000]}, timeout=15)
        return r.json()
    except Exception as e:
        logger.error("Send error: " + str(e))
        return {"error": str(e)}

def handle_update(update):
    try:
        msg = update.get("message", {})
        if not msg or not msg.get("text"):
            return
        chat_id = msg["chat"]["id"]
        text = msg["text"]
        user_id = str(msg["from"]["id"])
        name = msg["from"].get("first_name", "?")
        logger.info("[" + name + "]: " + text)
        
        add_to_history(user_id, "user", text)
        
        if text == "/start":
            send_message(chat_id, "Mimoclaw Agent active!\\n\\nMain sab kar sakta hoon:\\n- Baat karna (AI chat)\\n- Code likhna/execute karna\\n- Web search karna\\n- Files bana/padhna\\n- Images generate karna\\n- Memory save karna\\n\\nBas bolo kya karna hai!")
            return
        if text == "/clear":
            save_memory_data(user_id, {"history": [], "data": {}})
            send_message(chat_id, "Memory clear ho gayi!")
            return
        
        try:
            requests.post(BOT_API + "/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=5)
        except:
            pass
        
        ai_resp = call_nvidia(text, user_id)
        logger.info("AI: " + ai_resp[:80])
        final, img_path = process_tools(ai_resp, user_id)
        add_to_history(user_id, "assistant", final)
        send_message(chat_id, final, img_path)
        logger.info("Reply sent!")
    except Exception as e:
        logger.error("Handler error: " + str(e))

@app.route("/")
def health():
    return "Mimoclaw Agent running!", 200

@app.route("/health")
def health2():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    logger.info("=== MIMOCLAW AGENT v2 ===")
    logger.info("TOKEN: " + str(bool(TELEGRAM_TOKEN)) + " NVIDIA: " + str(bool(NVIDIA_API_KEY)) + " HF: " + str(bool(HF_TOKEN)))
    port = int(_environ.get("PORT", "10000"))
    logger.info("Port " + str(port))
    app.run(host="0.0.0.0", port=port)
