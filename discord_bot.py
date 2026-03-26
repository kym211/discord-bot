import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json
from datetime import datetime, timedelta
import pytz

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# =========================
# 기본 사전시간
# =========================

EVENT_DEFAULT_PRE = {
    "나흐마": [10],
    "카이라": [2],
    "아티쟁": [30],
    "슈고45": [0],
    "슈고15": [0],
    "아그로": [10]
}

EVENT_DESCRIPTION = {
    "나흐마": "매 주 토, 일요일 오후 10시",
    "카이라": "매 시각",
    "아티쟁": "매 주 화, 목, 토요일 오후 9시",
    "슈고45": "매 시각 45분",
    "슈고15": "매 시각 15분",
    "아그로": "처치 후 12시간 간격"
}

EVENT_EMOJI = {
    "나흐마": "🔥",
    "카이라": "⏰",
    "아티쟁": "⚔️",
    "슈고45": "🛡️",
    "슈고15": "🛡️",
    "아그로": "👹"
}

PRE_OPTIONS = [0, 2, 5, 10, 20, 30, 60]

# =========================
# 데이터
# =========================

def load():
    if not os.path.exists(DATA_FILE):
        return {"events": {}, "agro": {}}
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)

data = load()

def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(uid):
    data["events"].setdefault(uid, {})
    return data["events"][uid]

def is_on(uid, key):
    return get_user(uid).get(key, {}).get("on", False)

def get_pre(uid, key):
    user_pre = get_user(uid).get(key, {}).get("pre", None)
    if user_pre is None:
        return EVENT_DEFAULT_PRE.get(key, [0])
    return user_pre

# =========================
# DM 전송
# =========================

async def send_dm_user(uid, text):
    try:
        user = await bot.fetch_user(int(uid))
        await user.send(text)
        print(f"DM 성공 → {uid}")
    except Exception as e:
        print(f"DM 실패 → {uid} : {e}")

# =========================
# 아그로 변수
# =========================

agro_next = None
sent_cache: dict[str, bool] = {}

def make_cache_key(key, dt: datetime) -> str:
    return f"{key}_{dt.strftime('%Y%m%d%H%M')}"

# =========================
# 임베드 생성
# =========================

def build_main_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔔 알림 설정",
        description="아래 버튼을 눌러 알림을 설정하세요.\n각 이벤트를 클릭하면 사전 알림 시간을 선택할 수 있습니다.",
        color=0x5865F2
    )
    lines = []
    for key, desc in EVENT_DESCRIPTION.items():
        emoji = EVENT_EMOJI.get(key, "•")
        lines.append(f"{emoji} **{key}** — {desc}")
    embed.add_field(name="이벤트 목록", value="\n".join(lines), inline=False)
    if agro_next:
        nt = agro_next if agro_next.tzinfo else KST.localize(agro_next)
        embed.set_footer(text=f"👹 아그로 다음 등장: {nt.strftime('%m/%d %H:%M')}")
    return embed


def build_my_embed(uid: str) -> discord.Embed:
    embed = discord.Embed(title="🔔 내 알림 설정", color=0x5865F2)
    lines = []
    for key, desc in EVENT_DESCRIPTION.items():
        emoji = EVENT_EMOJI.get(key, "•")
        status = "🟢" if is_on(uid, key) else "⚫"
        pres = get_pre(uid, key)
        pre_str = ", ".join(f"{p}분 전" if p > 0 else "즉시" for p in pres)
        lines.append(f"{status} {emoji} **{key}**  |  {pre_str}\n　{desc}")
    embed.description = "\n\n".join(lines)
    if agro_next:
        nt = agro_next if agro_next.tzinfo else KST.localize(agro_next)
        embed.set_footer(text=f"👹 아그로 다음 등장: {nt.strftime('%m/%d %H:%M')}")
    return embed


