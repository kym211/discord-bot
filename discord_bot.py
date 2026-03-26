import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import pytz
import asyncio

# ============================
# 설정
# ============================

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

# 알림 역할
ROLE_NAMES = {
    "나흐마":   "📢 나흐마",
    "아티쟁":   "📢 아티쟁",
    "아그로":   "📢 아그로",
    "시공8":    "📢 시공 (오후 8시)",
    "시공23":   "📢 시공 (오후 11시)",
    "시공2":    "📢 시공 (오전 2시)",
}

# 사전 알림 역할 (몇 분 전)
PREALARM_ROLE_NAMES = {
    5:   "⏱ 사전알림 5분전",
    10:  "⏱ 사전알림 10분전",
    20:  "⏱ 사전알림 20분전",
    30:  "⏱ 사전알림 30분전",
    60:  "⏱ 사전알림 1시간전",
}

KST = pytz.timezone("Asia/Seoul")
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 아그로 설정
agro_start = 0
agro_interval = 12


def get_agro_hours():
    hours = []
    h = agro_start % 24
    while True:
        hours.append(h % 24)
        h += agro_interval
        if h >= agro_start + 24:
            break
    return hours


# ============================
# 역할 가져오거나 생성
# ============================

async def get_or_create_role(guild, role_name):
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        role = await guild.create_role(name=role_name, mentionable=True)
    return role


# ============================
# 임베드 뷰 1: 알림 종류 선택
# ============================

class AlarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def toggle_role(self, interaction: discord.Interaction, role_key: str):
        guild = interaction.guild
        role_name = ROLE_NAMES[role_key]
        role = await get_or_create_role(guild, role_name)
        member = interaction.user
        if role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message(f"🔕 **{role_name}** 알림 해제!", ephemeral=True)
        else:
            await member.add_roles(role)
            await interaction.response.send_message(f"🔔 **{role_name}** 알림 구독!", ephemeral=True)

    @discord.ui.button(label="나흐마", style=discord.ButtonStyle.primary, custom_id="alarm_nahma", emoji="🌙", row=0)
    async def nahma(self, interaction, button):
        await self.toggle_role(interaction, "나흐마")

    @discord.ui.button(label="아티쟁", style=discord.ButtonStyle.primary, custom_id="alarm_artisan", emoji="📅", row=0)
    async def artisan(self, interaction, button):
        await self.toggle_role(interaction, "아티쟁")

    @discord.ui.button(label="아그로", style=discord.ButtonStyle.success, custom_id="alarm_agro", emoji="⏰", row=0)
    async def agro(self, interaction, button):
        await self.toggle_role(interaction, "아그로")

    @discord.ui.button(label="시공 (오후 8시)", style=discord.ButtonStyle.danger, custom_id="alarm_sigong8", emoji="🔔", row=1)
    async def sigong8(self, interaction, button):
        await self.toggle_role(interaction, "시공8")

    @discord.ui.button(label="시공 (오후 11시)", style=discord.ButtonStyle.danger, custom_id="alarm_sigong23", emoji="🔔", row=1)
    async def sigong23(self, interaction, button):
        await self.toggle_role(interaction, "시공23")

    @discord.ui.button(label="시공 (오전 2시)", style=discord.ButtonStyle.danger, custom_id="alarm_sigong2", emoji="🔔", row=1)
    async def sigong2(self, interaction, button):
        await self.toggle_role(interaction, "시공2")


# ============================
# 임베드 뷰 2: 사전 알림 시간 선택
# ============================

class PreAlarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def toggle_prealarm(self, interaction: discord.Interaction, minutes: int):
        guild = interaction.guild
        role_name = PREALARM_ROLE_NAMES[minutes]
        role = await get_or_create_role(guild, role_name)
        member = interaction.user
        if role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message(f"🔕 **{role_name}** 해제!", ephemeral=True)
        else:
            await member.add_roles(role)
            await interaction.response.send_message(f"🔔 **{role_name}** 구독!", ephemeral=True)

    @discord.ui.button(label="5분 전", style=discord.ButtonStyle.secondary, custom_id="pre_5", emoji="⏱", row=0)
    async def pre5(self, interaction, button):
        await self.toggle_prealarm(interaction, 5)

    @discord.ui.button(label="10분 전", style=discord.ButtonStyle.secondary, custom_id="pre_10", emoji="⏱", row=0)
    async def pre10(self, interaction, button):
        await self.toggle_prealarm(interaction, 10)

    @discord.ui.button(label="20분 전", style=discord.ButtonStyle.secondary, custom_id="pre_20", emoji="⏱", row=0)
    async def pre20(self, interaction, button):
        await self.toggle_prealarm(interaction, 20)

    @discord.ui.button(label="30분 전", style=discord.ButtonStyle.secondary, custom_id="pre_30", emoji="⏱", row=0)
    async def pre30(self, interaction, button):
        await self.toggle_prealarm(interaction, 30)

    @discord.ui.button(label="1시간 전", style=discord.ButtonStyle.secondary, custom_id="pre_60", emoji="⏱", row=0)
    async def pre60(self, interaction, button):
        await self.toggle_prealarm(interaction, 60)


