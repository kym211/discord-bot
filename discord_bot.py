import discord
from discord.ext import commands, tasks
import os, json
from datetime import datetime
import pytz

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# =====================
# 데이터
# =====================

def load():
    if not os.path.exists(DATA_FILE):
        return {
            "enabled": {},
            "custom": {}
        }
    return json.load(open(DATA_FILE))

data = load()
dirty = False

def save():
    global dirty
    dirty = True

# =====================
# 이벤트
# =====================

EVENTS = [
    "나흐마","아티쟁","아그로",
    "시공8","시공23","시공2",
    "카이라","슈고15","슈고45"
]

def is_enabled(uid, key):
    return data["enabled"].get(uid, {}).get(key, False)

# =====================
# 캐시
# =====================

cache = {}

def rebuild(guild):
    global cache
    cache = {k: [] for k in EVENTS}

    for m in guild.members:
        uid = str(m.id)
        for k in EVENTS:
            if is_enabled(uid, k):
                cache[k].append(m)

# =====================
# 커스텀 추가
# =====================

class CustomAddModal(discord.ui.Modal, title="커스텀 알림 추가"):
    time = discord.ui.TextInput(label="시간 (예: 1320)")

    async def on_submit(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)

        t = self.time.value.zfill(4)
        h, m = int(t[:2]), int(t[2:])

        data["custom"].setdefault(uid, [])
        data["custom"][uid].append({"h": h, "m": m})

        save()

        await interaction.response.send_message(
            f"✅ 추가됨: {h:02d}:{m:02d}",
            ephemeral=True
        )

# =====================
# 커스텀 삭제 UI
# =====================

class CustomDeleteButton(discord.ui.Button):
    def __init__(self, uid, idx, t):
        super().__init__(label=f"{t['h']:02d}:{t['m']:02d}", style=discord.ButtonStyle.danger)
        self.uid = uid
        self.idx = idx

    async def callback(self, i: discord.Interaction):
        data["custom"][self.uid].pop(self.idx)
        save()

        await i.response.edit_message(view=CustomDeleteView(self.uid))

class CustomDeleteView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=120)
        arr = data["custom"].get(uid, [])

        if not arr:
            self.add_item(discord.ui.Button(label="없음", disabled=True))
            return

        for idx, t in enumerate(arr):
            self.add_item(CustomDeleteButton(uid, idx, t))

# =====================
# ON/OFF
# =====================

class ToggleButton(discord.ui.Button):
    def __init__(self, key, uid):
        enabled = is_enabled(uid, key)
        style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger
        super().__init__(label=f"{key} {'ON' if enabled else 'OFF'}", style=style)

        self.key = key
        self.uid = uid

    async def callback(self, i: discord.Interaction):
        data["enabled"].setdefault(self.uid, {})
        data["enabled"][self.uid][self.key] = not is_enabled(self.uid, self.key)

        save()
        rebuild(i.guild)

        await i.response.edit_message(view=ControlView(self.uid))

class ControlView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=120)
        for k in EVENTS:
            self.add_item(ToggleButton(k, uid))

# =====================
# 메인 UI
# =====================

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⚙️ ON/OFF", custom_id="main_toggle")
    async def toggle(self, i, b):
        await i.response.send_message(view=ControlView(str(i.user.id)), ephemeral=True)

    @discord.ui.button(label="➕ 커스텀 추가", custom_id="custom_add")
    async def add(self, i, b):
        await i.response.send_modal(CustomAddModal())

    @discord.ui.button(label="🗑 커스텀 삭제", custom_id="custom_del")
    async def delete(self, i, b):
        await i.response.send_message(
            view=CustomDeleteView(str(i.user.id)),
            ephemeral=True
        )

# =====================
# 알림
# =====================

async def send_event(key):
    users = cache.get(key, [])
    if users:
        await bot.get_channel(CHANNEL_ID).send(
            f"{' '.join([u.mention for u in users])}\n🔔 {key}"
        )

async def send_custom():
    now = datetime.now(KST)

    for uid, arr in data["custom"].items():
        for t in arr:
            if now.hour == t["h"] and now.minute == t["m"]:
                user = bot.get_user(int(uid))
                if user:
                    try:
                        await user.send(f"🔔 개인 알림 {t['h']:02d}:{t['m']:02d}")
                    except:
                        pass

# =====================
# 스케줄
# =====================

@tasks.loop(minutes=1)
async def scheduler():
    now = datetime.now(KST)

    if now.hour == 22 and now.weekday() in [5,6]:
        await send_event("나흐마")

    if now.hour == 21 and now.weekday() in [1,3,5]:
        await send_event("아티쟁")

    if now.minute == 0:
        await send_event("카이라")

    if now.minute == 15:
        await send_event("슈고15")

    if now.minute == 45:
        await send_event("슈고45")

    await send_custom()

# =====================
# 저장
# =====================

@tasks.loop(seconds=10)
async def autosave():
    global dirty
    if dirty:
        json.dump(data, open(DATA_FILE,"w"))
        dirty = False

# =====================
# 실행
# =====================

@bot.event
async def on_ready():
    if not hasattr(bot,"ready"):
        ch = bot.get_channel(CHANNEL_ID)
        await ch.send("🔔 알림 설정", view=MainView())

        rebuild(bot.guilds[0])

        scheduler.start()
        autosave.start()

        bot.ready = True

    print("🔥 완전체 최종 실행")

bot.run(BOT_TOKEN)
