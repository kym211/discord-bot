import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz
import asyncio

# ============================
# 설정 (여기만 수정하세요!)
# ============================

BOT_TOKEN = os.environ["MTQ4NjY0NDY2MDY4MzQwNzQ4MQ.GVe09y.jfrCwfHVmxDofT0zP7FRaA_2TBeXKGZEe-zWtM"]
CHANNEL_ID = int(os.environ["1088330134987210783"])  # 알림 보낼 채널 ID (정수)

# 각 알림 메시지 내용
MSG_1 = "🔔 **알림 1** - 토/일 오후 10시 알림입니다!"
MSG_2 = "🔔 **알림 2** - 화/목/토 오후 9시 알림입니다!"
MSG_3 = "🔔 **알림 3** - 12시간 간격 알림입니다!"
MSG_4 = "🔔 **알림 4** - 정기 알림입니다! (오후 8시 / 오후 11시 / 오전 2시)"

# ============================

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
    weekday = now.weekday()  # 0=월 1=화 2=수 3=목 4=금 5=토 6=일
    hour = now.hour
    minute = now.minute

    if minute != 0:
        return  # 매 정각에만 실행

    # 알림 1: 토(5), 일(6) 오후 10시
    if weekday in [5, 6] and hour == 22:
        await send_notification(MSG_1)

    # 알림 2: 화(1), 목(3), 토(5) 오후 9시
    if weekday in [1, 3, 5] and hour == 21:
        await send_notification(MSG_2)

    # 알림 3: 매일 12시간 간격 (정오 12시, 자정 0시)
    if hour in [0, 12]:
        await send_notification(MSG_3)

    # 알림 4: 오후 8시(20), 오후 11시(23), 오전 2시(2)
    if hour in [20, 23, 2]:
        await send_notification(MSG_4)


@scheduler.before_loop
async def before_scheduler():
    await bot.wait_until_ready()

    # 다음 정각까지 대기 (정각에 맞춰 시작)
    now = datetime.now(KST)
    seconds_until_next_minute = 60 - now.second
    print(f"[봇] {seconds_until_next_minute}초 후 스케줄러 시작...")
    await asyncio.sleep(seconds_until_next_minute)


@bot.event
async def on_ready():
    print(f"[봇] {bot.user} 로그인 완료!")
    print(f"[봇] 알림 채널 ID: {CHANNEL_ID}")
    scheduler.start()


bot.run(BOT_TOKEN)
