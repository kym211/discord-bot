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
# 타입:
#   fixed  → 고정 시간 (weekdays 옵션)
#   hourly → 매 시 정각
#   agro   → /아그로 명령어로 시작점 지정, 12시간 간격 (런타임 상태)
# =====================

DEFAULT_EVENTS = {
    "나흐마":      {"type": "fixed",  "time": [(22, 0)],           "weekdays": [5, 6]},
    "아그로":      {"type": "agro"},
    "카이라":      {"type": "hourly"},
    "아티쟁":      {"type": "fixed",  "time": [(21, 0)],           "weekdays": [1, 3, 5]},
    "시공(20시)":  {"type": "fixed",  "time": [(20, 0)]},
    "시공(23시)":  {"type": "fixed",  "time": [(23, 0)]},
    "시공(02시)":  {"type": "fixed",  "time": [(2,  0)]},
}

# 아그로 런타임 상태: {uid: datetime (다음 알림 시각)}
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
        super().__init__(timeout=60)
        for m in [2, 5, 10, 20, 30, 60]:
            self.add_item(PreButton(key, uid, m))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

# =====================
# 토글 버튼
# =====================

class ToggleButton(discord.ui.Button):
    def __init__(self, key, uid):
        on = is_on(uid, key)
        ev = DEFAULT_EVENTS.get(key, {})

        # 아그로는 ON 상태 표시를 다음 알림 시각으로
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

        # 아그로 ON 시도 → 명령어 안내
        if ev.get("type") == "agro" and not currently_on:
            await i.response.send_message(
                "⚠️ 약간의 시간 오차가 있을 수 있습니다.",
                ephemeral=True
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
            # 아그로 OFF → 다음 알림 제거
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
            await i.response.send_message("삭제할 항목 없음", ephemeral=True)
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
        super().__init__(timeout=60)
        self.add_item(DeleteSelect(uid))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

# =====================
# 컨트롤
# =====================

class ControlView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=60)

        # 기본 이벤트
        for k in DEFAULT_EVENTS.keys():
            self.add_item(ToggleButton(k, uid))

        # 커스텀
        for k in get_user(uid).keys():
            if k not in DEFAULT_EVENTS:
                self.add_item(ToggleButton(k, uid))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

# =====================
# 커스텀 생성
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
        super().__init__(timeout=60)
        self.add_item(CustomTimeButton(name, uid))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

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

    @discord.ui.button(label="➕ 커스텀 추가", style=discord.ButtonStyle.secondary)
    async def add_btn(self, i, b):
        await i.response.send_modal(CustomNameModal())

    @discord.ui.button(label="🗑 커스텀 삭제", style=discord.ButtonStyle.danger)
    async def del_btn(self, i, b):
        await i.response.send_message(
            view=DeleteSelectView(str(i.user.id)),
            ephemeral=True
        )

# =====================
# /아그로 명령어
#
# 사용법:
#   /아그로 0600       → 오늘 06:00부터 12시간 간격 (절대 시각)
#   /아그로 0600 후에  → 지금으로부터 6시간 후부터 12시간 간격 (상대 시간)
#   /아그로 0130 후에  → 지금으로부터 1시간 30분 후부터 12시간 간격
# =====================

