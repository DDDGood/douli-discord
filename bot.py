import discord
from discord.ext import commands, tasks
from datetime import time, datetime, timedelta
import pytz
import csv
from dotenv import load_dotenv
import os
import asyncio
import logging
import random
import atexit
from dataclasses import dataclass, field
from typing import List, Tuple

# 在文件頂部設置日誌，允許從環境變數設置日誌級別
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=getattr(logging, log_level))

local_tz = datetime.now().astimezone().tzinfo

# 設定每日早晚執行一次函式
morning_time = time(hour=9, minute=0, tzinfo=local_tz)
evening_time = time(hour=18, minute=0, tzinfo=local_tz)

# 早晚訊息
morning_messages = [
    "早安～新的一天開始了，祝你有個美好的一天 :smiley:",
    "大家早安 :sunny: 希望你今天充滿活力和笑容！",
    "早安～願你今天順利又愉快 :smiling_face_with_3_hearts: "
]

evening_messages = [
    "晚安～今天辛苦了，記得放鬆一下 :beers: ",
    "結束了一天的忙碌，請好好休息 :sleeping: ",
    "晚安～享受一下輕鬆的時光吧 :partying_face: "
]

# 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

# 設定 bot 的 intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

# 創建 bot 實例
bot = commands.Bot(command_prefix='!', intents=intents)

@dataclass
class CheckinRecord:
    username: str
    checkin_time: str
    period: str

# 全局變量
checkin_message = None
checkin_message_ids: List[int] = []
user_checkins: List[CheckinRecord] = []

# 創建存放簽到記錄的資料夾
RECORDS_FOLDER = 'checkin_records'
if not os.path.exists(RECORDS_FOLDER):
    os.makedirs(RECORDS_FOLDER)

# 寫入簽到紀錄到文件的函數
def write_checkin_record(record: CheckinRecord):
    filename = os.path.join(RECORDS_FOLDER, f"checkin_records_{datetime.now().strftime('%Y-%m-%d')}.csv")
    is_new_file = not os.path.exists(filename)
    with open(filename, 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if is_new_file:
            writer.writerow(["使用者", "簽到時間", "時段"])
        writer.writerow([record.username, record.checkin_time, record.period])

# 修改 on_ready 事件
@bot.event
async def on_ready():
    print(f'{bot.user} 已連接到 Discord!')
    scheduled_morning_checkin_message.start()
    scheduled_evening_checkin_message.start()
    print("簽到任務已啟動")

# 修改自動簽到函數
@tasks.loop(time=morning_time)
async def scheduled_morning_checkin_message():
    message = random.choice(morning_messages)
    await send_checkin_message(message, "早上", "早安！")

@tasks.loop(time=evening_time)
async def scheduled_evening_checkin_message():
    message = random.choice(evening_messages)
    await send_checkin_message(message, "晚上", "休息囉！")

async def send_checkin_message(message, period, button_label):
    try:
        global checkin_message, checkin_message_ids
        channel = bot.get_channel(CHANNEL_ID)
        if channel is None:
            logging.error(f"無法找到頻道 ID: {CHANNEL_ID}")
            return
        
        # 刪除舊消息
        # for message_id in checkin_message_ids:
        #     try:
        #         old_message = await channel.fetch_message(message_id)
        #         await old_message.delete()
        #     except Exception as e:
        #         logging.error(f"刪除舊消息時發生錯誤: {e}")
        # checkin_message_ids.clear()
        
        try:
            deleted = await channel.purge(limit=100)
            logging.info(f"已刪除 {len(deleted)} 則訊息")
        except Exception as e:
            logging.error(f"清空頻道訊息時發生錯誤: {e}")
        
        view = discord.ui.View(timeout=None)
        button = discord.ui.Button(label=button_label, style=discord.ButtonStyle.primary)
        
        async def button_callback(interaction):
            checkin_time = datetime.now(pytz.timezone('Asia/Taipei')).strftime("%Y-%m-%d %H:%M:%S")
            record = CheckinRecord(interaction.user.name, checkin_time, period)
            user_checkins.append(record)
            write_checkin_record(record)
            await interaction.response.send_message(f"{period}簽到成功！", ephemeral=True)
        
        button.callback = button_callback
        view.add_item(button)
        
        checkin_message = await channel.send(f"{message}\n請點擊按鈕簽到！", view=view)
        # checkin_message_ids.append(checkin_message.id)
        logging.info(f"{period}消息已發送")
    except Exception as e:
        logging.error(f"發送消息時發生錯誤: {e}")

@scheduled_morning_checkin_message.before_loop
@scheduled_evening_checkin_message.before_loop
async def before_scheduled_checkin_message():
    await bot.wait_until_ready()
    logging.info("Bot 已準備就緒，自動消息任務即將開始")

# 手動觸發消息的命令
@bot.command(name='手動')
@commands.has_permissions(administrator=True)
async def manual_checkin_message(ctx):
    message = "這是一條手動觸發的消息。"
    await send_checkin_message(message, "手動", "回覆")
    await ctx.send("手動消息已發送")

@bot.command(name='查看簽到')
@commands.has_permissions(administrator=True)
async def view_checkins(ctx):
    if ctx.author.guild_permissions.administrator:
        response = "今日簽到紀錄:\n"
        for record in user_checkins:
            response += f"{record.username} ({record.period}): {record.checkin_time}\n"
        await ctx.send(response)

@bot.command(name='導出簽到')
@commands.has_permissions(administrator=True)
async def export_checkins(ctx):
    if ctx.author.guild_permissions.administrator:
        export_path = os.path.join(RECORDS_FOLDER, 'checkins.csv')
        with open(export_path, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["使用者", "簽到時間", "時段"])
            for record in user_checkins:
                writer.writerow([record.username, record.checkin_time, record.period])
        await ctx.send("簽到紀錄已導出為 CSV 文件。", file=discord.File(export_path))

# 新增刪除舊消息的函數
async def delete_old_messages():
    # global checkin_message_ids
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        logging.error(f"無法找到頻道 ID: {CHANNEL_ID}")
        return
    # for message_id in checkin_message_ids:
    #     try:
    #         old_message = await channel.fetch_message(message_id)
    #         await old_message.delete()
    #     except Exception as e:
    #         logging.error(f"刪除舊消息時發生錯誤: {e}")
    # checkin_message_ids.clear()
    # 刪除頻道內所有訊息（限最近的100條，可多次呼叫獲取更多）
    try:
        deleted = await channel.purge(limit=100)
        logging.info(f"已刪除 {len(deleted)} 則訊息")
    except Exception as e:
        logging.error(f"清空頻道訊息時發生錯誤: {e}")

# 使用 atexit 註冊退出時運行的函數
def on_exit():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(delete_old_messages())

atexit.register(on_exit)

# 運行 bot
bot.run(TOKEN)
