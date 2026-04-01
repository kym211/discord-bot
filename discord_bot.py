import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, json
import asyncio
from datetime import datetime, timedelta
import pytz

# =========================
# 설정 (환경 변수)
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TOKEN_HERE")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# =========================
# 이벤트 및 알림 기본값 정의
# =========================

EVENT_DEFAULT_PRE = {
    "카이라": [2],
    "슈고15": [0],
    "슈고45": [0],
    "아그로": [10],
    "아티쟁": [30],
    "나흐마": [10],
    "시공_20시": [5],
    "시공_23시": [5],
    "시공_02시": [5]
}

EVENT_DESCRIPTION = {
    "카이라": "매 시각 정각",
    "슈고15": "매 시각 15분",
    "슈고45": "매 시각 45분",
    "아그로": "처치 후 12시간 간격",
    "아티쟁": "화, 목, 토 오후 9시 5분", # 21:05로 변경됨
    "나흐마": "토, 일 오후 10시",
    "시공_20시": "매일 저녁 8시 (20:00)",
    "시공_23시": "매일 밤 11시 (23:00)",
    "시공_02시": "매일 새벽 2시 (02:00)"
}

EVENT_EMOJI = {
    "카이라": "⏰",
    "슈고15": "🛡️",
    "슈고45": "🛡️",
    "아그로": "👹",
    "아티쟁": "⚔️",
    "나흐마": "🔥",
    "시공_20시": "🌌",
    "시공_23시": "🌌",
    "시공_02시": "🌌"
}

# 1분, 90분(1.5시간), 120분(2시간) 옵션 포함
PRE_OPTIONS = [0, 1, 2, 5, 10, 20, 30, 60, 90, 120]

# =========================
# 데이터 관리 함수
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

def get_user_data(uid):
    data["events"].setdefault(str(uid), {})
    return data["events"][str(uid)]

def is_on(uid, key):
    return get_user_data(uid).get(key, {}).get("on", False)

def get_pre(uid, key):
    user_pre = get_user_data(uid).get(key, {}).get("pre", None)
    if user_pre is None:
        return EVENT_DEFAULT_PRE.get(key, [0])
    return user_pre

def format_pre_time(m):
    if m == 0: return "즉시"
    if m >= 60:
        h = m // 60
        rem = m % 60
        return f"{h}시간 {f'{rem}분 ' if rem else ''}전"
    return f"{m}분 전"

# =========================
# DM 전송 (최적화 버전)
# =========================

async def send_dm_user(uid, text):
    try:
        user_id = int(uid)
        # 1. get_user로 캐시에서 먼저 찾기
        user = bot.get_user(user_id)
        # 2. 없으면 fetch_user로 API 호출
        if user is None:
            user = await bot.fetch_user(user_id)
        
        await user.send(text)
        print(f"DM 성공 → {uid}")
    except Exception as e:
        print(f"DM 실패 → {uid} : {e}")

# =========================
# UI 구성 (Embed & Views)
# =========================

def build_main_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔔 알림 설정 센터",
        description="아래 **[목록]** 버튼을 눌러 본인의 알림을 설정하세요.\n이벤트별로 원하는 사전 알림 시간을 다르게 설정할 수 있습니다.",
        color=0x5865F2
    )
    lines = []
    for key, desc in EVENT_DESCRIPTION.items():
        emoji = EVENT_EMOJI.get(key, "•")
        lines.append(f"{emoji} **{key}** — {desc}")
    embed.add_field(name="지원하는 이벤트", value="\n".join(lines), inline=False)
    
    if "agro" in data and "next" in data["agro"]:
        nt_str = data["agro"]["next"]
        nt = datetime.fromisoformat(nt_str).astimezone(KST)
        embed.set_footer(text=f"👹 아그로 다음 등장 예상: {nt.strftime('%m/%d %H:%M')}")
    return embed

def build_my_embed(uid: str) -> discord.Embed:
    embed = discord.Embed(title="🔔 내 알림 설정 현황", color=0x5865F2)
    lines = []
    for key, desc in EVENT_DESCRIPTION.items():
        emoji = EVENT_EMOJI.get(key, "•")
        status = "🟢" if is_on(uid, key) else "⚫"
        pres = get_pre(uid, key)
        pre_str = ", ".join(format_pre_time(p) for p in pres)
        lines.append(f"{status} {emoji} **{key}** | {pre_str}\n　{desc}")
    embed.description = "\n\n".join(lines)
    return embed