# ============================
# 임베드 전송
# ============================

async def post_alarm_embed():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"[오류] 채널을 찾을 수 없습니다: {CHANNEL_ID}")
        return

    hours = get_agro_hours()
    hours_str = ", ".join([f"{h}시" for h in hours])

    # 알림 종류 임베드
    embed1 = discord.Embed(
        title="🔔 알림 구독 설정",
        description=(
            "받고 싶은 알림을 선택하세요!\n"
            "다시 클릭하면 해제됩니다.\n\n"
            "🌙 **나흐마** - 토/일 밤 10시\n"
            "📅 **아티쟁** - 화/목/토 밤 9시\n"
            f"⏰ **아그로** - {hours_str} ({agro_interval}시간 간격)\n"
            "🔔 **시공** - 오후 8시 / 오후 11시 / 오전 2시"
        ),
        color=discord.Color.blurple()
    )
    embed1.set_footer(text="응답은 본인에게만 보입니다")

    # 사전 알림 임베드
    embed2 = discord.Embed(
        title="⏱ 사전 알림 시간 설정",
        description=(
            "알림을 몇 분 전에 받을지 선택하세요!\n"
            "중복 선택 가능 (예: 30분 전 + 5분 전)\n\n"
            "선택한 시간 전에 **구독한 모든 알림**을 미리 알려드려요."
        ),
        color=discord.Color.gold()
    )
    embed2.set_footer(text="응답은 본인에게만 보입니다")

    await channel.send(embed=embed1, view=AlarmView())
    await channel.send(embed=embed2, view=PreAlarmView())
    print("[봇] 임베드 전송 완료!")


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


async def send_prealarm(guild, label: str, target_hour: int, target_min: int, minutes_before: int):
    """사전 알림 전송 - 구독한 역할이 있는 사람에게만"""
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    prealarm_role = discord.utils.get(guild.roles, name=PREALARM_ROLE_NAMES[minutes_before])
    if not prealarm_role or len(prealarm_role.members) == 0:
        return

    # 알림 역할 구독자 중 사전알림도 구독한 사람만 멘션
    # 각 알림 역할별로 사전알림 구독자와 교집합 멘션
    mentions = set()
    for role_name in ROLE_NAMES.values():
        alarm_role = discord.utils.get(guild.roles, name=role_name)
        if alarm_role:
            for member in alarm_role.members:
                if prealarm_role in member.roles:
                    mentions.add(member.mention)

    if mentions:
        mention_str = " ".join(mentions)
        time_str = f"{target_hour}시" if target_min == 0 else f"{target_hour}시 {target_min}분"
        before_str = f"{minutes_before}분 전" if minutes_before < 60 else "1시간 전"
        await channel.send(f"⏱ {mention_str}\n**{label}** 알림 **{before_str}** 입니다! (`{time_str}` 예정)")


# ============================
# 스케줄러
# ============================

