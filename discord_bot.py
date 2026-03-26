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
    "나흐마": {"type": "fixed", "time": [(22, 0)], "weekdays": [5, 6]},
    "아그로": {"type": "agro"},
    "카이라": {"type": "hourly"},
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
            value=", ".join([f"{m}분 전" for m in sorted(selected)]),
            inline=False
        )

    return embed


# =====================
# Pre View
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

    async def callback(self, interaction):

        arr = get_user(self.uid).setdefault(
            self.key,
            {}
        ).setdefault("pre", [])

        if self.m in arr:
            arr.remove(self.m)
        else:
            arr.append(self.m)

        save()

        await interaction.response.edit_message(
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

        for m in [2, 5, 10, 20, 30, 60]:
            self.add_item(
                PreButton(key, uid, m)
            )

    async def on_timeout(self):

        try:
            await self.message.delete()
        except:
            pass


# =====================
# Toggle Button
# =====================

class ToggleButton(discord.ui.Button):

    def __init__(self, key, uid):

        on = is_on(uid, key)

        label = f"🟢 {key}" if on else f"🔴 {key}"

        super().__init__(
            label=label,
            style=discord.ButtonStyle.success if on else discord.ButtonStyle.danger
        )

        self.key = key
        self.uid = uid

    async def callback(self, interaction):

        u = get_user(self.uid)
        u.setdefault(self.key, {})

        ev = DEFAULT_EVENTS.get(self.key, {})

        currently_on = is_on(
            self.uid,
            self.key
        )

        # 아그로 버튼 설명
        if ev.get("type") == "agro" and not currently_on:

            await interaction.response.send_message(
                "⚠️ 약간의 시간 오차가 있을수 있습니다",
                ephemeral=True,
                delete_after=30
            )

            return

        u[self.key]["on"] = not currently_on

        save()

        if u[self.key]["on"]:

            await interaction.response.send_message(
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

            await interaction.response.edit_message(
                view=ControlView(
                    self.uid
                )
            )


# =====================
# Control View
# =====================

class ControlView(discord.ui.View):

    def __init__(self, uid):

        super().__init__(timeout=30)

        for k in DEFAULT_EVENTS.keys():

            self.add_item(
                ToggleButton(
                    k,
                    uid
                )
            )

    async def on_timeout(self):

        try:
            await self.message.delete()
        except:
            pass


# =====================
# Main View
# =====================

class MainView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 목록",
        style=discord.ButtonStyle.primary
    )

    async def list_btn(self, interaction, button):

        await interaction.response.send_message(
            view=ControlView(
                str(interaction.user.id)
            ),
            ephemeral=True
        )


# =====================
# 저장 루프
# =====================

@tasks.loop(seconds=10)

async def save_loop():

    global dirty

    if dirty:

        with open(
            DATA_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

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

    ch = bot.get_channel(
        CHANNEL_ID
    )

    if ch:

        msg = await ch.send(
            "🔔 알림 설정",
            view=MainView()
        )

    save_loop.start()

    print("🔥 시작 완료")


bot.run(BOT_TOKEN)