def build_pre_embed(uid: str, key: str) -> discord.Embed:
    emoji = EVENT_EMOJI.get(key, "•")
    pres = get_pre(uid, key)
    pre_str = ", ".join(format_pre_time(p) for p in pres)
    on = is_on(uid, key)
    embed = discord.Embed(
        title=f"{emoji} {key} 세부 설정",
        description=(
            f"**현재 상태:** {'🟢 알림 켜짐' if on else '⚫ 알림 꺼짐'}\n"
            f"**설정된 시간:** {pre_str}\n\n"
            "아래 버튼을 눌러 알림 시간을 추가/제거하세요.\n(여러 개를 동시에 선택할 수 있습니다)"
        ),
        color=0x5865F2
    )
    return embed

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="목록보기 / 설정하기", emoji="🔔", style=discord.ButtonStyle.primary, custom_id="main_open")
    async def open_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        await interaction.response.send_message(
            embed=build_my_embed(uid),
            view=MyListView(uid=uid),
            ephemeral=True
        )

class MyListView(discord.ui.View):
    def __init__(self, uid: str):
        super().__init__(timeout=180)
        self.uid = uid
        for key in EVENT_DESCRIPTION:
            self.add_item(EventSelectButton(uid=uid, key=key))

class EventSelectButton(discord.ui.Button):
    def __init__(self, uid: str, key: str):
        on = is_on(uid, key)
        super().__init__(
            label=key,
            emoji=EVENT_EMOJI.get(key, "•"),
            style=discord.ButtonStyle.success if on else discord.ButtonStyle.secondary
        )
        self.uid, self.key = uid, key

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=build_pre_embed(self.uid, self.key),
            view=PreSelectView(uid=self.uid, key=self.key)
        )

class PreSelectView(discord.ui.View):
    def __init__(self, uid: str, key: str):
        super().__init__(timeout=180)
        self.uid, self.key = uid, key
        for minutes in PRE_OPTIONS:
            self.add_item(PreTimeButton(uid=uid, key=key, minutes=minutes))
        self.add_item(EventOnOffButton(uid=uid, key=key))
        self.add_item(BackButton(uid=uid))

class PreTimeButton(discord.ui.Button):
    def __init__(self, uid: str, key: str, minutes: int):
        pres = get_pre(uid, key)
        super().__init__(
            label=format_pre_time(minutes),
            style=discord.ButtonStyle.success if minutes in pres else discord.ButtonStyle.secondary
        )
        self.uid, self.key, self.minutes = uid, key, minutes

    async def callback(self, interaction: discord.Interaction):
        u_data = get_user_data(self.uid).setdefault(self.key, {})
        current = list(get_pre(self.uid, self.key))
        if self.minutes in current:
            current.remove(self.minutes)
        else:
            current.append(self.minutes)
            current.sort()
        u_data["pre"] = current
        if current: u_data["on"] = True
        save()
        await interaction.response.edit_message(embed=build_pre_embed(self.uid, self.key), view=PreSelectView(self.uid, self.key))

class EventOnOffButton(discord.ui.Button):
    def __init__(self, uid: str, key: str):
        on = is_on(uid, key)
        super().__init__(
            label=f"알림 {'끄기' if on else '켜기'}",
            style=discord.ButtonStyle.danger if on else discord.ButtonStyle.primary,
            row=3
        )
        self.uid, self.key = uid, key

    async def callback(self, interaction: discord.Interaction):
        u_data = get_user_data(self.uid).setdefault(self.key, {})
        u_data["on"] = not u_data.get("on", False)
        save()
        await interaction.response.edit_message(embed=build_pre_embed(self.uid, self.key), view=PreSelectView(self.uid, self.key))

class BackButton(discord.ui.Button):
    def __init__(self, uid: str):
        super().__init__(label="← 뒤로가기", style=discord.ButtonStyle.secondary, row=4)
        self.uid = uid
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=build_my_embed(self.uid), view=MyListView(self.uid))

# =========================
# 알림 체크 로직 (Loop)
# =========================

sent_cache = {}
agro_next = None

