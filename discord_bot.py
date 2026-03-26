import discord
from discord.ext import commands
import os, json

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

def load():
    if not os.path.exists(DATA_FILE):
        return {"prealarms": {}}
    return json.load(open(DATA_FILE))

def save():
    json.dump(data, open(DATA_FILE, "w"))

data = load()

# ============================
# 공통 함수
# ============================

def get_user_times(uid, key):
    return data["prealarms"].get(uid, {}).get(key, [])

# ============================
# 사전알림 선택 View (핵심)
# ============================

class PreAlarmView(discord.ui.View):
    def __init__(self, alarm_key, user_id):
        super().__init__(timeout=120)
        self.alarm_key = alarm_key
        self.user_id = user_id

        self.update_buttons()

    def update_buttons(self):
        self.clear_items()

        times = [2,5,10,20,30,60]
        user_times = get_user_times(self.user_id, self.alarm_key)

        for t in times:
            label = f"{t}분"
            if t in user_times:
                label = f"✅ {t}분"

            self.add_item(PreAlarmButton(t, label, self.alarm_key, self.user_id))

class PreAlarmButton(discord.ui.Button):
    def __init__(self, minutes, label, key, user_id):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.minutes = minutes
        self.key = key
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):

        uid = str(self.user_id)

        data["prealarms"].setdefault(uid, {})
        data["prealarms"][uid].setdefault(self.key, [])

        if self.minutes in data["prealarms"][uid][self.key]:
            data["prealarms"][uid][self.key].remove(self.minutes)
        else:
            data["prealarms"][uid][self.key].append(self.minutes)

        save()

        # 🔥 UI 다시 생성
        view = PreAlarmView(self.key, uid)
        embed = make_embed(self.key, uid)

        await interaction.response.edit_message(embed=embed, view=view)

# ============================
# 임베드 생성
# ============================

def make_embed(key, user_id):

    times = get_user_times(user_id, key)

    if times:
        txt = ", ".join([f"{t}분 전" for t in sorted(times)])
    else:
        txt = "설정 없음"

    return discord.Embed(
        title=f"⏱ {key} 사전알림 설정",
        description=(
            f"현재 설정: **{txt}**\n\n"
            "버튼을 눌러 추가/제거하세요"
        ),
        color=discord.Color.gold()
    )

# ============================
# 메인 View
# ============================

class AlarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def open_menu(self, interaction, key):

        uid = str(interaction.user.id)

        embed = make_embed(key, uid)
        view = PreAlarmView(key, uid)

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="🌙 나흐마", custom_id="nahma")
    async def b1(self, i, b): await self.open_menu(i, "나흐마")

    @discord.ui.button(label="📅 아티쟁", custom_id="arti")
    async def b2(self, i, b): await self.open_menu(i, "아티쟁")

    @discord.ui.button(label="⏰ 아그로", custom_id="agro")
    async def b3(self, i, b): await self.open_menu(i, "아그로")

    @discord.ui.button(label="🔔 시공20", custom_id="s8")
    async def b4(self, i, b): await self.open_menu(i, "시공8")

    @discord.ui.button(label="🔔 시공23", custom_id="s23")
    async def b5(self, i, b): await self.open_menu(i, "시공23")

    @discord.ui.button(label="🔔 시공02", custom_id="s2")
    async def b6(self, i, b): await self.open_menu(i, "시공2")

# ============================
# 임베드 전송
# ============================

async def post_embed():

    channel = bot.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="🔔 알림 설정",
        description=(
            "버튼 클릭 → 사전알림 설정\n\n"
            "✅ 체크 표시 = 현재 선택됨\n"
            "🔁 다시 누르면 해제됨"
        ),
        color=discord.Color.blurple()
    )

    await channel.send(embed=embed, view=AlarmView())

# ============================
# 시작
# ============================

@bot.event
async def on_ready():
    await bot.tree.sync()
    bot.add_view(AlarmView())
    await post_embed()
    print("🚀 완성형 UI 준비 완료")

bot.run(BOT_TOKEN)