def build_pre_embed(uid: str, key: str) -> discord.Embed:
    emoji = EVENT_EMOJI.get(key, "•")
    pres = get_pre(uid, key)
    pre_str = ", ".join(f"{p}분 전" if p > 0 else "즉시" for p in pres)
    on = is_on(uid, key)
    extra = "\n\n💡 처치 후 `/아그로 1245` 입력 (12시간 45분 후 등장)" if key == "아그로" else ""
    embed = discord.Embed(
        title=f"{emoji} {key} 알림 설정",
        description=(
            f"**상태:** {'🟢 ON' if on else '⚫ OFF'}\n"
            f"**현재 알림 시간:** {pre_str}\n\n"
            f"원하는 시간을 선택하세요. (복수 선택 가능){extra}"
        ),
        color=0x5865F2
    )
    return embed

# =========================
# 채널 고정 버튼 View (영구)
# =========================

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(OpenListButton())


class OpenListButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="목록",
            emoji="🔔",
            style=discord.ButtonStyle.primary,
            custom_id="main_open"
        )

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        await interaction.response.send_message(
            embed=build_my_embed(uid),
            view=MyListView(uid=uid),
            ephemeral=True
        )

# =========================
# 개인 설정 1단계 View
# =========================

class MyListView(discord.ui.View):
    def __init__(self, uid: str):
        super().__init__(timeout=120)
        self.uid = uid
        for key in EVENT_DESCRIPTION:
            self.add_item(EventSelectButton(uid=uid, key=key))


class EventSelectButton(discord.ui.Button):
    def __init__(self, uid: str, key: str):
        on = is_on(uid, key)
        super().__init__(
            label=key,
            emoji=EVENT_EMOJI.get(key, "•"),
            style=discord.ButtonStyle.success if on else discord.ButtonStyle.secondary,
            custom_id=f"sel_{uid}_{key}"
        )
        self.uid = uid
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if uid != self.uid:
            await interaction.response.send_message("⚠️ 본인의 알림만 설정할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=build_pre_embed(uid, self.key),
            view=PreSelectView(uid=uid, key=self.key)
        )

# =========================
# 개인 설정 2단계 View: 시간 선택
# =========================

class PreSelectView(discord.ui.View):
    def __init__(self, uid: str, key: str):
        super().__init__(timeout=120)
        self.uid = uid
        self.key = key
        for minutes in PRE_OPTIONS:
            self.add_item(PreTimeButton(uid=uid, key=key, minutes=minutes))
        self.add_item(EventOnOffButton(uid=uid, key=key))
        self.add_item(BackButton(uid=uid))


class PreTimeButton(discord.ui.Button):
    def __init__(self, uid: str, key: str, minutes: int):
        pres = get_pre(uid, key)
        active = minutes in pres
        label = f"{minutes}분 전" if minutes > 0 else "즉시"
        super().__init__(
            label=label,
            style=discord.ButtonStyle.success if active else discord.ButtonStyle.secondary,
            custom_id=f"pre_{uid}_{key}_{minutes}"
        )
        self.uid = uid
        self.key = key
        self.minutes = minutes

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if uid != self.uid:
            await interaction.response.send_message("⚠️ 본인의 알림만 설정할 수 있습니다.", ephemeral=True)
            return
        user_data = get_user(uid)
        user_data.setdefault(self.key, {})
        current = list(get_pre(uid, self.key))
        if self.minutes in current:
            current.remove(self.minutes)
        else:
            current.append(self.minutes)
            current.sort()
        user_data[self.key]["pre"] = current
        if current:
            user_data[self.key]["on"] = True
        save()

        active = self.minutes in current
        self.style = discord.ButtonStyle.success if active else discord.ButtonStyle.secondary

        for item in self.view.children:
            if isinstance(item, EventOnOffButton):
                on = is_on(uid, self.key)
                item.label = f"알림 {'ON 🟢' if on else 'OFF ⚫'}"
                item.style = discord.ButtonStyle.success if on else discord.ButtonStyle.danger

        await interaction.response.edit_message(
            embed=build_pre_embed(uid, self.key), view=self.view
        )