@tasks.loop(seconds=30)
async def loop_check():
    global agro_next
    try:
        now = datetime.now(KST)
        weekday = now.weekday() # 월0 화1 수2 목3 금4 토5 일6

        async def check_and_send(key, msg, target_dt: datetime):
            for uid in list(data["events"].keys()):
                if not is_on(uid, key): continue
                for pre in get_pre(uid, key):
                    send_at = target_dt - timedelta(minutes=pre)
                    # 30초 오차 범위 내에서 발송
                    if 0 <= (now - send_at).total_seconds() < 30:
                        ckey = f"{key}_{uid}_{pre}_{send_at.strftime('%Y%m%d%H%M')}"
                        if ckey not in sent_cache:
                            sent_cache[ckey] = True
                            notice = f"{msg} ({format_pre_time(pre)})" if pre > 0 else msg
                            await send_dm_user(uid, notice)

        # 1. 정기 이벤트
        # 카이라 (매시 정각)
        next_kaira = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0) if now.minute > 0 else now.replace(minute=0, second=0, microsecond=0)
        await check_and_send("카이라", "⏰ 카이라 등장!", next_kaira)

        # 아티쟁 (화/목/토 21:05)
        if weekday in [1, 3, 5]:
            await check_and_send("아티쟁", "⚔️ 아티쟁 시작!", now.replace(hour=21, minute=5, second=0, microsecond=0))

        # 나흐마 (토/일 22:00)
        if weekday in [5, 6]:
            await check_and_send("나흐마", "🔥 나흐마 등장!", now.replace(hour=22, minute=0, second=0, microsecond=0))

        # 시공 (매일 20시, 23시, 02시)
        for h in [20, 23, 2]:
            target = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if h == 2 and now.hour > 2: target += timedelta(days=1)
            await check_and_send(f"시공_{h:02d}시", f"🌌 시공 등장! ({h}시)", target)

        # 슈고 (15분, 45분)
        for m in [15, 45]:
            target = now.replace(minute=m, second=0, microsecond=0)
            if now.minute > m: target += timedelta(hours=1)
            await check_and_send(f"슈고{m}", f"🛡️ 슈고 등장! ({m}분)", target)

        # 2. 아그로 (유동적)
        if agro_next:
            await check_and_send("아그로", "👹 아그로 등장!", agro_next)
            if now >= agro_next:
                agro_next += timedelta(hours=12)
                data["agro"]["next"] = agro_next.isoformat()
                save()

        # 캐시 정리 (1시간 지난 것)
        curr_time = now.timestamp()
        expired = [k for k in sent_cache if (now - datetime.strptime(k.split('_')[-1], '%Y%m%d%H%M').replace(tzinfo=KST)).total_seconds() > 3600]
        for k in expired: del sent_cache[k]

    except Exception as e:
        print("루프 에러:", e)

# =========================
# 커맨드 및 초기화
# =========================

@bot.tree.command(name="아그로", description="아그로 처치 시간을 등록합니다 (예: 1245 -> 12시간 45분 후)")
async def cmd_agro(interaction: discord.Interaction, time: str):
    global agro_next
    time = time.strip().zfill(3)
    try:
        mm = int(time[-2:])
        hh = int(time[:-2]) if len(time) > 2 else 0
        if mm >= 60: raise ValueError
    except:
        return await interaction.response.send_message("형식 오류! 예: `/아그로 1245` (12시간 45분 후)", ephemeral=True)

    now = datetime.now(KST)
    agro_next = now + timedelta(hours=hh, minutes=mm)
    data["agro"]["next"] = agro_next.isoformat()
    save()

    await interaction.response.send_message(f"👹 아그로 등록 완료! 다음 등장: **{agro_next.strftime('%H:%M')}**", ephemeral=False)

@bot.event
async def on_ready():
    global agro_next
    # 아그로 시간 복원
    if "agro" in data and "next" in data["agro"]:
        agro_next = datetime.fromisoformat(data["agro"]["next"]).astimezone(KST)

    bot.add_view(MainView())
    if not loop_check.is_running():
        loop_check.start()
    
    # 채널 메시지 갱신/전송
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        async for msg in channel.history(limit=10):
            if msg.author == bot.user and msg.components:
                await msg.edit(embed=build_main_embed(), view=MainView())
                print("기존 메시지 갱신 완료")
                break
        else:
            await channel.send(embed=build_main_embed(), view=MainView())
            print("새 메시지 전송 완료")
            
    await bot.tree.sync()
    print(f"로그인 완료: {bot.user}")

bot.run(BOT_TOKEN)
