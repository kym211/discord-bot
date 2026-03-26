import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import pytz
import asyncio
import json

# ============================
# 설정
# ============================

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"
EMBED_MESSAGE_ID_FILE = "embed_id.txt"

# ============================
# 데이터
# ============================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"prealarms": {}, "agro": {"hour": 0, "minute": 0}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

data = load_data()

# ============================
# 역할
# ============================

ROLE_NAMES = {
    "나흐마": "📢 나흐마",
    "아티쟁": "📢 아티쟁",
    "아그로": "📢 아그로",
    "시공8": "📢 시공 (20:00)",
    "시공23": "📢 시공 (23:00)",
    "시공2": "📢 시공 (02:00)",
}

# ============================
# 아그로 시간
# ============================

def get_agro_times():
    h = data["agro"]["hour"]
    m = data["agro"]["minute"]

    base = datetime.now(KST).replace(hour=h, minute=m, second=0, microsecond=0)

    return [
        (base.hour, base.minute),
        ((base + timedelta(hours=12)).hour, (base + timedelta(hours=12)).minute)
    ]

# ============================
# 역할 생성
# ============================

async def get_or_create_role(guild, name):
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = await guild.create_role(name=name, mentionable=True)
    return role

# ============================
# 버튼
# ============================

class AlarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def toggle(self, interaction, key):
        role = await get_or_create_role(interaction.guild, ROLE_NAMES[key])

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"🔕 {key} 해제", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"🔔 {key} 구독", ephemeral=True)

    @discord.ui.button(label="🌙 나흐마", custom_id="nahma")
    async def b1(self, i, b): await self.toggle(i, "나흐마")

    @discord.ui.button(label="📅 아티쟁", custom_id="arti")
    async def b2(self, i, b): await self.toggle(i, "아티쟁")

    @discord.ui.button(label="⏰ 아그로", custom_id="agro")
    async def b3(self, i, b): await self.toggle(i, "아그로")

    @discord.ui.button(label="🔔 시공20", custom_id="s8")
    async def b4(self, i, b): await self.toggle(i, "시공8")

    @discord.ui.button(label="🔔 시공23", custom_id="s23")
    async def b5(self, i, b): await self.toggle(i, "시공23")

    @discord.ui.button(label="🔔 시공02", custom_id="s2")
    async def b6(self, i, b): await self.toggle(i, "시공2")

# ============================
# 임베드 (중복 방지)
# ============================

async def post_embed():

    channel = bot.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="🔔 알림 구독 시스템",
        description=(
            "버튼 클릭으로 알림을 구독하세요\n\n"
            "🌙 나흐마 (주말 22:00)\n"
            "📅 아티쟁 (화/목/토 21:00)\n"
            "⏰ 아그로 (12시간 반복)\n"
            "🔔 시공 (20:00 / 23:00 / 02:00)\n\n"
            "💡 /사전알림 으로 개인 알림 설정 가능"
        ),
        color=discord.Color.blurple()
    )

    # 기존 메시지 불러오기
    if os.path.exists(EMBED_MESSAGE_ID_FILE):
        with open(EMBED_MESSAGE_ID_FILE, "r") as f:
            msg_id = int(f.read())

        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed, view=AlarmView())
            return
        except:
            pass

    # 없으면 새로 생성
    msg = await channel.send(embed=embed, view=AlarmView())

    with open(EMBED_MESSAGE_ID_FILE, "w") as f:
        f.write(str(msg.id))

# ============================
# 슬래시 명령어
# ============================

@bot.tree.command(name="아그로")
async def set_agro(interaction: discord.Interaction, 시간: str):

    try:
        시간 = 시간.zfill(4)
        h = int(시간[:2])
        m = int(시간[2:])

        data["agro"]["hour"] = h
        data["agro"]["minute"] = m
        save_data()

        await interaction.response.send_message(
            f"✅ 아그로 설정\n{h:02d}:{m:02d} / {(h+12)%24:02d}:{m:02d}"
        )
    except:
        await interaction.response.send_message("❌ 형식 오류")

@bot.tree.command(name="사전알림")
async def prealarm(interaction: discord.Interaction, 알림: str, 분: int):

    uid = str(interaction.user.id)

    data["prealarms"].setdefault(uid, {})
    data["prealarms"][uid].setdefault(알림, [])

    if 분 in data["prealarms"][uid][알림]:
        data["prealarms"][uid][알림].remove(분)
        msg = "삭제"
    else:
        data["prealarms"][uid][알림].append(분)
        msg = "추가"

    save_data()
    await interaction.response.send_message(f"{알림} {분}분 전 {msg}")

@bot.tree.command(name="내알림")
async def my_alarm(interaction: discord.Interaction):

    uid = str(interaction.user.id)
    d = data["prealarms"].get(uid, {})

    if not d:
        await interaction.response.send_message("❌ 설정 없음")
        return

    msg = "📌 내 알림 설정\n\n"
    for k, v in d.items():
        msg += f"{k} → {', '.join(map(str,v))}분 전\n"

    await interaction.response.send_message(msg)

# ============================
# 시작
# ============================

@bot.event
async def on_ready():

    if not hasattr(bot, "ready"):
        await bot.tree.sync()
        bot.add_view(AlarmView())
        await post_embed()
        bot.ready = True

    print("🚀 봇 준비 완료")

bot.run(BOT_TOKEN)
