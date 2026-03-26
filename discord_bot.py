import os
import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz
import asyncio

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

MSG_1 = "🔔 **알림 1** - 토/일 오후 10시 알림입니다!"
MSG_2 = "🔔 **알림 2** - 화/목/토 오후 9시 알림입니다!"
MSG_3 = "🔔 **알림 3** - 12시간 간격 알림입니다!"
MSG_4 = "🔔 **알림 4** - 정기 알림입니다! (오후 8시 / 오후 11시 / 오전 2시)"

KST = pytz.timezone("Asia/Seoul")
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

async def send_notification(message: str):
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(message)
    else:
        print(f"[오류] 채널을 찾을 수 없습니다: {CHANNEL_ID}")

@tasks.loop(minutes=1)
async def scheduler():
    now = datetime.now(KST)
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute

    if minute != 0:
        return

    if weekday in [5, 6] and hour == 22:
        await send_notification(MSG_1)
    if weekday in [1, 3, 5] and hour == 21:
        await send_notification(MSG_2)
    if hour in [0, 12]:
        await send_notification(MSG_3)
    if hour in [20, 23, 2]:
        await send_notification(MSG_4)

@scheduler.before_loop
async def before_scheduler():
    await bot.wait_until_ready()
    now = datetime.now(KST)
    seconds_until_next_minute = 60 - now.second
    await asyncio.sleep(seconds_until_next_minute)

@bot.event
async def on_ready():
    print(f"[봇] {bot.user} 로그인 완료!")
    scheduler.start()

bot.run(BOT_TOKEN)
