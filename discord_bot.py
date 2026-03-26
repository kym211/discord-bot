import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import pytz
import asyncio
import json

# ============================
# 기본 설정
# ============================

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# ============================
# 데이터 로드/저장
# ============================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"prealarms": {}, "agro": {"hour": 0, "minute": 0}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

data = load_data()

# ============================
# 역할
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
# 아그로 시간
# ============================

def get_agro_times():
    h = data["agro"]["hour"]
    m = data["agro"]["minute"]

    base = datetime.now(KST).replace(hour=h, minute=m, second=0, microsecond=0)

    return [
        (base.hour, base.minute),
        ((base + timedelta(hours=12)).hour, (base + timedelta(hours=12)).minute)
    ]

# ============================
# 역할 생성
# ============================

async def get_or_create_role(guild, name):
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = await guild.create_role(name=name, mentionable=True)
    return role

# ============================
# 버튼 (영구)
# ============================

class AlarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def toggle(self, interaction, key):
        role = await get_or_create_role(interaction.guild, ROLE_NAMES[key])
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"🔕 {key} 해제", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"🔔 {key} 구독", ephemeral=True)

    @discord.ui.button(label="나흐마", custom_id="nahma")
    async def b1(self, i, b): await self.toggle(i, "나흐마")

    @discord.ui.button(label="아티쟁", custom_id="arti")
    async def b2(self, i, b): await self.toggle(i, "아티쟁")

    @discord.ui.button(label="아그로", custom_id="agro")
    async def b3(self, i, b): await self.toggle(i, "아그로")

    @discord.ui.button(label="시공8", custom_id="s8")
    async def b4(self, i, b): await self.toggle(i, "시공8")

    @discord.ui.button(label="시공23", custom_id="s23")
    async def b5(self, i, b): await self.toggle(i, "시공23")

    @discord.ui.button(label="시공2", custom_id="s2")
    async def b6(self, i, b): await self.toggle(i, "시공2")

# ============================
# 사전알림
# ============================

@bot.tree.command(name="사전알림")
async def prealarm(interaction: discord.Interaction, 알림: str, 분: int):

    uid = str(interaction.user.id)

    if uid not in data["prealarms"]:
        data["prealarms"][uid] = {}

    if 알림 not in data["prealarms"][uid]:
        data["prealarms"][uid][알림] = []

    if 분 in data["prealarms"][uid][알림]:
        data["prealarms"][uid][알림].remove(분)
        msg = "삭제"
    else:
        data["prealarms"][uid][알림].append(분)
        msg = "추가"

    save_data()

    await interaction.response.send_message(f"{알림} {분}분 전 {msg}")

# ============================
# 내 설정 확인
# ============================

@bot.tree.command(name="내알림")
async def my_alarm(interaction: discord.Interaction):

    uid = str(interaction.user.id)
    d = data["prealarms"].get(uid, {})

    if not d:
        await interaction.response.send_message("❌ 없음")
        return

    msg = "📌 내 설정\n\n"
    for k, v in d.items():
        msg += f"{k} → {', '.join(map(str,v))}분 전\n"

    await interaction.response.send_message(msg)

# ============================
# 아그로 시간 설정
# ============================

@bot.tree.command(name="아그로")
async def set_agro(interaction: discord.Interaction, 시간: str):

    try:
        시간 = 시간.zfill(4)
        h = int(시간[:2])
        m = int(시간[2:])

        data["agro"]["hour"] = h
        data["agro"]["minute"] = m
        save_data()

        await interaction.response.send_message(
            f"✅ {h:02d}:{m:02d} / {(h+12)%24:02d}:{m:02d}"
        )
    except:
        await interaction.response.send_message("❌ 형식 오류")

# ============================
# 알림 전송
# ============================

async def send_notification(guild, key):
    role = discord.utils.get(guild.roles, name=ROLE_NAMES[key])
    if role:
        await bot.get_channel(CHANNEL_ID).send(f"{role.mention} {key} 알림")

async def send_prealarm(guild, key, mins):

    mentions = []

    for member in guild.members:
        uid = str(member.id)
        d = data["prealarms"].get(uid, {})

        if key in d and mins in d[key]:
            mentions.append(member.mention)

    if mentions:
        await bot.get_channel(CHANNEL_ID).send(
            f"⏱ {' '.join(mentions)}\n{key} {mins}분 전"
        )

# ============================
# 스케줄
# ============================

def get_schedules():

    s = []

    s.append({"h":22,"m":0,"wd":[5,6],"k":"나흐마"})
    s.append({"h":21,"m":0,"wd":[1,3,5],"k":"아티쟁"})

    for h,m in get_agro_times():
        s.append({"h":h,"m":m,"wd":None,"k":"아그로"})

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
            await send_notification(g, s["k"])

        for mins in [5,10,20,30,60]:
            t = now.replace(hour=s["h"], minute=s["m"]) - timedelta(minutes=mins)

            if now.hour == t.hour and now.minute == t.minute:
                await send_prealarm(g, s["k"], mins)

@scheduler.before_loop
async def before():
    await bot.wait_until_ready()
    await asyncio.sleep(60 - datetime.now().second)

# ============================
# 시작
# ============================

@bot.event
async def on_ready():

    if not hasattr(bot, "synced"):
        await bot.tree.sync()
        bot.synced = True

    bot.add_view(AlarmView())
    scheduler.start()

    print("🚀 봇 준비 완료")

bot.run(BOT_TOKEN)
