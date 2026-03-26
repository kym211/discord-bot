import discord
from discord.ext import commands, tasks
import os, json
from datetime import datetime, timedelta
import pytz

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

DATA_FILE = "data.json"

# =====================
# 데이터
# =====================

def load():
    if not os.path.exists(DATA_FILE):
        return {"events": {}}

    with open(DATA_FILE, encoding="utf-8") as f:
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

    "나흐마": {
        "type": "fixed",
        "time": [(22, 0)],
        "weekdays": [5, 6]
    },

    "아그로": {
        "type": "agro"
    },

    "카이라": {
        "type": "hourly"
    },

    "아티쟁": {
        "type": "fixed",
        "time": [(21, 0)],
        "weekdays": [1, 3, 5]
    },

    "슈고45": {
        "type": "minute",
        "minute": 45
    },

    "슈고15": {
        "type": "minute",
        "minute": 15
    },
}

agro_next = {}

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
        description=f"{key} 기준",
        color=0x2b2d31
    )

    if selected:

        embed.add_field(
            name="현재 선택",
            value=", ".join(
                [f"{m}분 전" for m in sorted(selected)]
            ),
            inline=False
        )

    return embed

# =====================
# 버튼
# =====================

class PreButton(discord.ui.Button):

    def __init__(self, key, uid, m):

        super().__init__(
            label=f"{m}분",
            style=discord.ButtonStyle.secondary
        )

        self.key = key
        self.uid = uid
        self.m = m

    async def callback(self, i):

        arr = get_user(self.uid).setdefault(
            self.key,
            {}
        ).setdefault("pre", [])

        if self.m in arr:
            arr.remove(self.m)
        else:
            arr.append(self.m)

        save()

        await i.response.edit_message(
            embed=build_pre_embed(
                self.key,
                self.uid
            ),
            view=PreView(
                self.key,
                self.uid
            )
        )

class PreView(discord.ui.View):

    def __init__(self, key, uid):

        super().__init__(timeout=30)

        for m in [2,5,10,20,30,60]:

            self.add_item(
                PreButton(
                    key,
                    uid,
                    m
                )
            )

    async def on_timeout(self):

        try:
            await self.message.delete()
        except:
            pass

# =====================
# Toggle
# =====================

class ToggleButton(discord.ui.Button):

    def __init__(self, key, uid, row=0):

        on = is_on(uid, key)

        label = f"🟢 {key}" if on else f"🔴 {key}"

        super().__init__(
            label=label,
            style=discord.ButtonStyle.success if on else discord.ButtonStyle.danger,
            row=row
        )

        self.key = key
        self.uid = uid

    async def callback(self, i):

        u = get_user(self.uid)
        u.setdefault(self.key, {})

        ev = DEFAULT_EVENTS.get(self.key, {})

        currently_on = is_on(
            self.uid,
            self.key
        )

        if ev.get("type") == "agro" and not currently_on:

            await i.response.send_message(
                "⚠️ 약간의 시간 오차가 있을수 있습니다",
                ephemeral=True,
                delete_after=30
            )
            return

        u[self.key]["on"] = not currently_on

        save()

        if u[self.key]["on"]:

            await i.response.send_message(
                embed=build_pre_embed(
                    self.key,
                    self.uid
                ),
                view=PreView(
                    self.key,
                    self.uid
                ),
                ephemeral=True
            )

        else:

            await i.response.edit_message(
                view=ControlView(
                    self.uid
                )
            )

# =====================
# Control UI
# =====================

class ControlView(discord.ui.View):

    def __init__(self, uid):

        super().__init__(timeout=30)

        row = 0
        count = 0

        for k in DEFAULT_EVENTS.keys():

            self.add_item(
                ToggleButton(
                    k,
                    uid,
                    row=row
                )
            )

            count += 1

            if count % 5 == 0:
                row += 1

        for k in get_user(uid).keys():

            if k not in DEFAULT_EVENTS:

                self.add_item(
                    ToggleButton(
                        k,
                        uid,
                        row=row
                    )
                )

                count += 1

                if count % 5 == 0:
                    row += 1

    async def on_timeout(self):

        try:
            await self.message.delete()
        except:
            pass

# =====================
# 커스텀 추가
# =====================

class CustomNameModal(discord.ui.Modal):

    name = discord.ui.TextInput(
        label="이름 입력"
    )

    async def on_submit(self, i):

        uid = str(i.user.id)

        name = self.name.value.strip()

        if not name:

            await i.response.send_message(
                "❌ 이름 오류",
                ephemeral=True
            )
            return

        u = get_user(uid)

        if name in u:

            await i.response.send_message(
                "❌ 이미 존재",
                ephemeral=True
            )
            return

        u[name] = {
            "on": True,
            "time": [],
            "pre": []
        }

        save()

        await i.response.send_modal(
            CustomTimeModal(name)
        )

class CustomTimeModal(discord.ui.Modal):

    def __init__(self, name):

        super().__init__(
            title="시간 입력 (예: 0930 1430)"
        )

        self.name = name

        self.time = discord.ui.TextInput(
            label="시간"
        )

        self.add_item(self.time)

    async def on_submit(self, i):

        uid = str(i.user.id)

        raw = self.time.value.split()

        times = []

        for t in raw:

            t = t.zfill(4)

            try:

                h = int(t[:2])
                m = int(t[2:])

                if not (0 <= h < 24 and 0 <= m < 60):
                    raise ValueError

                times.append((h, m))

            except:

                await i.response.send_message(
                    f"❌ 시간 오류: {t}",
                    ephemeral=True
                )
                return

        get_user(uid)[self.name]["time"] = times

        save()

        await i.response.send_message(
            embed=build_pre_embed(
                self.name,
                uid
            ),
            view=PreView(
                self.name,
                uid
            ),
            ephemeral=True
        )

# =====================
# 메인 UI
# =====================

class MainView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 목록",
        style=discord.ButtonStyle.primary
    )
    async def list_btn(self, i, b):

        await i.response.send_message(
            view=ControlView(
                str(i.user.id)
            ),
            ephemeral=True
        )

    @discord.ui.button(
        label="➕ 커스텀 추가",
        style=discord.ButtonStyle.secondary
    )
    async def add_btn(self, i, b):

        await i.response.send_modal(
            CustomNameModal()
        )

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

    ch = bot.get_channel(
        CHANNEL_ID
    )

    if ch:

        await ch.send(
            "🔔 알림 설정",
            view=MainView()
        )

    print("🔥 시작 완료")

bot.run(BOT_TOKEN)
