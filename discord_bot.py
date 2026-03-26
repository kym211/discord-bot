import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json, asyncio
from datetime import datetime, timedelta
import pytz

print("프로그램 시작")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

if not BOT_TOKEN or not CHANNEL_ID:
    raise ValueError("환경변수 없음")
    
CHANNEL_ID = int(CHANNEL_ID)

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

DATA_FILE = "data.json"
PAGE_SIZE = 5

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

def get_user(uid):
    data["events"].setdefault(uid, {})
    return data["events"][uid]

def is_on(uid, key):
    return get_user(uid).get(key, {}).get("on", False)

def get_pre(uid, key):
    return get_user(uid).get(key, {}).get("pre", [])

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
# EMBED
# =====================

def build_pre_embed(key, uid):
    selected = get_pre(uid, key)
    embed = discord.Embed(title="⏱ 사전 알림", description=key)

    if selected:
        embed.add_field(
            name="선택됨",
            value=", ".join(f"{m}분 전" for m in sorted(selected)),
            inline=False
        )
    return embed

# =====================
# 버튼 (실시간 갱신 핵심)
# =====================

class ToggleButton(discord.ui.Button):
    def __init__(self, key, uid, page):
        self.key = key
        self.uid = uid
        self.page = page

        on = is_on(uid, key)
        label = f"🟢 {key}" if on else f"🔴 {key}"

        super().__init__(
            label=label,
            style=discord.ButtonStyle.success if on else discord.ButtonStyle.danger
        )

    async def callback(self, i: discord.Interaction):
        u = get_user(self.uid)
        u.setdefault(self.key, {})

        u[self.key]["on"] = not is_on(self.uid, self.key)
        save()

        # ✅ 상태 즉시 반영 (핵심)
        await i.response.edit_message(
            view=ControlView(self.uid, self.page)
        )

# =====================
# 페이지 버튼
# =====================

class PrevButton(discord.ui.Button):
    def __init__(self, uid, page):
        super().__init__(label="⬅", style=discord.ButtonStyle.secondary)
        self.uid = uid
        self.page = page

    async def callback(self, i):
        await i.response.edit_message(
            view=ControlView(self.uid, self.page - 1)
        )

class NextButton(discord.ui.Button):
    def __init__(self, uid, page):
        super().__init__(label="➡", style=discord.ButtonStyle.secondary)
        self.uid = uid
        self.page = page

    async def callback(self, i):
        await i.response.edit_message(
            view=ControlView(self.uid, self.page + 1)
        )

# =====================
# 컨트롤 UI
# =====================

class ControlView(discord.ui.View):
    def __init__(self, uid, page=0):
        super().__init__(timeout=60)
        self.uid = uid
        self.page = page

        keys = list(DEFAULT_EVENTS.keys()) + [
            k for k in get_user(uid).keys() if k not in DEFAULT_EVENTS
        ]

        start = page * PAGE_SIZE
        end = start + PAGE_SIZE

        for k in keys[start:end]:
            self.add_item(ToggleButton(k, uid, page))

        if page > 0:
            self.add_item(PrevButton(uid, page))
        if end < len(keys):
            self.add_item(NextButton(uid, page))

# =====================
# 슬래시 명령어
# =====================

@tree.command(name="목록")
async def list_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        view=ControlView(str(interaction.user.id), 0),
        ephemeral=True
    )

@tree.command(name="아그로")
@app_commands.describe(time_str="0600", mode="후에")
async def agro_cmd(interaction: discord.Interaction, time_str: str, mode: str = ""):
    uid = str(interaction.user.id)

    t = time_str.zfill(4)
    h, m = int(t[:2]), int(t[2:])

    now = datetime.now(KST)

    if mode == "후에":
        start = now + timedelta(hours=h, minutes=m)
    else:
        start = now.replace(hour=h, minute=m)
        if start <= now:
            start += timedelta(hours=12)

    agro_next[uid] = start

    u = get_user(uid)
    u.setdefault("아그로", {})
    u["아그로"]["on"] = True
    save()

    await interaction.response.send_message(
        f"다음: {start.strftime('%H:%M')}",
        ephemeral=True
    )

# =====================
# 스케줄 (최적화됨)
# =====================

@tasks.loop(minutes=1)
async def scheduler_loop():
    now = datetime.now(KST)
    h, m = now.hour, now.minute

    for uid in data["events"].keys():
        member = None
        for g in bot.guilds:
            member = g.get_member(int(uid))
            if member:
                break
        if not member:
            continue

        for key, v in DEFAULT_EVENTS.items():
            if not is_on(uid, key):
                continue

            if v["type"] == "hourly" and m == 0:
                try:
                    await member.send(f"🔔 {key}")
                except Exception as e:
                    print(e)

# =====================
# 저장 루프
# =====================

@tasks.loop(seconds=10)
async def save_loop():
    global dirty
    if not dirty:
        return
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        dirty = False
    except Exception as e:
        print("저장 실패:", e)

# =====================
# 실행
# =====================

@bot.event
async def on_ready():
    await tree.sync()

    for g in bot.guilds:
        await g.chunk()

    scheduler_loop.start()
    save_loop.start()

    print("🔥 READY")

# ✅ 429 방지 실행
async def main():
    while True:
        try:
            await bot.start(BOT_TOKEN)
        except Exception as e:
            print("재시도:", e)
            await asyncio.sleep(60)

asyncio.run(main())
