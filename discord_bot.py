import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import pytz
import asyncio

# ============================
# 기본 설정
# ============================

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================
# 역할 설정
# ============================

ROLE_NAMES = {
    "나흐마": "📢 나흐마",
    "아티쟁": "📢 아티쟁",
    "아그로": "📢 아그로",
    "시공8": "📢 시공 (오후 8시)",
    "시공23": "📢 시공 (오후 11시)",
    "시공2": "📢 시공 (오전 2시)",
}

# ============================
# 유저별 사전알림 데이터
# ============================

user_prealarms = {}

# ============================
# 아그로 시간 설정
# ============================

agro_start = 0
agro_minute = 0

def get_agro_times():
    base = datetime.now(KST).replace(hour=agro_start, minute=agro_minute, second=0, microsecond=0)
    times = []

    for i in range(2):  # 12시간 간격
        t = base + timedelta(hours=12 * i)
        times.append((t.hour, t.minute))

    return times

# ============================
# 역할 생성
# ============================

async def get_or_create_role(guild, role_name):
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        role = await guild.create_role(name=role_name, mentionable=True)
    return role

# ============================
# 알림 구독 버튼
# ============================

class AlarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def toggle_role(self, interaction, key):
        role = await get_or_create_role(interaction.guild, ROLE_NAMES[key])
        member = interaction.user

        if role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message(f"🔕 {ROLE_NAMES[key]} 해제", ephemeral=True)
        else:
            await member.add_roles(role)
            await interaction.response.send_message(f"🔔 {ROLE_NAMES[key]} 구독", ephemeral=True)

    @discord.ui.button(label="나흐마")
    async def b1(self, i, b): await self.toggle_role(i, "나흐마")

    @discord.ui.button(label="아티쟁")
    async def b2(self, i, b): await self.toggle_role(i, "아티쟁")

    @discord.ui.button(label="아그로")
    async def b3(self, i, b): await self.toggle_role(i, "아그로")

    @discord.ui.button(label="시공8")
    async def b4(self, i, b): await self.toggle_role(i, "시공8")

    @discord.ui.button(label="시공23")
    async def b5(self, i, b): await self.toggle_role(i, "시공23")

    @discord.ui.button(label="시공2")
    async def b6(self, i, b): await self.toggle_role(i, "시공2")

# ============================
# 사전알림 설정 (슬래시)
# ============================

@bot.tree.command(name="사전알림", description="알림별 사전시간 설정")
async def prealarm(interaction: discord.Interaction, 알림: str, 분: int):

    user_id = interaction.user.id

    if 알림 not in ROLE_NAMES:
        await interaction.response.send_message("❌ 알림 이름 오류")
        return

    if user_id not in user_prealarms:
        user_prealarms[user_id] = {}

    if 알림 not in user_prealarms[user_id]:
        user_prealarms[user_id][알림] = []

    if 분 in user_prealarms[user_id][알림]:
        user_prealarms[user_id][알림].remove(분)
        msg = "삭제"
    else:
        user_prealarms[user_id][알림].append(분)
        msg = "추가"

    await interaction.response.send_message(f"✅ {알림} {분}분 전 알림 {msg}")

# ============================
# 내 설정 조회
# ============================

@bot.tree.command(name="내알림", description="내 알림 설정 확인")
async def my_alarm(interaction: discord.Interaction):

    data = user_prealarms.get(interaction.user.id, {})

    if not data:
        await interaction.response.send_message("❌ 없음")
        return

    msg = "📌 설정\n\n"

    for k, v in data.items():
        times = ", ".join([f"{m}분 전" for m in v])
        msg += f"{k} → {times}\n"

    await interaction.response.send_message(msg)

# ============================
# 아그로 시간 설정 (핵심)
# ============================

@bot.tree.command(name="아그로", description="아그로 시간 설정 (예: 600 / 0930)")
async def set_agro(interaction: discord.Interaction, 시간: str):

    global agro_start, agro_minute

    try:
        시간 = 시간.zfill(4)
        h = int(시간[:2])
        m = int(시간[2:])

        agro_start = h
        agro_minute = m

        await interaction.response.send_message(
            f"✅ 설정 완료\n{h:02d}:{m:02d} / {(h+12)%24:02d}:{m:02d}"
        )

    except:
        await interaction.response.send_message("❌ 형식 오류")

# ============================
# 알림 전송
# ============================

async def send_notification(guild, key, msg):
    role = discord.utils.get(guild.roles, name=ROLE_NAMES[key])
    if role:
        await bot.get_channel(CHANNEL_ID).send(f"{role.mention} {msg}")

async def send_prealarm(guild, label, h, m, before):

    channel = bot.get_channel(CHANNEL_ID)
    mentions = []

    for member in guild.members:
        data = user_prealarms.get(member.id, {})
        if label in data and before in data[label]:
            mentions.append(member.mention)

    if mentions:
        await channel.send(
            f"⏱ {' '.join(mentions)}\n{label} {before}분 전"
        )

# ============================
# 스케줄
# ============================

def get_schedules():

    s = []

    # 나흐마
    s.append({"h":22,"m":0,"wd":[5,6],"k":"나흐마"})

    # 아티쟁
    s.append({"h":21,"m":0,"wd":[1,3,5],"k":"아티쟁"})

    # 아그로
    for h,m in get_agro_times():
        s.append({"h":h,"m":m,"wd":None,"k":"아그로"})

    # 시공
    s += [
        {"h":20,"m":0,"wd":None,"k":"시공8"},
        {"h":23,"m":0,"wd":None,"k":"시공23"},
        {"h":2,"m":0,"wd":None,"k":"시공2"},
    ]

    return s

@tasks.loop(minutes=1)
async def scheduler():

    now = datetime.now(KST)
    g = bot.guilds[0]

    for s in get_schedules():

        if s["wd"] and now.weekday() not in s["wd"]:
            continue

        if now.hour == s["h"] and now.minute == s["m"]:
            await send_notification(g, s["k"], f"{s['k']} 알림")

        for mins in [5,10,20,30,60]:
            t = now.replace(hour=s["h"], minute=s["m"]) - timedelta(minutes=mins)

            if now.hour == t.hour and now.minute == t.minute:
                await send_prealarm(g, s["k"], s["h"], s["m"], mins)

@scheduler.before_loop
async def before():
    await bot.wait_until_ready()
    await asyncio.sleep(60 - datetime.now().second)

# ============================
# 시작
# ============================

@bot.event
async def on_ready():
    print("봇 시작")
    bot.add_view(AlarmView())
    await bot.tree.sync()
    scheduler.start()

bot.run(BOT_TOKEN)
