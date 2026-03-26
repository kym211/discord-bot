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

def load():
    if not os.path.exists(DATA_FILE):
        return {"events": {}}

    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)

data = load()
dirty = False

def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

def get_user(uid):
    data["events"].setdefault(uid, {})
    return data["events"][uid]

def is_on(uid, key):
    return get_user(uid).get(key, {}).get("on", False)

def get_pre(uid, key):
    return get_user(uid).get(key, {}).get("pre", [])

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

        currently_on = is_on(
            self.uid,
            self.key
        )

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

class ControlView(discord.ui.View):

    def __init__(self, uid):

        super().__init__(timeout=30)

        row = 0
        count = 0

        keys = list(DEFAULT_EVENTS.keys()) + [
            k for k in get_user(uid).keys()
            if k not in DEFAULT_EVENTS
        ]

        for k in keys:

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

# =====================
# /아그로 명령
# =====================

@bot.command(name="아그로")
async def agro_cmd(ctx, time_str: str = "", mode: str = ""):

    uid = str(ctx.author.id)

    try:

        t = time_str.zfill(4)

        h = int(t[:2])
        m = int(t[2:])

    except:

        await ctx.reply(
            "❌ 형식 오류\n"
            "/아그로 0600\n"
            "/아그로 0130 후에",
            delete_after=30
        )
        return

    now = datetime.now(KST)

    if mode.strip() == "후에":

        delta = timedelta(
            hours=h,
            minutes=m
        )

        start = (
            now + delta
        ).replace(
            second=0,
            microsecond=0
        )

    else:

        start = now.replace(
            hour=h,
            minute=m,
            second=0,
            microsecond=0
        )

        if start <= now:

            start += timedelta(
                hours=12
            )

    agro_next[uid] = start

    u = get_user(uid)

    u.setdefault("아그로", {})

    u["아그로"]["on"] = True
    u["아그로"]["next"] = start.isoformat()

    save()

    await ctx.reply(
        f"✅ 아그로 설정 완료\n"
        f"다음: {start.strftime('%H:%M')}",
        delete_after=30
    )

# =====================
# LOOP
# =====================

@tasks.loop(seconds=60)
async def check_loop():

    now = datetime.now(KST)

    for uid, next_t in list(agro_next.items()):

        if now >= next_t:

            ch = bot.get_channel(
                CHANNEL_ID
            )

            if ch:

                user = bot.get_user(
                    int(uid)
                )

                await ch.send(
                    f"{user.mention} ⚔️ 아그로 시간!"
                )

            new_time = next_t + timedelta(hours=12)

            agro_next[uid] = new_time

            get_user(uid)["아그로"]["next"] = new_time.isoformat()

            save()

# =====================
# READY
# =====================

_ready_sent = False

@bot.event
async def on_ready():

    global _ready_sent

    if _ready_sent:
        return

    _ready_sent = True

    # 아그로 복원

    for uid, udata in data["events"].items():

        if "아그로" in udata:

            agro_data = udata["아그로"]

            if (
                agro_data.get("on")
                and "next" in agro_data
            ):

                try:

                    agro_next[uid] = datetime.fromisoformat(
                        agro_data["next"]
                    )

                except:

                    pass

    check_loop.start()

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
