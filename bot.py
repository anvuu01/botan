import discord
from discord.ext import commands, tasks
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
import random
import os
from flask import Flask
from threading import Thread

# === KEEPALIVE CHO RENDER ===
app = Flask(__name__)
@app.route('/')
def home(): return "Bot đang chạy phiên bản gộp gốc!"
def run_server(): app.run(host="0.0.0.0", port=8080)

# === CẤU HÌNH TỪ FILE CŨ CỦA BẠN ===
# Lưu ý: Token dưới đây là token cũ bạn cung cấp, hãy thay bằng Token mới sau khi đổi mật khẩu
TOKEN = os.environ.get("TOKEN")

# --- Từ react.py ---
DELAY = 1.6
MAX_MESSAGES_PER_CHANNEL = None
SKIP_BOT_MESSAGES = True
FULL_SCAN = True
CONCURRENT_CHANNELS = 4
EMOJI_WHITELIST = []
EMOJI_BLACKLIST = []

CATEGORIES = [
    {
        "id": 1281146625435369472,
        "excluded_channels": [
            1229710841927045222, 1246901718143205437, 1516859270140792842,
            1516859246476787933, 1517099249257414777, 1196522451857842287,
            1232731962834161775, 1437860347032895518, 1390315019006251008,
            1281171567513960461, 1357284374684500159
        ]
    }
]

# --- Từ spam.py ---
SPAM_CHANNEL_ID = 1381302690335952988
SPAM_GUILD_ID = 1194106864582004849

BASE_DIR = Path(__file__).parent
PROGRESS_FILE = BASE_DIR / "progress.json"
LOG_FILE = BASE_DIR / "bot_log.txt"

log_fh = open(LOG_FILE, "a", encoding="utf-8")

def log(msg):
    print(msg)
    log_fh.write(f"[{datetime.now():%H:%M:%S}] {msg}\n")
    log_fh.flush()

bot = commands.Bot(command_prefix="!", self_bot=True)
progress = {}