class EventOnOffButton(discord.ui.Button):
    def __init__(self, uid: str, key: str):
        on = is_on(uid, key)
        super().__init__(
            label=f"알림 {'ON 🟢' if on else 'OFF ⚫'}",
            style=discord.ButtonStyle.success if on else discord.ButtonStyle.danger,
            custom_id=f"onoff_{uid}_{key}",
            row=2
        )
        self.uid = uid
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if uid != self.uid:
            await interaction.response.send_message("⚠️ 본인의 알림만 설정할 수 있습니다.", ephemeral=True)
            return
        user_data = get_user(uid)
        user_data.setdefault(self.key, {})
        current = user_data[self.key].get("on", False)
        user_data[self.key]["on"] = not current
        save()
        on = user_data[self.key]["on"]
        self.label = f"알림 {'ON 🟢' if on else 'OFF ⚫'}"
        self.style = discord.ButtonStyle.success if on else discord.ButtonStyle.danger
        await interaction.response.edit_message(
            embed=build_pre_embed(uid, self.key), view=self.view
        )


class BackButton(discord.ui.Button):
    def __init__(self, uid: str):
        super().__init__(
            label="← 목록으로",
            style=discord.ButtonStyle.secondary,
            custom_id=f"back_{uid}",
            row=3
        )
        self.uid = uid

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if uid != self.uid:
            await interaction.response.send_message("⚠️ 본인의 알림만 설정할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=build_my_embed(uid),
            view=MyListView(uid=uid)
        )

# =========================
# LOOP
# =========================

@tasks.loop(seconds=30)
async def loop_check():
    global agro_next

    try:
        now = datetime.now(KST)
        weekday = now.weekday()
        minute = now.minute
        second = now.second

        async def check_and_send(key, msg, target_dt: datetime):
            for uid in list(data["events"].keys()):
                if not is_on(uid, key):
                    continue
                for pre in get_pre(uid, key):
                    send_at = target_dt - timedelta(minutes=pre)
                    diff_sec = (now - send_at).total_seconds()
                    if -30 < diff_sec <= 30:
                        cache_key = make_cache_key(f"{key}_{uid}_{pre}", send_at)
                        if cache_key not in sent_cache:
                            sent_cache[cache_key] = True
                            if pre > 0:
                                base = msg.rstrip("!")
                                notice = f"{base} {pre}분 전!"
                            else:
                                notice = msg
                            await send_dm_user(uid, notice)

        # 카이라
        next_kaira = now.replace(minute=0, second=0, microsecond=0)
        if minute > 0:
            next_kaira += timedelta(hours=1)
        await check_and_send("카이라", "⏰ 카이라 등장!", next_kaira)

        # 나흐마
        if weekday in [5, 6]:
            await check_and_send("나흐마", "🔥 나흐마 등장!",
                now.replace(hour=22, minute=0, second=0, microsecond=0))

        # 아티쟁
        if weekday in [1, 3, 5]:
            await check_and_send("아티쟁", "⚔️ 아티쟁 시작!",
                now.replace(hour=21, minute=0, second=0, microsecond=0))

        # 슈고45
        next_45 = now.replace(minute=45, second=0, microsecond=0)
        if minute > 45 or (minute == 45 and second > 30):
            next_45 += timedelta(hours=1)
        await check_and_send("슈고45", "🛡️ 슈고 등장! (45분)", next_45)

        # 슈고15
        next_15 = now.replace(minute=15, second=0, microsecond=0)
        if minute > 15 or (minute == 15 and second > 30):
            next_15 += timedelta(hours=1)
        await check_and_send("슈고15", "🛡️ 슈고 등장! (15분)", next_15)

        # 아그로
        if agro_next:
            if agro_next.tzinfo is None:
                agro_next = KST.localize(agro_next)
            await check_and_send("아그로", "👹 아그로 등장!", agro_next)
            if now >= agro_next:
                agro_next += timedelta(hours=12)
                data["agro"]["next"] = agro_next.isoformat()
                save()

        # 캐시 정리
        expired = [k for k in sent_cache if _cache_age_minutes(k, now) > 60]
        for k in expired:
            del sent_cache[k]

    except Exception as e:
        print("loop 오류:", e)


