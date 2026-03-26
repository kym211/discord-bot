import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json
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

DATA_FILE = "data.json"

# ============================
# 데이터 로드/저장
# ============================

def load():
    if not os.path.exists(DATA_FILE):
        return {
            "prealarms": {},
            "agro": {"hour": 0, "minute": 0},
            "enabled": {}
        }
    return json.load(open(DATA_FILE))

def save():
    json.dump(data, open(DATA_FILE, "w"))

data = load()

# ============================
# 설정
# ============================

EVENTS = ["나흐마","아티쟁","아그로","시공8","시공23","시공2","카이라"]
MAX_SELECT = 3

# ============================
# 공통
# ============================

def get_user_times(uid, key):
    return data["prealarms"].get(uid, {}).get(key, [])

def is_enabled(uid, key):
    return data["enabled"].get(uid, {}).get(key, True)

def get_agro_times():
    h = data["agro"]["hour"]
    m = data["agro"]["minute"]
    base = datetime.now(KST).replace(hour=h, minute=m, second=0, microsecond=0)
    return [(base.hour, base.minute),
            ((base + timedelta(hours=12)).hour, (base + timedelta(hours=12)).minute)]

# ============================
# 사전알림 버튼
# ============================

class PreAlarmButton(discord.ui.Button):
    def __init__(self, minutes, key, user_id):
        uid = str(user_id)
        selected = minutes in get_user_times(uid, key)

        style = discord.ButtonStyle.success if selected else discord.ButtonStyle.secondary
        label = f"{minutes}분"

        super().__init__(label=label, style=style)

        self.minutes = minutes
        self.key = key
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        uid = str(self.user_id)

        data["prealarms"].setdefault(uid, {})
        data["prealarms"][uid].setdefault(self.key, [])

        arr = data["prealarms"][uid][self.key]

        if self.minutes in arr:
            arr.remove(self.minutes)
        else:
            if len(arr) >= MAX_SELECT:
                await interaction.response.send_message("❌ 최대 3개", ephemeral=True)
                return
            arr.append(self.minutes)

        save()

        view = PreAlarmView(self.key, uid)
        embed = make_embed(self.key, uid)

        await interaction.response.edit_message(embed=embed, view=view)

# ============================
# 사전알림 View
# ============================

class PreAlarmView(discord.ui.View):
    def __init__(self, key, user_id):
        super().__init__(timeout=120)

        for t in [2,5,10,20,30,60]:
            self.add_item(PreAlarmButton(t, key, user_id))

# ============================
# ON/OFF 버튼
# ============================

class ToggleButton(discord.ui.Button):
    def __init__(self, key, user_id):
        uid = str(user_id)
        enabled = is_enabled(uid, key)

        style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger
        label = f"{key} {'ON' if enabled else 'OFF'}"

        super().__init__(label=label, style=style)

        self.key = key
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        uid = str(self.user_id)

        data["enabled"].setdefault(uid, {})
        current = data["enabled"][uid].get(self.key, True)
        data["enabled"][uid][self.key] = not current

        save()

        view = AlarmControlView(uid)
        await interaction.response.edit_message(view=view)

class AlarmControlView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)

        for key in EVENTS:
            self.add_item(ToggleButton(key, user_id))

# ============================
# 시간 입력 모달
# ============================

class TimeModal(discord.ui.Modal, title="아그로 시간 설정"):
    time_input = discord.ui.TextInput(label="시간 입력 (예: 0930)")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            t = self.time_input.value.zfill(4)
            h = int(t[:2])
            m = int(t[2:])

            data["agro"]["hour"] = h
            data["agro"]["minute"] = m
            save()

            await interaction.response.send_message(
                f"✅ {h:02d}:{m:02d} / {(h+12)%24:02d}:{m:02d}",
                ephemeral=True
            )
        except:
            await interaction.response.send_message("❌ 형식 오류", ephemeral=True)

# ============================
# 임베드 생성
# ============================

def make_embed(key, uid):
    times = get_user_times(uid, key)
    txt = ", ".join([f"{t}분" for t in sorted(times)]) if times else "없음"

    return discord.Embed(
        title=f"{key} 설정",
        description=f"현재 사전알림: {txt}",
        color=discord.Color.gold()
    )

# ============================
# 메인 View
# ============================

class AlarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def open_menu(self, interaction, key):
        uid = str(interaction.user.id)
        embed = make_embed(key, uid)
        view = PreAlarmView(key, uid)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🌙 나흐마", custom_id="nahma")
    async def b1(self, i, b): await self.open_menu(i, "나흐마")

    @discord.ui.button(label="📅 아티쟁", custom_id="arti")
    async def b2(self, i, b): await self.open_menu(i, "아티쟁")

    @discord.ui.button(label="⏰ 아그로", custom_id="agro")
    async def b3(self, i, b): await self.open_menu(i, "아그로")

    @discord.ui.button(label="🔔 시공20", custom_id="s8")
    async def b4(self, i, b): await self.open_menu(i, "시공8")

    @discord.ui.button(label="🔔 시공23", custom_id="s23")
    async def b5(self, i, b): await self.open_menu(i, "시공23")

    @discord.ui.button(label="🔔 시공02", custom_id="s2")
    async def b6(self, i, b): await self.open_menu(i, "시공2")

    @discord.ui.button(label="🔥 카이라", custom_id="kaira")
    async def b7(self, i, b): await self.open_menu(i, "카이라")

    @discord.ui.button(label="⚙️ ON/OFF 설정", custom_id="toggle")
    async def b8(self, i, b):
        await i.response.send_message("알림 ON/OFF", view=AlarmControlView(i.user.id), ephemeral=True)

    @discord.ui.button(label="⏱ 아그로 시간", custom_id="modal")
    async def b9(self, i, b):
        await i.response.send_modal(TimeModal())

# ============================
# 알림 전송
# ============================

async def send_notification(guild, key):
    mentions = []

    for m in guild.members:
        uid = str(m.id)
        if is_enabled(uid, key):
            mentions.append(m.mention)

    if mentions:
        await bot.get_channel(CHANNEL_ID).send(
            f"{' '.join(mentions)}\n🔔 {key} 알림"
        )

async def send_prealarm(guild, key, mins):
    mentions = []

    for m in guild.members:
        uid = str(m.id)
        if is_enabled(uid, key) and mins in get_user_times(uid, key):
            mentions.append(m.mention)

    if mentions:
        await bot.get_channel(CHANNEL_ID).send(
            f"⏱ {' '.join(mentions)} {key} {mins}분 전"
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

    for h in range(24):
        s.append({"h":h,"m":0,"wd":None,"k":"카이라"})

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

        for mins in [2,5,10,20,30,60]:
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
    if not hasattr(bot, "ready"):
        await bot.tree.sync()
        bot.add_view(AlarmView())
        scheduler.start()
        bot.ready = True

    print("🚀 최종 통합 버전 실행")

bot.run(BOT_TOKEN)
