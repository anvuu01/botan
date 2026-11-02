import discord
from discord.ext import commands, tasks
import os
import asyncio
import random
import json
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask
from threading import Thread

# === 1. WEB SERVER KEEPALIVE ===
app = Flask(__name__)
@app.route('/')
def home(): return "Bot đang cày React full tính năng!"
def run_server(): app.run(host="0.0.0.0", port=8080)

bot = commands.Bot(command_prefix="!", self_bot=True)

# === 2. CẤU HÌNH TÀI KHOẢN ===
CHANNEL_ID = 1381302690335952988
GUILD_ID = 1194106864582004849
FARM_EMOJI = "🔥"

CONCURRENT_CHANNELS = 2  
CHUNK_SIZE = 100         

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

BASE_DIR = Path(__file__).parent
PROGRESS_FILE = BASE_DIR / "progress.json"

def load_json():
    if not PROGRESS_FILE.exists(): return {}
    with open(PROGRESS_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_json(data):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)

# === 3. XỬ LÝ QUÉT BÀI CŨ AN TOÀN ===
async def process_channel(channel, progress_data):
    key = str(channel.id)
    ch_progress = progress_data.get(key, {})
    last_id = ch_progress.get("last_reacted_id")
    reacted = ch_progress.get("total_reacted", 0)

    kwargs = {"limit": CHUNK_SIZE} 
    if last_id: kwargs["after"] = discord.Object(id=int(last_id))

    last_reacted_id = None
    
    async for message in channel.history(oldest_first=True, **kwargs):
        if message.author.bot: continue
        
        last_reacted_id = message.id
        
        # Nhái lại toàn bộ icon đang có trên bài viết
        if message.reactions:
            for reaction in message.reactions:
                try:
                    await asyncio.sleep(random.uniform(1.2, 2.5))
                    await message.add_reaction(reaction.emoji)
                    reacted += 1
                except discord.HTTPException as e:
                    if e.status == 429:
                        penalty = float(getattr(e, "retry_after", 5.0))
                        await asyncio.sleep(penalty + 1.0)
                except: pass
        # Nếu bài chưa có icon nào, thả icon mặc định
        else:
            try:
                await asyncio.sleep(random.uniform(1.2, 2.5))
                await message.add_reaction(FARM_EMOJI)
                reacted += 1
            except discord.HTTPException as e:
                if e.status == 429:
                    penalty = float(getattr(e, "retry_after", 5.0))
                    await asyncio.sleep(penalty + 1.0)
            except: pass

    if last_reacted_id:
        progress_data[key] = {"last_reacted_id": str(last_reacted_id), "total_reacted": reacted}
        save_json(progress_data)

async def do_react_task():
    await bot.wait_until_ready()
    while True:
        progress_data = load_json()
        sem = asyncio.Semaphore(CONCURRENT_CHANNELS)
        
        for cat_cfg in CATEGORIES:
            cat = bot.get_channel(cat_cfg["id"])
            if not cat: continue
            excluded = set(cat_cfg.get("excluded_channels", []))
            
            async def work(ch):
                async with sem: await process_channel(ch, progress_data)
                
            tasks_list = [work(ch) for ch in cat.channels if isinstance(ch, discord.TextChannel) and ch.id not in excluded]
            await asyncio.gather(*tasks_list, return_exceptions=True)
            
        await asyncio.sleep(15) 

# === 4. AUTO SPAM EMOJI THEO PHÚT ===
@tasks.loop(minutes=1)
async def spam_emoji_task():
    try:
        await asyncio.sleep(random.uniform(1.0, 5.0)) 
        guild = bot.get_guild(GUILD_ID)
        channel = bot.get_channel(CHANNEL_ID)
        if guild and channel and guild.emojis:
            await channel.send(str(random.choice(guild.emojis)))
    except: pass

# === 5. SỰ KIỆN ĐÁNH BOSS ===
def is_boss_time():
    now = datetime.utcnow() + timedelta(hours=7)
    if (now.hour == 11 and now.minute >= 55) or (now.hour == 12 and now.minute <= 20): return True
    if (now.hour == 19 and now.minute >= 10) or (now.hour == 19 and now.minute <= 35): return True
    return False

@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.invisible)
    if not spam_emoji_task.is_running(): spam_emoji_task.start()
    asyncio.create_task(do_react_task())

@bot.event
async def on_message(message):
    if is_boss_time() and message.author.bot and message.components:
        for row in message.components:
            for component in getattr(row, 'children', []):
                label = getattr(component, 'label', '') or ''
                emoji_name = component.emoji.name if getattr(component, 'emoji', None) else ''
                if "Đánh Boss" in label or "⚔️" in emoji_name:
                    try:
                        await asyncio.sleep(random.uniform(2.5, 6.0))
                        await component.click()
                    except: pass
    await bot.process_commands(message)

Thread(target=run_server).start()
bot.run(os.environ.get("DISCORD_TOKEN"))
