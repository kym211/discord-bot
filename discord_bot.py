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
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# =====================
# 데이터
# =====================

def load():
    if not os.path.exists(DATA_FILE):
        return {"events": {}}
    with open(DATA_FILE) as f:
        return json.load(f)

data = load()
dirty = False

def save():
    global dirty
    dirty = True

# =====================
# 기본 이벤트
# =====================

DEFAULT_EVENTS = {
    "나흐마": {"time": [(22, 0)], "weekdays": [5, 6]},
    "아티쟁": {"time": [(21, 0)], "weekdays": [1, 3, 5]},
    "시공": {"time": [(20,0),(23,0),(2,0)]},  # ✅ 추가
}

# =====================
# 유저 데이터
# =====================

def get_user(uid):
    data["events"].setdefault(uid, {})
    return data["events"][uid]

def is_on(uid, key):
    return get_user(uid).get(key, {}).get("on", False)

def get_pre(uid, key):
    return get_user(uid).get(key, {}).get("pre", [])

# =====================
# EMBED
# =====================

def build_pre_embed(key, uid):
    selected = get_pre(uid, key)

    embed = discord.Embed(
        title="⏱ 사전 알림 설정",
        description=f"{key} 알림 기준",
        color=0x2b2d31
    )

    if selected:
        embed.add_field(
            name="현재 선택",
            value=", ".join([f"{m}분 전" for m in sorted(selected)]),
            inline=False
        )

    return embed

# =====================
# 사전 알림 버튼
# =====================

class PreButton(discord.ui.Button):
    def __init__(self, key, uid, m):
        super().__init__(
            label=f"{m}분",
            style=discord.ButtonStyle.success if m in get_pre(uid, key) else discord.ButtonStyle.secondary,
            row=0 if m in [2,5,10] else 1
        )
        self.key = key
        self.uid = uid
        self.m = m

    async def callback(self, i):
        if not is_on(self.uid, self.key):
            await i.response.send_message("❌ ON 먼저", ephemeral=True)
            return

        arr = get_user(self.uid).setdefault(self.key, {}).setdefault("pre", [])

        if self.m in arr:
            arr.remove(self.m)
        else:
            arr.append(self.m)

        save()

        await i.response.edit_message(
            embed=build_pre_embed(self.key, self.uid),
            view=PreView(self.key, self.uid)
        )

class PreView(discord.ui.View):
    def __init__(self, key, uid):
        super().__init__(timeout=120)
        for m in [2,5,10,20,30,60]:
            self.add_item(PreButton(key, uid, m))

# =====================
# 토글 버튼
# =====================

class ToggleButton(discord.ui.Button):
    def __init__(self, key, uid):
        on = is_on(uid, key)

        super().__init__(
            label=f"🟢 {key}" if on else f"🔴 {key}",
            style=discord.ButtonStyle.success if on else discord.ButtonStyle.danger
        )
        self.key = key
        self.uid = uid

    async def callback(self, i):
        u = get_user(self.uid)
        u.setdefault(self.key, {})
        u[self.key]["on"] = not is_on(self.uid, self.key)
        save()

        if u[self.key]["on"]:
            await i.response.send_message(
                embed=build_pre_embed(self.key, self.uid),
                view=PreView(self.key, self.uid),
                ephemeral=True
            )
        else:
            await i.response.edit_message(view=ControlView(self.uid))

# =====================
# 삭제 버튼
# =====================

class DeleteButton(discord.ui.Button):
    def __init__(self, key, uid):
        super().__init__(label=f"❌ {key}", style=discord.ButtonStyle.secondary)
        self.key = key
        self.uid = uid

    async def callback(self, i):
        u = get_user(self.uid)

        if self.key in u:
            del u[self.key]
            save()

        await i.response.edit_message(
            content=f"{self.key} 삭제됨",
            view=ControlView(self.uid)
        )

# =====================
# 컨트롤
# =====================

class ControlView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=120)

        # 기본
        for k in DEFAULT_EVENTS.keys():
            self.add_item(ToggleButton(k, uid))

        # 커스텀
        for k in get_user(uid).keys():
            if k not in DEFAULT_EVENTS:
                self.add_item(ToggleButton(k, uid))
                self.add_item(DeleteButton(k, uid))  # ✅ 삭제 추가