@bot.command(name="아그로")
async def agro_cmd(ctx, time_str: str = "", mode: str = ""):
    uid = str(ctx.author.id)

    try:
        t = time_str.zfill(4)
        h, m = int(t[:2]), int(t[2:])
        if not (0 <= h < 99 and 0 <= m < 60):
            raise ValueError
    except:
        await ctx.reply(
            "❌ 형식 오류.\n"
            "• 절대 시각: `/아그로 0600` → 06:00부터\n"
            "• 상대 시간: `/아그로 0130 후에` → 1시간 30분 후부터",
            ephemeral=True
        )
        return

    now = datetime.now(KST)

    if mode.strip() == "후에":
        # 상대 모드: h시간 m분 후
        delta = timedelta(hours=h, minutes=m)
        start = (now + delta).replace(second=0, microsecond=0)
        mode_desc = f"지금으로부터 {h}시간 {m}분 후"
    else:
        # 절대 모드: 오늘 HH:MM (과거면 내일)
        if not (0 <= h < 24):
            await ctx.reply("❌ 절대 시각은 00~23시만 가능합니다.", ephemeral=True)
            return
        start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if start <= now:
            start += timedelta(hours=12)
        mode_desc = f"오늘 {h:02d}:{m:02d}"

    agro_next[uid] = start

    u = get_user(uid)
    u.setdefault("아그로", {})
    u["아그로"]["on"] = True
    save()

    await ctx.reply(
        f"✅ 아그로 알림 설정됨\n"
        f"기준: **{mode_desc}**\n"
        f"다음 알림: **{start.strftime('%H:%M')}** (이후 12시간 간격)\n\n"
        "사전 알림도 설정하시겠어요?",
        view=PreView("아그로", uid),
        ephemeral=True
    )

# =====================
# 스케줄
# =====================

@tasks.loop(minutes=1)
async def loop():
    now = datetime.now(KST)
    h, m = now.hour, now.minute
    weekday = now.weekday()  # 0=월 ... 6=일

    for g in bot.guilds:
        for member in g.members:
            if member.bot:
                continue
            uid = str(member.id)

            for key, v in DEFAULT_EVENTS.items():
                ev_type = v.get("type")

                if not is_on(uid, key):
                    continue

                # ── fixed 타입 ──────────────────────────────
                if ev_type == "fixed":
                    wd = v.get("weekdays")
                    if wd and weekday not in wd:
                        continue

                    for eh, em in v["time"]:
                        event_total = eh * 60 + em
                        now_total   = h  * 60 + m
                        diff = event_total - now_total
                        if diff < 0:
                            diff += 1440

                        if diff == 0:
                            try:
                                await member.send(f"🔔 {key}")
                            except:
                                pass

                        if diff in get_pre(uid, key):
                            try:
                                await member.send(f"⏱ {key} {diff}분 전")
                            except:
                                pass

                # ── hourly 타입 (카이라) ────────────────────
                elif ev_type == "hourly":
                    if m == 0:
                        try:
                            await member.send(f"🔔 {key} ({h:02d}:00)")
                        except:
                            pass

                    # 사전 알림: 매 시 정각 기준
                    for pre_m in get_pre(uid, key):
                        if m == (60 - pre_m) % 60:
                            try:
                                await member.send(f"⏱ {key} {pre_m}분 전")
                            except:
                                pass

                # ── agro 타입 ───────────────────────────────
                elif ev_type == "agro":
                    if uid not in agro_next:
                        continue

                    next_t = agro_next[uid]
                    now_floor = now.replace(second=0, microsecond=0)

                    # 사전 알림
                    for pre_m in get_pre(uid, key):
                        pre_target = next_t - timedelta(minutes=pre_m)
                        pre_floor  = pre_target.replace(second=0, microsecond=0)
                        if now_floor == pre_floor:
                            try:
                                await member.send(f"⏱ 아그로 {pre_m}분 전")
                            except:
                                pass

                    # 정각 알림
                    next_floor = next_t.replace(second=0, microsecond=0)
                    if now_floor == next_floor:
                        try:
                            await member.send(f"🔔 아그로")
                        except:
                            pass
                        # 12시간 뒤로 갱신
                        agro_next[uid] = next_t + timedelta(hours=12)

            # ── 커스텀 이벤트 ───────────────────────────────
            for key, val in get_user(uid).items():
                if key in DEFAULT_EVENTS:
                    continue
                if not val.get("on"):
                    continue

                for eh, em in val.get("time", []):
                    event_total = eh * 60 + em
                    now_total   = h  * 60 + m
                    diff = event_total - now_total
                    if diff < 0:
                        diff += 1440

                    if diff == 0:
                        try:
                            await member.send(f"🔔 {key}")
                        except:
                            pass

                    if diff in val.get("pre", []):
                        try:
                            await member.send(f"⏱ {key} {diff}분 전")
                        except:
                            pass

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