# 정각 알림 스케줄 (hour, minute, role_key, message, label)
def get_schedules():
    schedules = []
    agro_hours = get_agro_hours()

    # 나흐마: 토(5),일(6) 22시
    for wd in [5, 6]:
        schedules.append({"hour": 22, "minute": 0, "weekdays": [5, 6], "role": "나흐마",
                          "msg": "🌙 **나흐마** 알림! (토/일 밤 10시)", "label": "나흐마"})
        break

    # 아티쟁: 화(1),목(3),토(5) 21시
    schedules.append({"hour": 21, "minute": 0, "weekdays": [1, 3, 5], "role": "아티쟁",
                      "msg": "📅 **아티쟁** 알림! (화/목/토 밤 9시)", "label": "아티쟁"})

    # 아그로
    for h in agro_hours:
        schedules.append({"hour": h, "minute": 0, "weekdays": None, "role": "아그로",
                          "msg": "⏰ **아그로** 알림!", "label": "아그로"})

    # 시공
    schedules.append({"hour": 20, "minute": 0, "weekdays": None, "role": "시공8",
                      "msg": "🔔 **시공** 알림! (오후 8시)", "label": "시공 오후8시"})
    schedules.append({"hour": 23, "minute": 0, "weekdays": None, "role": "시공23",
                      "msg": "🔔 **시공** 알림! (오후 11시)", "label": "시공 오후11시"})
    schedules.append({"hour": 2,  "minute": 0, "weekdays": None, "role": "시공2",
                      "msg": "🔔 **시공** 알림! (오전 2시)", "label": "시공 오전2시"})

    return schedules


@tasks.loop(minutes=1)
async def scheduler():
    now = datetime.now(KST)
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute

    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        return

    schedules = get_schedules()

    for s in schedules:
        # 요일 필터
        if s["weekdays"] and weekday not in s["weekdays"]:
            continue

        target_dt = now.replace(hour=s["hour"], minute=s["minute"], second=0, microsecond=0)

        # 정각 알림
        if hour == s["hour"] and minute == s["minute"]:
            await send_notification(guild, s["role"], s["msg"])

        # 사전 알림 체크 (5, 10, 20, 30, 60분 전)
        for mins in [5, 10, 20, 30, 60]:
            pre_dt = target_dt - timedelta(minutes=mins)
            if hour == pre_dt.hour and minute == pre_dt.minute:
                await send_prealarm(guild, s["label"], s["hour"], s["minute"], mins)


@scheduler.before_loop
async def before_scheduler():
    await bot.wait_until_ready()
    now = datetime.now(KST)
    seconds_until_next_minute = 60 - now.second
    await asyncio.sleep(seconds_until_next_minute)


# ============================
# 관리자 명령어
# ============================

@bot.command(name="아그로설정")
@commands.has_permissions(administrator=True)
async def set_agro(ctx, start: int, interval: int):
    """사용법: !아그로설정 [시작시각] [간격]  예: !아그로설정 6 12"""
    global agro_start, agro_interval
    if not (0 <= start <= 23):
        await ctx.send("⚠️ 시작시각은 0~23 사이로 입력해주세요.", delete_after=10)
        return
    if not (1 <= interval <= 24):
        await ctx.send("⚠️ 간격은 1~24 사이로 입력해주세요.", delete_after=10)
        return
    agro_start = start
    agro_interval = interval
    hours = get_agro_hours()
    hours_str = ", ".join([f"{h}시" for h in hours])
    await ctx.send(f"✅ 아그로 변경!\n시작: {start}시 / 간격: {interval}시간\n알림 시각: {hours_str}")


@bot.command(name="아그로상태")
@commands.has_permissions(administrator=True)
async def agro_status(ctx):
    hours = get_agro_hours()
    hours_str = ", ".join([f"{h}시" for h in hours])
    now = datetime.now(KST)
    next_hours = [h for h in hours if h > now.hour]
    next_time = f"{next_hours[0]}시" if next_hours else f"내일 {hours[0]}시"
    await ctx.send(f"⏰ 아그로 설정\n시작: {agro_start}시 / 간격: {agro_interval}시간\n알림 시각: {hours_str}\n다음 알림: **{next_time}**")


@bot.command(name="알림설정")
@commands.has_permissions(administrator=True)
async def post_embed(ctx):
    """알림 구독 임베드 수동 전송"""
    await post_alarm_embed()
    await ctx.message.delete()


@set_agro.error
async def agro_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("⛔ 관리자만 사용 가능합니다.", delete_after=5)
    else:
        await ctx.send("⚠️ 사용법: `!아그로설정 [시작시각] [간격]`\n예: `!아그로설정 6 12`", delete_after=10)


# ============================
# 봇 시작
# ============================

@bot.event
async def on_ready():
    print(f"[봇] {bot.user} 로그인 완료!")
    bot.add_view(AlarmView())
    bot.add_view(PreAlarmView())
    await post_alarm_embed()
    scheduler.start()


bot.run(BOT_TOKEN)
