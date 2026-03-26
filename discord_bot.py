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
    "카이라": {"time": [(h, 0) for h in range(24)]},
    "슈고15": {"time": [(h, 15) for h in range(24)]},
    "슈고45": {"time": [(h, 45) for h in range(24)]},
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
# UI - 사전 알림
# =====================

class PreButton(discord.ui.Button):
    def __init__(self, key, uid, m):
        selected = m in get_pre(uid, key)
        style = discord.ButtonStyle.success if selected else discord.ButtonStyle.secondary
        super().__init__(label=f"{m}분", style=style)
        self.key = key
        self.uid = uid
        self.m = m

    async def callback(self, i):
        if not is_on(self.uid, self.key):
            await i.response.send_message("❌ ON 먼저", ephemeral=True)
            return

        u = get_user(self.uid)
        u.setdefault(self.key, {}).setdefault("pre", [])
        arr = u[self.key]["pre"]

        if self.m in arr:
            arr.remove(self.m)
        else:
            arr.append(self.m)

        save()
        await i.response.edit_message(view=PreView(self.key, self.uid))

class PreView(discord.ui.View):
    def __init__(self, key, uid):
        super().__init__(timeout=120)
        for m in [2, 5, 10, 20, 30, 60]:
            self.add_item(PreButton(key, uid, m))

    async def on_timeout(self):
        # 타임아웃 시 조용히 종료 (에러 방지)
        pass

# =====================
# ON/OFF 버튼
# =====================

class ToggleButton(discord.ui.Button):
    def __init__(self, key, uid):
        style = discord.ButtonStyle.success if is_on(uid, key) else discord.ButtonStyle.danger
        super().__init__(label=f"{key}", style=style)
        self.key = key
        self.uid = uid

    async def callback(self, i):
        u = get_user(self.uid)
        u.setdefault(self.key, {})
        u[self.key]["on"] = not is_on(self.uid, self.key)
        save()

        if u[self.key]["on"]:
            await i.response.send_message(
                f"{self.key} 사전알림 설정",
                view=PreView(self.key, self.uid),
                ephemeral=True
            )
        else:
            await i.response.edit_message(view=ControlView(self.uid))

class ControlView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=120)
        # ✅ 수정: 중복 키 제거 (DEFAULT + 커스텀 합산 후 set으로 중복 방지)
        default_keys = list(DEFAULT_EVENTS.keys())
        custom_keys = [k for k in get_user(uid).keys() if k not in DEFAULT_EVENTS]
        for k in default_keys + custom_keys:
            self.add_item(ToggleButton(k, uid))

# =====================
# 커스텀
# =====================

class CustomNameModal(discord.ui.Modal, title="커스텀 이름"):
    name = discord.ui.TextInput(label="이름")

    async def on_submit(self, i):
        uid = str(i.user.id)
        name = self.name.value
        u = get_user(uid)
        u[name] = {"on": True, "time": [], "pre": []}
        save()
        await i.response.send_modal(CustomTimeModal(name))

class CustomTimeModal(discord.ui.Modal, title="시간 설정"):
    time = discord.ui.TextInput(label="예: 0930")

    def __init__(self, name):
        super().__init__()
        self.name = name

    async def on_submit(self, i):
        uid = str(i.user.id)
        t = self.time.value.zfill(4)
        h, m = int(t[:2]), int(t[2:])
        get_user(uid)[self.name]["time"] = [(h, m)]
        save()
        await i.response.send_message(
            "사전알림 설정",
            view=PreView(self.name, uid),
            ephemeral=True
        )

# =====================
# 메인 UI
# =====================

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⚙️ ON/OFF", custom_id="toggle")
    async def t(self, i, b):
        await i.response.send_message(
            view=ControlView(str(i.user.id)),
            ephemeral=True
        )

    @discord.ui.button(label="➕ 커스텀", custom_id="custom")
    async def c(self, i, b):
        await i.response.send_modal(CustomNameModal())

# =====================
# 알림 전송
# =====================

async def send_alert(key, suffix=""):
    """기본 이벤트 알림 (모든 서버 멤버 대상)"""
    for g in bot.guilds:
        for m in g.members:
            if m.bot:
                continue
            uid = str(m.id)
            if is_on(uid, key):
                try:
                    await m.send(f"🔔 {key}{suffix}")
                except Exception:
                    pass

async def send_custom_alert(uid, key, suffix=""):
    """커스텀 이벤트 알림 (특정 유저 대상)"""
    user = bot.get_user(int(uid))
    if user:
        try:
            await user.send(f"🔔 {key}{suffix}")
        except Exception:
            pass

# =====================
# 스케줄
# =====================

@tasks.loop(minutes=1)
async def loop():
    now = datetime.now(KST)
    h, m, wd = now.hour, now.minute, now.weekday()

    # ── 기본 이벤트 ──
    for key, v in DEFAULT_EVENTS.items():
        for eh, em in v["time"]:
            if h == eh and m == em:
                if not v.get("weekdays") or wd in v["weekdays"]:
                    await send_alert(key)

    # ✅ 수정: 기본 이벤트 사전 알림
    for key, v in DEFAULT_EVENTS.items():
        if not v.get("weekdays") or wd in v["weekdays"]:
            for eh, em in v["time"]:
                # 이벤트까지 남은 분 계산
                event_total = eh * 60 + em
                now_total = h * 60 + m
                diff = event_total - now_total
                if diff <= 0:
                    diff += 24 * 60  # 자정 넘김 처리

                # 각 유저의 pre 목록과 비교
                for g in bot.guilds:
                    for member in g.members:
                        if member.bot:
                            continue
                        uid = str(member.id)
                        if is_on(uid, key) and diff in get_pre(uid, key):
                            try:
                                await member.send(f"⏱ {key} {diff}분 전")
                            except Exception:
                                pass

    # ── 커스텀 이벤트 ──
    for uid, u in list(data["events"].items()):
        for key, v in u.items():
            if not v.get("on") or not v.get("time"):
                continue
            for eh, em in v["time"]:
                if h == eh and m == em:
                    await send_custom_alert(uid, key)

                # ✅ 수정: 커스텀 이벤트 사전 알림
                event_total = eh * 60 + em
                now_total = h * 60 + m
                diff = event_total - now_total
                if diff <= 0:
                    diff += 24 * 60

                if diff in v.get("pre", []):
                    await send_custom_alert(uid, key, suffix=f" {diff}분 전")

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

_ready_sent = False  # ✅ 수정: 전역 플래그로 중복 실행 방지

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

    print("🔥 봇 시작 완료")

bot.run(BOT_TOKEN)
