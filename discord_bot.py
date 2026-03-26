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
# 알림 목록 임베드 생성
# =========================

def build_status_embed(uid: str) -> discord.Embed:
    embed = discord.Embed(title="🔔 내 알림 설정", color=0x5865F2)
    lines = []
    for key, desc in EVENT_DESCRIPTION.items():
        emoji = EVENT_EMOJI.get(key, "•")
        status = "🟢 ON" if is_on(uid, key) else "⚫ OFF"
        pres = get_pre(uid, key)
        pre_str = ", ".join(f"{p}분 전" if p > 0 else "즉시" for p in pres)
        lines.append(f"{emoji} **{key}** {status}\n　{desc}\n　알림: {pre_str}")
    embed.description = "\n\n".join(lines)
    if agro_next:
        nt = agro_next
        if nt.tzinfo is None:
            nt = KST.localize(nt)
        embed.set_footer(text=f"👹 아그로 다음 등장: {nt.strftime('%m/%d %H:%M')}")
    return embed

# =========================
# 버튼 View
# =========================

class NotifyListView(discord.ui.View):
    def __init__(self, uid: str):
        super().__init__(timeout=120)
        self.uid = uid
        for key in EVENT_DESCRIPTION:
            self.add_item(EventToggleButton(uid=uid, key=key))
        self.add_item(AgroRegisterButton(uid=uid))
        self.add_item(UnsubscribeAllButton(uid=uid))


class EventToggleButton(discord.ui.Button):
    def __init__(self, uid: str, key: str):
        on = is_on(uid, key)
        super().__init__(
            label=f"{key} {'ON' if on else 'OFF'}",
            emoji=EVENT_EMOJI.get(key, "•"),
            style=discord.ButtonStyle.success if on else discord.ButtonStyle.secondary,
            custom_id=f"toggle_{uid}_{key}"
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
        self.label = f"{self.key} {'ON' if on else 'OFF'}"
        self.style = discord.ButtonStyle.success if on else discord.ButtonStyle.secondary
        await interaction.response.edit_message(embed=build_status_embed(uid), view=self.view)


class AgroRegisterButton(discord.ui.Button):
    def __init__(self, uid: str):
        super().__init__(
            label="아그로 처치 등록",
            emoji="👹",
            style=discord.ButtonStyle.danger,
            custom_id=f"agro_{uid}"
        )
        self.uid = uid

    async def callback(self, interaction: discord.Interaction):
        global agro_next
        uid = str(interaction.user.id)
        if uid != self.uid:
            await interaction.response.send_message("⚠️ 본인의 알림만 설정할 수 있습니다.", ephemeral=True)
            return
        now = datetime.now(KST)
        agro_next = now + timedelta(hours=12)
        data["agro"]["next"] = agro_next.isoformat()
        save()
        await interaction.response.edit_message(embed=build_status_embed(uid), view=self.view)
        await interaction.followup.send(
            f"👹 아그로 처치 등록 완료!\n다음 등장: **{agro_next.strftime('%m/%d %H:%M')}**",
            ephemeral=True
        )


class UnsubscribeAllButton(discord.ui.Button):
    def __init__(self, uid: str):
        super().__init__(
            label="전체 구독취소",
            emoji="🔕",
            style=discord.ButtonStyle.secondary,
            custom_id=f"unsub_{uid}"
        )
        self.uid = uid

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if uid != self.uid:
            await interaction.response.send_message("⚠️ 본인의 알림만 설정할 수 있습니다.", ephemeral=True)
            return
        user_data = get_user(uid)
        for key in EVENT_DESCRIPTION:
            user_data.setdefault(key, {})
            user_data[key]["on"] = False
        save()
        await interaction.response.edit_message(embed=build_status_embed(uid), view=self.view)
        await interaction.followup.send("🔕 모든 알림이 해제되었습니다.", ephemeral=True)

# =========================
# 슬래시 커맨드: /알림
# =========================

@bot.tree.command(name="알림", description="알림 설정 목록을 확인하고 ON/OFF 합니다")
async def cmd_notify(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    embed = build_status_embed(uid)
    view = NotifyListView(uid=uid)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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
                            label = f"{pre}분 전 " if pre > 0 else ""
                            await send_dm_user(uid, f"{label}{msg}")

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
            await check_and_send("아티쟁", "⚔️ 아티쟁 등장!",
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
# READY
# =========================

@bot.event
async def on_ready():
    global agro_next

    try:
        if "agro" in data and "next" in data["agro"]:
            parsed = datetime.fromisoformat(data["agro"]["next"])
            if parsed.tzinfo is None:
                parsed = KST.localize(parsed)
            agro_next = parsed
    except Exception as e:
        print("아그로 로드 실패:", e)

    await bot.tree.sync()

    if not loop_check.is_running():
        loop_check.start()

    ch = bot.get_channel(CHANNEL_ID)
    if ch:
        await ch.send("🔔 알림 설정 완료 — `/알림` 으로 설정하세요!")

    print("🔥 시작 완료")


bot.run(BOT_TOKEN)