def load_json(path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# === LOGIC REACT GỐC ===
async def add_reaction_with_retry(message, emoji):
    while True:
        try:
            await message.add_reaction(emoji)
            return True
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", None)
                if retry_after is None:
                    try:
                        retry_after = e.response.json().get("retry_after", 2.0) if hasattr(e, "response") else 2.0
                    except Exception:
                        retry_after = 2.0
                try:
                    retry_after = float(retry_after) + 0.5
                except Exception:
                    retry_after = 2.0
                log(f"  [429] Rate limited, dừng {retry_after:.2f}s...")
                await asyncio.sleep(retry_after)
                continue
            elif e.status == 403:
                return False
            else:
                err_txt = getattr(e, 'text', str(e))
                log(f"  [LOI {e.status}] {err_txt[:120]}")
                return False
        except Exception as e:
            log(f"  [LOI] {e}")
            return False

def is_emoji_allowed(emoji):
    emoji_str = str(emoji)
    if EMOJI_WHITELIST and emoji_str not in EMOJI_WHITELIST:
        return False
    if emoji_str in EMOJI_BLACKLIST:
        return False
    return True

async def process_channel(channel):
    key = str(channel.id)
    ch_progress = progress.get(key, {})
    last_id = ch_progress.get("last_reacted_id")
    reacted = ch_progress.get("total_reacted", 0)

    if FULL_SCAN:
        kwargs = {"limit": None}
    else:
        kwargs = {"limit": MAX_MESSAGES_PER_CHANNEL}
        if last_id:
            kwargs["after"] = discord.Object(id=int(last_id))

    new_reacted = 0
    last_reacted_id = None

    async for message in channel.history(**kwargs):
        if SKIP_BOT_MESSAGES and message.author.bot:
            continue
        if not message.reactions:
            continue

        for reaction in message.reactions:
            if reaction.me:
                continue
            if not is_emoji_allowed(reaction.emoji):
                continue

            ok = await add_reaction_with_retry(message, reaction.emoji)
            if ok:
                new_reacted += 1
                reacted += 1
                last_reacted_id = message.id
                log(f"  [{channel.id}] +{reaction.emoji} on {message.id} (total: {reacted})")

            await asyncio.sleep(DELAY)

    if last_reacted_id:
        progress[key] = {
            "name": channel.name,
            "last_reacted_id": str(last_reacted_id),
            "total_reacted": reacted,
        }
        save_json(PROGRESS_FILE, progress)

    return new_reacted

async def process_category(cat_cfg, sem):
    cat_id = cat_cfg["id"]
    category = bot.get_channel(cat_id)
    if not category:
        log(f"[!] Không tìm thấy category: {cat_id}")
        return 0

    excluded = set(cat_cfg.get("excluded_channels", []))
    channels = [
        ch for ch in category.channels
        if isinstance(ch, discord.TextChannel) and ch.id not in excluded
    ]

    if not channels:
        log(f"[{cat_id}] Không có channel nào cần xử lý")
        return 0

    log(f"[{cat_id}] Đang xử lý {len(channels)} channels (tối đa {CONCURRENT_CHANNELS} luồng)...")

    async def work(ch):
        async with sem:
            log(f"  >> {ch.name}")
            try:
                return await process_channel(ch)
            except discord.Forbidden:
                log(f"  [!] Không có quyền truy cập: {ch.name}")
                return 0
            except Exception as e:
                log(f"  [!] Lỗi {ch.name}: {e}")
                return 0

    results = await asyncio.gather(*[work(ch) for ch in channels], return_exceptions=True)
    return sum(r for r in results if isinstance(r, int))

async def do_react():
    global progress
    while True:
        progress = load_json(PROGRESS_FILE)

        if not CATEGORIES:
            log("Cấu hình thiếu 'CATEGORIES'")
            await asyncio.sleep(60)
            continue

        sem = asyncio.Semaphore(CONCURRENT_CHANNELS)
        total = 0
        for cat in CATEGORIES:
            total += await process_category(cat, sem)

        save_json(PROGRESS_FILE, progress)
        log(f"\nDone! Tổng reactions đã thêm trong lượt này: {total}. Nghỉ 10s...")
        await asyncio.sleep(10)


# === LOGIC SPAM EMOJI GỐC ===
@tasks.loop(seconds=60)
async def spam_task():
    try:
        guild = bot.get_guild(SPAM_GUILD_ID)
        channel = bot.get_channel(SPAM_CHANNEL_ID)
        if guild and channel and guild.emojis:
            emoji = random.choice(guild.emojis)
            await channel.send(str(emoji))
            print("Sent:", str(emoji))
    except Exception as e:
        log(f"Lỗi spam: {e}")


# === SỰ KIỆN BOT ===
@bot.event
async def on_ready():
    log(f"Đã log: {bot.user}")
    log(f"Categories: {len(CATEGORIES)}")
    log(f"Full scan: {FULL_SCAN}")
    
    if not spam_task.is_running():
        spam_task.start()
    asyncio.create_task(do_react())

@bot.event
async def on_message(message):
    # Logic Đánh Boss từ bot.py
    if message.author.bot:
        if message.components:
            for row in message.components:
                children = getattr(row, 'children', [])
                for component in children:
                    label = getattr(component, 'label', '') or ''
                    emoji = getattr(component, 'emoji', None)
                    emoji_name = emoji.name if emoji else ''

                    if "Đánh Boss" in label or "⚔️" in emoji_name:
                        try:
                            await component.click()
                            print(f"Đã đánh tại: {message.channel.name}")
                        except Exception as e:
                            print(f"Lỗi nhấn nút: {e}")
                            
    await bot.process_commands(message)

def main():
    Thread(target=run_server).start()
    if not TOKEN:
        log("TOKEN chưa được cấu hình!")
        sys.exit(1)
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
