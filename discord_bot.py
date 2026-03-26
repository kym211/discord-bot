import os
import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz
import asyncio

# ============================
# 설정
# ============================

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

# 알림 역할 이름 (디스코드 서버에 자동 생성됨)
ROLE_NAMES = {
    "알림1": "📢 토일 밤10시 알림",
    "알림2": "📢 화목토 밤9시 알림",
    "알림3": "📢 12시간 알림",
    "알림4": "📢 8시/11시/새벽2시 알림",
}

KST = pytz.timezone("Asia/Seoul")
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ============================
# 역할 가져오거나 생성
# ============================

async def get_or_create_role(guild, role_name):
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        role = await guild.create_role(name=role_name, mentionable=True)
    return role


# ============================
# 임베드 + 버튼 뷰
# ============================

class AlarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 영구 유지

    async def toggle_role(self, interaction: discord.Interaction, role_key: str):
        guild = interaction.guild
        role_name = ROLE_NAMES[role_key]
        role = await get_or_create_role(guild, role_name)
        member = interaction.user

        if role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message(
                f"🔕 **{role_name}** 알림을 해제했습니다.", ephemeral=True
            )
        else:
            await member.add_roles(role)
            await interaction.response.send_message(
                f"🔔 **{role_name}** 알림을 구독했습니다!", ephemeral=True
            )

    @discord.ui.button(label="토/일 밤 10시", style=discord.ButtonStyle.primary, custom_id="alarm1", emoji="🌙")
    async def alarm1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_role(interaction, "알림1")

    @discord.ui.button(label="화/목/토 밤 9시", style=discord.ButtonStyle.primary, custom_id="alarm2", emoji="📅")
    async def alarm2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_role(interaction, "알림2")

    @discord.ui.button(label="매일 12시간마다", style=discord.ButtonStyle.success, custom_id="alarm3", emoji="⏰")
    async def alarm3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_role(interaction, "알림3")

    @discord.ui.button(label="오후8시/밤11시/새벽2시", style=discord.ButtonStyle.danger, custom_id="alarm4", emoji="🔔")
    async def alarm4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_role(interaction, "알림4")


async def post_alarm_embed():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"[오류] 채널을 찾을 수 없습니다: {CHANNEL_ID}")
        return

    embed = discord.Embed(
        title="🔔 알림 구독 설정",
        description=(
            "원하는 알림 버튼을 클릭하면 구독/해제됩니다.\n"
            "다시 클릭하면 해제할 수 있어요!\n\n"
            "🌙 **토/일 밤 10시** - 주말 야간 알림\n"
            "📅 **화/목/토 밤 9시** - 주 3회 알림\n"
            "⏰ **매일 12시간마다** - 오전12시 / 오후12시\n"
            "🔔 **오후8시 / 밤11시 / 새벽2시** - 하루 3회 알림"
        ),
        color=discord.Color.blurple()
    )
    embed.set_footer(text="버튼을 눌러 알림을 켜고 끌 수 있습니다 • 본인에게만 보이는 메시지로 안내됩니다")

    await channel.send(embed=embed, view=AlarmView())
    print("[봇] 알림 구독 임베드 전송 완료!")


# ============================
# 알림 전송 함수
# ============================

async def send_notification(guild, role_key: str, message: str):
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return
    role = discord.utils.get(guild.roles, name=ROLE_NAMES[role_key])
    if role and len(role.members) > 0:
        await channel.send(f"{role.mention} {message}")
    else:
        print(f"[봇] {role_key} 구독자 없음 - 알림 스킵")


# ============================
# 스케줄러
# ============================

@tasks.loop(minutes=1)
async def scheduler():
    now = datetime.now(KST)
    weekday = now.weekday()  # 0=월 1=화 2=수 3=목 4=금 5=토 6=일
    hour = now.hour
    minute = now.minute

    if minute != 0:
        return

    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        return

    # 알림1: 토(5), 일(6) 오후 10시
    if weekday in [5, 6] and hour == 22:
        await send_notification(guild, "알림1", "🌙 **토/일 밤 10시 알림**입니다!")

    # 알림2: 화(1), 목(3), 토(5) 오후 9시
    if weekday in [1, 3, 5] and hour == 21:
        await send_notification(guild, "알림2", "📅 **화/목/토 밤 9시 알림**입니다!")

    # 알림3: 매일 12시간 간격
    if hour in [0, 12]:
        await send_notification(guild, "알림3", "⏰ **12시간 정기 알림**입니다!")

    # 알림4: 오후 8시, 오후 11시, 오전 2시
    if hour in [20, 23, 2]:
        await send_notification(guild, "알림4", "🔔 **정기 알림**입니다! (오후8시/밤11시/새벽2시)")


@scheduler.before_loop
async def before_scheduler():
    await bot.wait_until_ready()
    now = datetime.now(KST)
    seconds_until_next_minute = 60 - now.second
    await asyncio.sleep(seconds_until_next_minute)


# ============================
# 봇 시작
# ============================

@bot.event
async def on_ready():
    print(f"[봇] {bot.user} 로그인 완료!")
    bot.add_view(AlarmView())  # 버튼 영구 등록 (재시작 후에도 작동)
    await post_alarm_embed()   # 임베드 자동 전송
    scheduler.start()


bot.run(BOT_TOKEN)
