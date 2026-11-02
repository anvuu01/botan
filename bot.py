import discord
from discord.ext import commands
import os
import asyncio
import random
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

# Web server ảo cho UptimeRobot
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot đang chạy!"

def run_server():
    app.run(host="0.0.0.0", port=8080)

bot = commands.Bot(command_prefix="!", self_bot=True)

def is_boss_time():
    # Đồng bộ giờ chuẩn Việt Nam (UTC+7)
    now = datetime.utcnow() + timedelta(hours=7)
    
    # Khung giờ 1: 11:55 đến 12:20
    if now.hour == 11 and now.minute >= 55:
        return True
    if now.hour == 12 and now.minute <= 20:
        return True
        
    # Khung giờ 2: 19:10 đến 19:35
    if now.hour == 19 and 10 <= now.minute <= 35:
        return True
        
    return False

@bot.event
async def on_ready():
    print(f"Đã log: {bot.user}")

@bot.event
async def on_message(message):
    # Nếu không nằm trong giờ đánh boss, lập tức bỏ qua tin nhắn
    if not is_boss_time():
        return

    if message.author.bot and message.components:
        for row in message.components:
            for component in getattr(row, 'children', []):
                label = getattr(component, 'label', '') or ''
                emoji_name = component.emoji.name if getattr(component, 'emoji', None) else ''
                
                if "Đánh Boss" in label or "⚔️" in emoji_name:
                    try:
                        # Delay ngẫu nhiên để giả lập thao tác người thật
                        await asyncio.sleep(random.uniform(2.5, 6.0))
                        await component.click()
                        print(f"Đã đánh boss lúc {datetime.utcnow() + timedelta(hours=7)}")
                    except Exception as e:
                        print(f"Lỗi: {e}")
                        
    await bot.process_commands(message)

Thread(target=run_server).start()
bot.run(os.environ.get("DISCORD_TOKEN"))