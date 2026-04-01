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
# 이벤트 및 알림 기본값 정의 (요청사항 반영)
# =========================

EVENT_DEFAULT_PRE = {
    "카이라": [2],
    "슈고15": [0],
    "슈고45": [0],
    "아그로": [30],   # 10분 -> 30분 변경
    "아티쟁": [120],  # 30분 -> 120분(2시간) 변경
    "나흐마": [30],   # 10분 -> 30분 변경
    "시공_20시": [5],
    "시공_23시": [5],
    "시공_02시": [5]
}

EVENT_DESCRIPTION = {
    "카이라": "매 시각 정각",
    "슈고15": "매 시각 15분",
    "슈고45": "매 시각 45분",
    "아그로": "처치 후 12시간 간격",
    "아티쟁": "화, 목, 토 오후 9시 5분",
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
# DM 전송 (최적화)
# =========================

async def send_dm_user(uid, text):
    try:
        user_id = int(uid)
        user = bot.get_user(user_id)
        if user is None:
            user = await bot.fetch_user(user_id)
        await user.send(text)
    except Exception as e:
        print(f"DM 실패 → {uid} : {e}")

# =========================
# UI 구성
# =========================

def build_main_embed() -> discord.Embed:
    embed = discord.Embed(title="🔔 알림 설정 센터", color=0x5865F2)
    lines = [f"{EVENT_EMOJI.get(k)} **{k}** — {d}" for k, d in EVENT_DESCRIPTION.items()]
    embed.add_field(name="지원 이벤트", value="\n".join(lines), inline=False)
    if "agro" in data and "next" in data["agro"]:
        nt = datetime.fromisoformat(data["agro"]["next"]).astimezone(KST)
        embed.set_footer(text=f"👹 아그로 다음: {nt.strftime('%m/%d %H:%M')}")
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
        description=f"**상태:** {'🟢 켜짐' if on else '⚫ 꺼짐'}\n**시간:** {pre_str}",
        color=0x5865F2
    )
    return embed

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="목록보기 / 설정하기", emoji="🔔", style=discord.ButtonStyle.primary, custom_id="main_open")
    async def open_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=build_my_embed(interaction.user.id), view=MyListView(str(interaction.user.id)), ephemeral=True)

class MyListView(discord.ui.View):
    def __init__(self, uid: str):
        super().__init__(timeout=180)
        self.uid = uid
        for key in EVENT_DESCRIPTION:
            # 알림이 켜져있으면 초록색 버튼으로 표시
            style = discord.ButtonStyle.success if is_on(uid, key) else discord.ButtonStyle.secondary
            self.add_item(EventSelectButton(uid=uid, key=key, style=style))

class EventSelectButton(discord.ui.Button):
    def __init__(self, uid: str, key: str, style: discord.ButtonStyle):
        super().__init__(label=key, emoji=EVENT_EMOJI.get(key, "•"), style=style)
        self.uid, self.key = uid, key
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=build_pre_embed(self.uid, self.key), view=PreSelectView(self.uid, self.key))

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
        style = discord.ButtonStyle.success if minutes in pres else discord.ButtonStyle.secondary
        super().__init__(label=format_pre_time(minutes), style=style)
        self.uid, self.key, self.minutes = uid, key, minutes
    async def callback(self, interaction: discord.Interaction):
        u_data = get_user_data(self.uid).setdefault(self.key, {})
        current = list(get_pre(self.uid, self.key))
        if self.minutes in current: current.remove(self.minutes)
        else: current.append(self.minutes); current.sort()
        u_data["pre"] = current
        if current: u_data["on"] = True
        save()
        await interaction.response.edit_message(embed=build_pre_embed(self.uid, self.key), view=PreSelectView(self.uid, self.key))

class EventOnOffButton(discord.ui.Button):
    def __init__(self, uid: str, key: str):
        on = is_on(uid, key)
        super().__init__(label=f"알림 {'끄기' if on else '켜기'}", style=discord.ButtonStyle.danger if on else discord.ButtonStyle.primary, row=3)
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
        weekday = now.weekday()
        async def check_and_send(key, msg, target_dt: datetime):
            for uid in list(data["events"].keys()):
                if not is_on(uid, key): continue
                for pre in get_pre(uid, key):
                    send_at = target_dt - timedelta(minutes=pre)
                    if 0 <= (now - send_at).total_seconds() < 30:
                        ckey = f"{key}_{uid}_{pre}_{send_at.strftime('%Y%m%d%H%M')}"
                        if ckey not in sent_cache:
                            sent_cache[ckey] = True
                            notice = f"{msg} ({format_pre_time(pre)})" if pre > 0 else msg
                            await send_dm_user(uid, notice)

        # 이벤트 시간 체크
        if weekday in [1, 3, 5]: # 아티쟁 (화/목/토 21:05)
            await check_and_send("아티쟁", "⚔️ 아티쟁 시작!", now.replace(hour=21, minute=5, second=0))
        if weekday in [5, 6]: # 나흐마 (토/일 22:00)
            await check_and_send("나흐마", "🔥 나흐마 등장!", now.replace(hour=22, minute=0, second=0))
        for h in [20, 23, 2]: # 시공
            target = now.replace(hour=h, minute=0, second=0)
            if h == 2 and now.hour > 2: target += timedelta(days=1)
            await check_and_send(f"시공_{h:02d}시", f"🌌 시공 등장! ({h}시)", target)
        
        # 카이라, 슈고, 아그로 로직 동일... (생략된 부분 기존과 같음)
        next_kaira = (now + timedelta(hours=1)).replace(minute=0, second=0) if now.minute > 0 else now.replace(minute=0, second=0)
        await check_and_send("카이라", "⏰ 카이라 등장!", next_kaira)
        for m in [15, 45]:
            target = now.replace(minute=m, second=0)
            if now.minute > m: target += timedelta(hours=1)
            await check_and_send(f"슈고{m}", f"🛡️ 슈고 등장! ({m}분)", target)
        if agro_next:
            await check_and_send("아그로", "👹 아그로 등장!", agro_next)
            if now >= agro_next:
                agro_next += timedelta(hours=12); data["agro"]["next"] = agro_next.isoformat(); save()

    except Exception as e: print("루프 에러:", e)

# =========================
# 실행 및 초기화
# =========================

@bot.tree.command(name="아그로", description="아그로 시간 등록")
async def cmd_agro(interaction: discord.Interaction, time: str):
    global agro_next
    try:
        time = time.strip().zfill(3)
        mm, hh = int(time[-2:]), int(time[:-2]) if len(time) > 2 else 0
        if mm >= 60: raise ValueError
        agro_next = datetime.now(KST) + timedelta(hours=hh, minutes=mm)
        data["agro"]["next"] = agro_next.isoformat(); save()
        await interaction.response.send_message(f"👹 아그로 등록: **{agro_next.strftime('%H:%M')}**")
    except: await interaction.response.send_message("형식 오류!", ephemeral=True)

@bot.event
async def on_ready():
    global agro_next
    if "agro" in data and "next" in data["agro"]:
        agro_next = datetime.fromisoformat(data["agro"]["next"]).astimezone(KST)
    bot.add_view(MainView())
    if not loop_check.is_running(): loop_check.start()
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        async for msg in channel.history(limit=5):
            if msg.author == bot.user and msg.components:
                await msg.edit(embed=build_main_embed(), view=MainView()); break
        else: await channel.send(embed=build_main_embed(), view=MainView())
    await bot.tree.sync()
    print(f"봇 준비 완료: {bot.user}")

bot.run(BOT_TOKEN)
