import discord
from discord.ext import commands
from discord import app_commands
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
# 사전알림 선택 View
# ============================

class PreAlarmView(discord.ui.View):
    def __init__(self, alarm_key):
        super().__init__(timeout=60)
        self.alarm_key = alarm_key

    async def select_time(self, interaction, minutes):

        uid = str(interaction.user.id)

        data["prealarms"].setdefault(uid, {})
        data["prealarms"][uid].setdefault(self.alarm_key, [])

        if minutes in data["prealarms"][uid][self.alarm_key]:
            data["prealarms"][uid][self.alarm_key].remove(minutes)
            msg = "❌ 제거"
        else:
            data["prealarms"][uid][self.alarm_key].append(minutes)
            msg = "✅ 추가"

        save()

        await interaction.response.send_message(
            f"{self.alarm_key} → {minutes}분 전 {msg}",
            ephemeral=True
        )

    # 버튼들
    @discord.ui.button(label="2분 전")
    async def b1(self, i, b): await self.select_time(i, 2)

    @discord.ui.button(label="5분 전")
    async def b2(self, i, b): await self.select_time(i, 5)

    @discord.ui.button(label="10분 전")
    async def b3(self, i, b): await self.select_time(i, 10)

    @discord.ui.button(label="20분 전")
    async def b4(self, i, b): await self.select_time(i, 20)

    @discord.ui.button(label="30분 전")
    async def b5(self, i, b): await self.select_time(i, 30)

    @discord.ui.button(label="60분 전")
    async def b6(self, i, b): await self.select_time(i, 60)

# ============================
# 메인 알림 View
# ============================

class AlarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def open_menu(self, interaction, key):

        embed = discord.Embed(
            title=f"⏱ {key} 사전알림 설정",
            description="원하는 시간을 선택하세요 (중복 가능)",
            color=discord.Color.gold()
        )

        await interaction.response.send_message(
            embed=embed,
            view=PreAlarmView(key),
            ephemeral=True  # 🔥 개인창으로 띄움
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
            "✔ 여러 시간 선택 가능\n"
            "✔ 다시 누르면 제거됨"
        ),
        color=discord.Color.blurple()
    )

    await channel.send(embed=embed, view=AlarmView())

# ============================
# 내 설정 확인
# ============================

@bot.tree.command(name="내알림")
async def my_alarm(interaction: discord.Interaction):

    uid = str(interaction.user.id)
    d = data["prealarms"].get(uid, {})

    if not d:
        await interaction.response.send_message("❌ 없음")
        return

    msg = "📌 내 설정\n\n"
    for k, v in d.items():
        msg += f"{k} → {', '.join(map(str,v))}분 전\n"

    await interaction.response.send_message(msg)

# ============================
# 시작
# ============================

@bot.event
async def on_ready():

    await bot.tree.sync()
    bot.add_view(AlarmView())
    await post_embed()

    print("🚀 UI 준비 완료")

bot.run(BOT_TOKEN)
