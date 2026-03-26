import discord
from discord.ext import commands, tasks
import os, json, asyncio, logging, shutil
from datetime import datetime, timedelta
import pytz

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
# 로깅
# ============================

logging.basicConfig(level=logging.INFO)

# ============================
# 데이터
# ============================

def load():
    if not os.path.exists(DATA_FILE):
        return {"prealarms": {}, "agro": {"hour": 0, "minute": 0}, "enabled": {}}
    return json.load(open(DATA_FILE))

data = load()
dirty = False

def mark_dirty():
    global dirty
    dirty = True

# ============================
# 설정
# ============================

EVENTS = ["나흐마","아티쟁","아그로","시공8","시공23","시공2","카이라"]
MAX_SELECT = 3

# ============================
# 캐시
# ============================

subscribers_cache = {}

def rebuild_cache(guild):
    global subscribers_cache
    subscribers_cache = {k: [] for k in EVENTS}

    for m in guild.members:
        uid = str(m.id)
        for key in EVENTS:
            if data["enabled"].get(uid, {}).get(key, True):
                subscribers_cache[key].append(m)

# ============================
# 공통
# ============================

def get_user_times(uid, key):
    return data["prealarms"].get(uid, {}).get(key, [])

def get_agro_times():
    h = data["agro"]["hour"]
    m = data["agro"]["minute"]

    base = datetime.now(KST).replace(hour=h, minute=m, second=0, microsecond=0)

    return [
        (base.hour, base.minute),
        ((base + timedelta(hours=12)).hour, (base + timedelta(hours=12)).minute)
    ]

# ============================
# UI
# ============================

class PreAlarmButton(discord.ui.Button):
    def __init__(self, minutes, key, user_id):
        uid = str(user_id)
        selected = minutes in get_user_times(uid, key)

        style = discord.ButtonStyle.success if selected else discord.ButtonStyle.secondary
        super().__init__(label=f"{minutes}분", style=style)

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

        mark_dirty()
        rebuild_cache(interaction.guild)

        await interaction.response.edit_message(
            view=PreAlarmView(self.key, uid)
        )

class PreAlarmView(discord.ui.View):
    def __init__(self, key, user_id):
        super().__init__(timeout=120)
        for t in [2,5,10,20,30,60]:
            self.add_item(PreAlarmButton(t, key, user_id))

class ToggleButton(discord.ui.Button):
    def __init__(self, key, user_id):
        uid = str(user_id)
        enabled = data["enabled"].get(uid, {}).get(key, True)

        style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger
        super().__init__(label=f"{key} {'ON' if enabled else 'OFF'}", style=style)

        self.key = key
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        uid = str(self.user_id)

        data["enabled"].setdefault(uid, {})
        current = data["enabled"][uid].get(self.key, True)
        data["enabled"][uid][self.key] = not current

        mark_dirty()
        rebuild_cache(interaction.guild)

        await interaction.response.edit_message(
            view=AlarmControlView(uid)
        )

class AlarmControlView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        for k in EVENTS:
            self.add_item(ToggleButton(k, user_id))

class TimeModal(discord.ui.Modal, title="아그로 시간 설정"):
    time_input = discord.ui.TextInput(label="예: 0930")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            t = self.time_input.value.zfill(4)
            h, m = int(t[:2]), int(t[2:])
            data["agro"]["hour"] = h
            data["agro"]["minute"] = m

            mark_dirty()

            await interaction.response.send_message(
                f"✅ {h:02d}:{m:02d} / {(h+12)%24:02d}:{m:02d}",
                ephemeral=True
            )
        except:
            await interaction.response.send_message("❌ 형식 오류", ephemeral=True)

class AlarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def open_menu(self, interaction, key):
        await interaction.response.send_message(
            f"{key} 설정",
            view=PreAlarmView(key, interaction.user.id),
            ephemeral=True
        )

    @discord.ui.button(label="🌙 나흐마", custom_id="btn_nahma")
    async def b1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_menu(interaction, "나흐마")

    @discord.ui.button(label="📅 아티쟁", custom_id="btn_arti")
    async def b2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_menu(interaction, "아티쟁")

    @discord.ui.button(label="⏰ 아그로", custom_id="btn_agro")
    async def b3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_menu(interaction, "아그로")

    @discord.ui.button(label="🔔 시공20", custom_id="btn_s8")
    async def b4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_menu(interaction, "시공8")

    @discord.ui.button(label="🔔 시공23", custom_id="btn_s23")
    async def b5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_menu(interaction, "시공23")

    @discord.ui.button(label="🔔 시공02", custom_id="btn_s2")
    async def b6(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_menu(interaction, "시공2")

    @discord.ui.button(label="🔥 카이라", custom_id="btn_kaira")
    async def b7(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_menu(interaction, "카이라")

    @discord.ui.button(label="⚙️ ON/OFF", custom_id="btn_toggle")
    async def b8(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            view=AlarmControlView(interaction.user.id),
            ephemeral=True
        )

    @discord.ui.button(label="⏱ 아그로 시간", custom_id="btn_time")
    async def b9(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TimeModal())

# ============================
# 알림 전송
# ============================

async def send_notification(key):
    users = subscribers_cache.get(key, [])
    if users:
        await bot.get_channel(CHANNEL_ID).send(
            f"{' '.join([u.mention for u in users])}\n🔔 {key}"
        )

async def send_prealarm(key, mins):
    users = []
    for m in subscribers_cache.get(key, []):
        uid = str(m.id)
        if mins in get_user_times(uid, key):
            users.append(m)

    if users:
        await bot.get_channel(CHANNEL_ID).send(
            f"⏱ {' '.join([u.mention for u in users])} {key} {mins}분 전"
        )

# ============================
# 스케줄
# ============================

def schedules():
    s = []
    s.append((22,0,"나흐마",[5,6]))
    s.append((21,0,"아티쟁",[1,3,5]))

    for h,m in get_agro_times():
        s.append((h,m,"아그로",None))

    s += [(20,0,"시공8",None),(23,0,"시공23",None),(2,0,"시공2",None)]

    for h in range(24):
        s.append((h,0,"카이라",None))

    return s

@tasks.loop(minutes=1)
async def scheduler():
    try:
        now = datetime.now(KST)

        for h,m,k,wd in schedules():

            if wd and now.weekday() not in wd:
                continue

            if now.hour == h and now.minute == m:
                await send_notification(k)

            for mins in [2,5,10,20,30,60]:
                t = now.replace(hour=h, minute=m) - timedelta(minutes=mins)

                if now.hour == t.hour and now.minute == t.minute:
                    await send_prealarm(k, mins)

    except Exception as e:
        logging.error(f"스케줄 오류: {e}")

# ============================
# 저장 / 백업
# ============================

@tasks.loop(seconds=10)
async def auto_save():
    global dirty
    if dirty:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f)
        dirty = False

@tasks.loop(hours=6)
async def backup():
    shutil.copy(DATA_FILE, "backup.json")

# ============================
# 실행
# ============================

@bot.event
async def on_ready():
    if not hasattr(bot, "ready"):
        bot.add_view(AlarmView())

        channel = bot.get_channel(CHANNEL_ID)
        await channel.send("🔔 알림 설정", view=AlarmView())

        rebuild_cache(bot.guilds[0])

        scheduler.start()
        auto_save.start()
        backup.start()

        bot.ready = True

    print("🚀 완전 최종 실행")

@bot.event
async def on_disconnect():
    print("❌ 연결 끊김")

@bot.event
async def on_resumed():
    print("✅ 재연결")

bot.run(BOT_TOKEN)