# =====================
# 커스텀 (에러 수정)
# =====================

class CustomNameModal(discord.ui.Modal, title="커스텀 이름"):
    name = discord.ui.TextInput(label="이름")

    async def on_submit(self, i):
        uid = str(i.user.id)
        name = self.name.value.strip()

        if not name:
            await i.response.send_message("❌ 이름 비어있음", ephemeral=True)
            return

        u = get_user(uid)

        if name in u:
            await i.response.send_message("❌ 이미 존재", ephemeral=True)
            return

        u[name] = {"on": True, "time": [], "pre": []}
        save()

        await i.response.send_message(
            f"{name} 생성됨 → 시간 입력",
            view=CustomTimeView(name, uid),
            ephemeral=True
        )

# =====================
# 시간 입력
# =====================

class CustomTimeButton(discord.ui.Button):
    def __init__(self, name, uid):
        super().__init__(label="시간 입력", style=discord.ButtonStyle.primary)
        self.name = name
        self.uid = uid

    async def callback(self, i):
        await i.response.send_modal(CustomTimeModal(self.name))

class CustomTimeView(discord.ui.View):
    def __init__(self, name, uid):
        super().__init__(timeout=120)
        self.add_item(CustomTimeButton(name, uid))

class CustomTimeModal(discord.ui.Modal, title="시간 설정"):
    time = discord.ui.TextInput(label="예: 0930")

    def __init__(self, name):
        super().__init__()
        self.name = name

    async def on_submit(self, i):
        uid = str(i.user.id)

        try:
            t = self.time.value.zfill(4)
            h, m = int(t[:2]), int(t[2:])

            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError

        except:
            await i.response.send_message("❌ 시간 형식 오류", ephemeral=True)
            return

        get_user(uid)[self.name]["time"] = [(h, m)]
        save()

        await i.response.send_message(
            embed=build_pre_embed(self.name, uid),
            view=PreView(self.name, uid),
            ephemeral=True
        )

# =====================
# 메인 UI
# =====================

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📋 목록", style=discord.ButtonStyle.primary)
    async def list_btn(self, i, b):
        await i.response.send_message(
            view=ControlView(str(i.user.id)),
            ephemeral=True
        )

    @discord.ui.button(label="➕ 커스텀", style=discord.ButtonStyle.secondary)
    async def custom_btn(self, i, b):
        await i.response.send_modal(CustomNameModal())

# =====================
# 알림
# =====================

async def send_alert(key, suffix=""):
    for g in bot.guilds:
        for m in g.members:
            if m.bot:
                continue
            uid = str(m.id)
            if is_on(uid, key):
                try:
                    await m.send(f"🔔 {key}{suffix}")
                except:
                    pass

# =====================
# 스케줄
# =====================

@tasks.loop(minutes=1)
async def loop():
    now = datetime.now(KST)
    h, m = now.hour, now.minute

    for key, v in DEFAULT_EVENTS.items():
        for eh, em in v["time"]:
            event_total = eh * 60 + em
            now_total = h * 60 + m
            diff = event_total - now_total
            if diff <= 0:
                diff += 1440

            for g in bot.guilds:
                for member in g.members:
                    if member.bot:
                        continue
                    uid = str(member.id)

                    if not is_on(uid, key):
                        continue

                    # 정시
                    if diff == 0:
                        await member.send(f"🔔 {key}")

                    # 사전 알림
                    if diff in get_pre(uid, key):
                        await member.send(f"⏱ {key} {diff}분 전")

# =====================
# 저장
# =====================

@tasks.loop(seconds=10)
async def save_loop():
    global dirty
    if dirty:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        dirty = False

# =====================
# 실행
# =====================

_ready_sent = False

@bot.event
async def on_ready():
    global _ready_sent
    if _ready_sent:
        return
    _ready_sent = True

    ch = bot.get_channel(CHANNEL_ID)
    if ch:
        await ch.send("🔔 알림 설정", view=MainView())

    loop.start()
    save_loop.start()

    print("🔥 시작 완료")

bot.run(BOT_TOKEN)
