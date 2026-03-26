import discord
from discord.ext import commands, tasks
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
# 기본 데이터
# =========================

def load():

    if not os.path.exists(DATA_FILE):

        return {
            "events": {},
            "agro": {}
        }

    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)

data = load()

def save():

    with open(DATA_FILE,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)

# =========================
# DM 전송 함수
# =========================

async def send_dm_event(event_name, text):

    for uid, udata in data["events"].items():

        if udata.get(event_name,{}).get("on"):

            user = bot.get_user(int(uid))

            if user:

                try:
                    await user.send(text)
                except:
                    pass

# =========================
# 버튼 UI
# =========================

class ToggleButton(discord.ui.Button):

    def __init__(self,key,uid,row):

        on=data["events"]\
            .get(uid,{})\
            .get(key,{})\
            .get("on",False)

        super().__init__(

            label=key,

            style=(
                discord.ButtonStyle.success
                if on
                else discord.ButtonStyle.danger
            ),

            row=row

        )

        self.key=key
        self.uid=uid

    async def callback(self,i):

        u=data["events"].setdefault(
            self.uid,
            {}
        )

        ev=u.setdefault(
            self.key,
            {}
        )

        ev["on"]=not ev.get(
            "on",
            False
        )

        save()

        view=ControlView(self.uid)
        view.message=i.message

        await i.response.edit_message(
            view=view
        )

# =========================

class ControlView(discord.ui.View):

    def __init__(self,uid):

        super().__init__(timeout=60)

        self.uid=uid
        self.message=None

        keys=[
            "나흐마",
            "카이라",
            "아티쟁",
            "슈고45",
            "슈고15",
            "아그로"
        ]

        row=0
        count=0

        for k in keys:

            self.add_item(
                ToggleButton(
                    k,
                    uid,
                    row
                )
            )

            count+=1

            if count%5==0:
                row+=1

    async def on_timeout(self):

        try:
            if self.message:
                await self.message.delete()
        except:
            pass

# =========================

class MainView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 목록",
        style=discord.ButtonStyle.primary
    )
    async def list_btn(self,i,b):

        view=ControlView(
            str(i.user.id)
        )

        await i.response.send_message(
            view=view,
            ephemeral=True
        )

        view.message = await i.original_response()

# =========================
# 아그로
# =========================

agro_next = None

@bot.tree.command(
name="아그로",
description="공용 아그로 시간 설정"
)
async def agro_cmd(
interaction: discord.Interaction,
time:str,
mode:str=""
):

    global agro_next

    t=time.zfill(4)

    h=int(t[:2])
    m=int(t[2:])

    now=datetime.now(KST)

    if mode=="후에":

        start=(now+
            timedelta(
                hours=h,
                minutes=m
            )
        ).replace(second=0)

    else:

        start=now.replace(
            hour=h,
            minute=m,
            second=0
        )

        if start<=now:
            start+=timedelta(hours=12)

    agro_next=start

    data["agro"]={
        "on":True,
        "next":start.isoformat()
    }

    save()

    await interaction.response.send_message(

        f"✅ 공용 아그로 설정 완료\n다음 {start.strftime('%H:%M')}",

        ephemeral=False
    )

    await interaction.delete_original_response(delay=30)

# =========================
# 알림 루프
# =========================

@tasks.loop(seconds=60)
async def loop_check():

    global agro_next

    now=datetime.now(KST)

    # 카이라
    if now.minute==0:

        await send_dm_event(
            "카이라",
            "⏰ 카이라 등장!"
        )

    # 슈고45
    if now.minute==45:

        await send_dm_event(
            "슈고45",
            "⏰ 슈고 45분 등장!"
        )

    # 슈고15
    if now.minute==15:

        await send_dm_event(
            "슈고15",
            "⏰ 슈고 15분 등장!"
        )

    # 나흐마
    if now.weekday() in [5,6]:

        if now.hour==22 and now.minute==0:

            await send_dm_event(
                "나흐마",
                "⏰ 나흐마 등장!"
            )

    # 아티쟁
    if now.weekday() in [1,3,5]:

        if now.hour==21 and now.minute==0:

            await send_dm_event(
                "아티쟁",
                "⏰ 아티쟁 등장!"
            )

    # 아그로
    if agro_next:

        if now>=agro_next:

            await send_dm_event(
                "아그로",
                "⚔️ 아그로!"
            )

            new_time=agro_next+timedelta(hours=12)

            agro_next=new_time

            data["agro"]["next"]=new_time.isoformat()

            save()

# =========================
# READY
# =========================

@bot.event
async def on_ready():

    global agro_next

    if "agro" in data:

        agro_data=data["agro"]

        if agro_data.get("on"):

            try:

                agro_next=datetime.fromisoformat(
                    agro_data["next"]
                )

            except:
                pass

    await bot.tree.sync()

    loop_check.start()

    ch=bot.get_channel(
        CHANNEL_ID
    )

    if ch:

        await ch.send(
            "🔔 알림 설정",
            view=MainView()
        )

    print("🔥 시작 완료")

bot.run(BOT_TOKEN)
