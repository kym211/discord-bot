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
    "나흐마": {"type": "fixed", "time": [(22, 0)], "weekdays": [5, 6]},
    "아그로": {"type": "agro"},
    "카이라": {"type": "hourly"},
    "아티쟁": {"type": "fixed", "time": [(21, 0)], "weekdays": [1, 3, 5]},
    "시공(20시)": {"type": "fixed", "time": [(20, 0)]},
    "시공(23시)": {"type": "fixed", "time": [(23, 0)]},
    "시공(02시)": {"type": "fixed", "time": [(2, 0)]},
}

agro_next: dict[str, datetime] = {}

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
# 사전 알림 버튼
# =====================

class PreButton(discord.ui.Button):
    def __init__(self, key, uid, m):
        super().__init__(
            label=f"{m}분",
            style=discord.ButtonStyle.success if m in get_pre(uid, key) else discord.ButtonStyle.secondary,
            row=0 if m in [2, 5, 10] else 1
        )
        self.key = key
        self.uid = uid
        self.m = m

    async def callback(self, i):
        if not is_on(self.uid, self.key):
            await i.response.send_message(
                "❌ ON 먼저",
                ephemeral=True,
                delete_after=30
            )
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
        super().__init__(timeout=30)
        for m in [2, 5, 10, 20, 30, 60]:
            self.add_item(PreButton(key, uid, m))

    async def on_timeout(self):
        try:
            await self.message.delete()
        except:
            pass

# =====================
# 토글 버튼
# =====================

class ToggleButton(discord.ui.Button):
    def __init__(self, key, uid):
        on = is_on(uid, key)
        ev = DEFAULT_EVENTS.get(key, {})

        if ev.get("type") == "agro" and on and uid in agro_next:
            next_t = agro_next[uid].strftime("%H:%M")
            label = f"🟢 아그로 (다음: {next_t})"
        else:
            label = f"🟢 {key}" if on else f"🔴 {key}"

        super().__init__(
            label=label,
            style=discord.ButtonStyle.success if on else discord.ButtonStyle.danger
        )
        self.key = key
        self.uid = uid

    async def callback(self, i):
        u = get_user(self.uid)
        u.setdefault(self.key, {})
        ev = DEFAULT_EVENTS.get(self.key, {})

        currently_on = is_on(self.uid, self.key)

        # 아그로 버튼 안내 변경됨
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
                embed=build_pre_embed(self.key, self.uid),
                view=PreView(self.key, self.uid),
                ephemeral=True
            )
        else:
            if ev.get("type") == "agro":
                agro_next.pop(self.uid, None)

            await i.response.edit_message(view=ControlView(self.uid))

# =====================
# 삭제 선택 UI
# =====================

class DeleteSelect(discord.ui.Select):
    def __init__(self, uid):
        self.uid = uid

        options = [
            discord.SelectOption(label=k)
            for k in get_user(uid).keys()
            if k not in DEFAULT_EVENTS
        ]

        if not options:
            options = [discord.SelectOption(label="삭제할 항목 없음", value="none")]

        super().__init__(
            placeholder="삭제할 커스텀 선택",
            options=options
        )

    async def callback(self, i):
        val = self.values[0]

        if val == "none":
            await i.response.send_message(
                "삭제할 항목 없음",
                ephemeral=True,
                delete_after=30
            )
            return

        u = get_user(self.uid)

        if val in u:
            del u[val]
            save()

        await i.response.edit_message(
            content=f"✅ {val} 삭제됨",
            view=None
        )

class DeleteSelectView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=30)
        self.add_item(DeleteSelect(uid))

    async def on_timeout(self):
        try:
            await self.message.delete()
        except:
            pass

# =====================
# 컨트롤
# =====================

class ControlView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=30)

        for k in DEFAULT_EVENTS.keys():
            self.add_item(ToggleButton(k, uid))

        for k in get_user(uid).keys():
            if k not in DEFAULT_EVENTS:
                self.add_item(ToggleButton(k, uid))

    async def on_timeout(self):
        try:
            await self.message.delete()
        except:
            pass

# =====================
# 메인 UI
# =====================

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="📋 목록", style=discord.ButtonStyle.primary)
    async def list_btn(self, i, b):
        await i.response.send_message(
            view=ControlView(str(i.user.id)),
            ephemeral=True
        )

    @discord.ui.button(label="➕ 커스텀 추가", style=discord.ButtonStyle.secondary)
    async def add_btn(self, i, b):
        await i.response.send_message(
            "기능 준비됨",
            ephemeral=True,
            delete_after=30
        )

    @discord.ui.button(label="🗑 커스텀 삭제", style=discord.ButtonStyle.danger)
    async def del_btn(self, i, b):
        await i.response.send_message(
            view=DeleteSelectView(str(i.user.id)),
            ephemeral=True
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

    ch = bot.get_channel(CHANNEL_ID)

    if ch:
        await ch.send("🔔 알림 설정", view=MainView())

    print("🔥 시작 완료")

bot.run(BOT_TOKEN)    with open(DATA_FILE, encoding="utf-8") as f:
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
