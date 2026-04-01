import discord
from discord.ext import commands, tasks
import os, json
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
# 이벤트 및 알림 기본값
# =========================
EVENT_DEFAULT_PRE = {
    "카이라": [2], "슈고15": [0], "슈고45": [0],
    "아그로": [30], "아티쟁": [120], "나흐마": [30],
    "시공_20시": [10], "시공_23시": [10], "시공_02시": 10]
}

EVENT_DESCRIPTION = {
    "카이라": "매 시각 정각", "슈고15": "매 시각 15분", "슈고45": "매 시각 45분",
    "아그로": "처치 후 12시간 간격", "아티쟁": "화, 목, 토 오후 9시 5분", "나흐마": "토, 일 오후 10시",
    "시공_20시": "매일 저녁 8시 (20:00)", "시공_23시": "매일 밤 11시 (23:00)", "시공_02시": "매일 새벽 2시 (02:00)"
}

EVENT_EMOJI = {
    "카이라": "⏰", "슈고15": "🛡️", "슈고45": "🛡️", "아그로": "👹", "아티쟁": "⚔️", 
    "나흐마": "🔥", "시공_20시": "🌌", "시공_23시": "🌌", "시공_02시": "🌌"
}

PRE_OPTIONS = [0, 1, 2, 5, 10, 20, 30, 60, 90, 120]

# =========================
# 데이터 관리
# =========================
def load():
    if not os.path.exists(DATA_FILE): return {"events": {}, "agro": {}}
    with open(DATA_FILE, encoding="utf-8") as f: return json.load(f)

data = load()

def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_data(uid):
    data["events"].setdefault(str(uid), {})
    return data["events"][str(uid)]

def is_on(uid, key): return get_user_data(uid).get(key, {}).get("on", False)

def get_pre(uid, key):
    user_pre = get_user_data(uid).get(key, {}).get("pre", None)
    return user_pre if user_pre is not None else EVENT_DEFAULT_PRE.get(key, [0])

def format_pre_time(m):
    if m == 0: return "즉시"
    if m >= 60: return f"{m//60}시간 {f'{m%60}분 ' if m%60 else ''}전"
    return f"{m}분 전"

# =========================
# UI 구성
# =========================

def build_main_embed():
    embed = discord.Embed(title="🔔 알림 설정 센터", description="이벤트 발생 전 DM으로 알림을 보내드립니다.", color=0x5865F2)
    guide = "1️⃣ **[목록보기]** 클릭\n2️⃣ **콘텐츠** 선택\n3️⃣ **[알림 켜기]** 클릭 시 활성화!"
    embed.add_field(name="📖 사용 방법", value=guide, inline=False)
    return embed

def build_my_embed(uid: str):
    embed = discord.Embed(title="🔔 내 알림 설정 현황", color=0x5865F2)
    lines = []
    for key, desc in EVENT_DESCRIPTION.items():
        status = "🟢" if is_on(uid, key) else "⚫"
        pres = ", ".join(format_pre_time(p) for p in get_pre(uid, key))
        lines.append(f"{status} {EVENT_EMOJI.get(key)} **{key}** | {pres}\n　{desc}")
    embed.description = "\n\n".join(lines)
    return embed

def build_pre_embed(uid: str, key: str):
    on = is_on(uid, key)
    pres = ", ".join(format_pre_time(p) for p in get_pre(uid, key))
    return discord.Embed(title=f"{EVENT_EMOJI.get(key)} {key} 설정", 
                         description=f"**상태:** {'🟢 켜짐' if on else '⚫ 꺼짐'}\n**시간:** {pres}", color=0x5865F2)

class MainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="목록보기 / 설정하기", emoji="🔔", style=discord.ButtonStyle.primary, custom_id="main_open")
    async def open_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        await interaction.response.send_message(embed=build_my_embed(uid), view=MyListView(uid), ephemeral=True)

class MyListView(discord.ui.View):
    def __init__(self, uid: str):
        super().__init__(timeout=60)
        self.uid = uid
        for key in EVENT_DESCRIPTION:
            style = discord.ButtonStyle.success if is_on(uid, key) else discord.ButtonStyle.secondary
            self.add_item(EventSelectButton(uid, key, style))

class EventSelectButton(discord.ui.Button):
    def __init__(self, uid, key, style):
        super().__init__(label=key, emoji=EVENT_EMOJI.get(key), style=style)
        self.uid, self.key = uid, key
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=build_pre_embed(self.uid, self.key), view=PreSelectView(self.uid, self.key))

class PreSelectView(discord.ui.View):
    def __init__(self, uid, key):
        super().__init__(timeout=60)
        self.uid, self.key = uid, key
        for m in PRE_OPTIONS: self.add_item(PreTimeButton(uid, key, m))
        self.add_item(EventOnOffButton(uid, key))
        self.add_item(BackButton(uid))

class PreTimeButton(discord.ui.Button):
    def __init__(self, uid, key, m):
        style = discord.ButtonStyle.success if m in get_pre(uid, key) else discord.ButtonStyle.secondary
        super().__init__(label=format_pre_time(m), style=style)
        self.uid, self.key, self.m = uid, key, m
    async def callback(self, interaction: discord.Interaction):
        u_data = get_user_data(self.uid).setdefault(self.key, {})
        current = list(get_pre(self.uid, self.key))
        if self.m in current: current.remove(self.m)
        else: current.append(self.m); current.sort()
        u_data["pre"] = current
        if current: u_data["on"] = True
        save()
        await interaction.response.edit_message(embed=build_pre_embed(self.uid, self.key), view=PreSelectView(self.uid, self.key))

class EventOnOffButton(discord.ui.Button):
    def __init__(self, uid, key):
        on = is_on(uid, key)
        super().__init__(label=f"알림 {'끄기' if on else '켜기'}", style=discord.ButtonStyle.danger if on else discord.ButtonStyle.primary, row=3)
        self.uid, self.key = uid, key
    async def callback(self, interaction: discord.Interaction):
        u_data = get_user_data(self.uid).setdefault(self.key, {})
        u_data["on"] = not u_data.get("on", False)
        save()
        await interaction.response.edit_message(embed=build_pre_embed(self.uid, self.key), view=PreSelectView(self.uid, self.key))

class BackButton(discord.ui.Button):
    def __init__(self, uid): super().__init__(label="← 뒤로가기", style=discord.ButtonStyle.secondary, row=4)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=build_my_embed(interaction.user.id), view=MyListView(str(interaction.user.id)))

# =========================
# 알림 로직 및 기타 커맨드 (생략 - 기존과 동일하게 유지)
# =========================

@bot.event
async def on_ready():
    bot.add_view(MainView())
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(embed=build_main_embed(), view=MainView())
    print(f"Logged in as {bot.user}")

bot.run(BOT_TOKEN)