def _cache_age_minutes(cache_key: str, now: datetime) -> float:
    try:
        dt = KST.localize(datetime.strptime(cache_key[-12:], "%Y%m%d%H%M"))
        return abs((now - dt).total_seconds() / 60)
    except Exception:
        return 0

# =========================
# 슬래시 커맨드: /아그로
# =========================

@bot.tree.command(name="아그로", description="아그로 처치 후 다음 등장까지 남은 시간 입력 (예: 1245 → 12시간 45분 후)")
@app_commands.describe(time="시간분 형식 입력 (예: 1245, 030, 100)")
async def cmd_agro(interaction: discord.Interaction, time: str):
    global agro_next

    time = time.strip().zfill(3)
    try:
        minutes_part = int(time[-2:])
        hours_part = int(time[:-2]) if len(time) > 2 else 0
        if minutes_part >= 60:
            raise ValueError
    except ValueError:
        await interaction.response.send_message(
            "⚠️ 형식이 올바르지 않습니다.\n예) `/아그로 1245` → 12시간 45분 후\n예) `/아그로 030` → 30분 후",
            ephemeral=True
        )
        return

    now = datetime.now(KST)
    agro_next = now + timedelta(hours=hours_part, minutes=minutes_part)
    data["agro"]["next"] = agro_next.isoformat()
    save()

    uid = str(interaction.user.id)
    pres = get_pre(uid, "아그로")
    pre_str = ", ".join(f"{p}분 전" if p > 0 else "즉시" for p in pres)

    await interaction.response.send_message(
        f"👹 아그로 처치 등록!\n"
        f"다음 등장: **{agro_next.strftime('%m/%d %H:%M')}** "
        f"({hours_part}시간 {minutes_part}분 후)\n"
        f"알림 설정: {pre_str}",
        ephemeral=False
    )

# =========================
# SETUP HOOK — on_ready 전에 커맨드 등록 및 sync
# =========================

async def setup_hook():
    await bot.tree.sync()
    print("✅ 슬래시 커맨드 동기화 완료")

bot.setup_hook = setup_hook

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    global agro_next

    # 아그로 시간 복원
    try:
        if "agro" in data and "next" in data["agro"]:
            parsed = datetime.fromisoformat(data["agro"]["next"])
            if parsed.tzinfo is None:
                parsed = KST.localize(parsed)
            agro_next = parsed
    except Exception as e:
        print("아그로 로드 실패:", e)

    # 영구 View 복원
    bot.add_view(MainView())

    # 루프 시작
    if not loop_check.is_running():
        loop_check.start()

    # 채널 메시지 전송 또는 업데이트
    ch = bot.get_channel(CHANNEL_ID)
    if ch:
        existing_msg = None
        async for msg in ch.history(limit=50):
            if msg.author == bot.user and msg.components:
                for row in msg.components:
                    for comp in row.children:
                        if hasattr(comp, "custom_id") and comp.custom_id == "main_open":
                            existing_msg = msg
                            break
                    if existing_msg:
                        break
            if existing_msg:
                break

        if existing_msg:
            await existing_msg.edit(embed=build_main_embed(), view=MainView())
            print("✅ 기존 알림 메시지 업데이트")
        else:
            await ch.send(embed=build_main_embed(), view=MainView())
            print("✅ 새 알림 메시지 전송")

    print(f"🔥 {bot.user} 시작 완료")


bot.run(BOT_TOKEN)
