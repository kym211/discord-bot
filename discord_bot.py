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

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

DATA_FILE = "data.json"

# =========================
# 기본 사전시간
# =========================

EVENT_DEFAULT_PRE = {

    "나흐마":[10],
    "카이라":[2],
    "아티쟁":[30],

    "슈고45":[0],
    "슈고15":[0],

    "아그로":[10]

}

EVENT_DESCRIPTION = {

    "나흐마":"매 주 토, 일요일 오후 10시",
    "카이라":"매 시각",
    "아티쟁":"매 주 화, 목, 토요일 오후 9시",
    "슈고45":"매 시각 45분",
    "슈고15":"매 시각 15분",
    "아그로":"처치 후 12시간 간격"

}

# =========================
# 데이터
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

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

def get_user(uid):

    data["events"].setdefault(uid,{})
    return data["events"][uid]

def is_on(uid,key):

    return get_user(uid)\
        .get(key,{})\
        .get("on",False)

def get_pre(uid,key):

    return get_user(uid)\
        .get(key,{})\
        .get("pre",[])

# =========================
# DM 전송 (중요 수정)
# =========================

async def send_dm_event(key,text):

    for uid,udata in data["events"].items():

        if not udata.get(key,{}).get("on"):
            continue

        try:

            user = await bot.fetch_user(int(uid))

            await user.send(text)

            print(
                f"DM 성공 → {uid} ({key})"
            )

        except Exception as e:

            print(
                f"DM 실패 → {uid} ({key}) : {e}"
            )

# =========================
# 사전 Embed
# =========================

def build_pre_embed(key,uid):

    selected=get_pre(uid,key)

    desc=EVENT_DESCRIPTION.get(key,"")

    embed=discord.Embed(

        title=f"⏱ {key}",
        description=desc,
        color=0x2b2d31

    )

    if key in ["슈고45","슈고15"]:

        embed.add_field(

            name="알림 방식",

            value="정시 알림 (0분 전)",

            inline=False

        )

    elif selected:

        embed.add_field(

            name="선택됨",

            value=", ".join(
                [f"{m}분 전"
                 for m in sorted(selected)]
            )

        )

    return embed

# =========================
# 사전 버튼
# =========================

class PreButton(discord.ui.Button):

    def __init__(self,key,uid,m):

        selected=m in get_pre(uid,key)

        super().__init__(

            label=f"{m}분",

            style=(
                discord.ButtonStyle.success
                if selected
                else discord.ButtonStyle.secondary
            )

        )

        self.key=key
        self.uid=uid
        self.m=m

    async def callback(self,i):

        arr=get_user(self.uid)\
            .setdefault(self.key,{})\
            .setdefault("pre",[])

        if self.m in arr:
            arr.remove(self.m)
        else:
            arr.append(self.m)

        save()

        view=PreView(self.key,self.uid)
        view.message=i.message

        await i.response.edit_message(

            embed=build_pre_embed(
                self.key,self.uid
            ),

            view=view

        )

class PreView(discord.ui.View):

    def __init__(self,key,uid):

        super().__init__(timeout=30)

        self.key=key
        self.uid=uid
        self.message=None

        if key in ["슈고45","슈고15"]:
            return

        for m in [2,5,10,20,30,60]:

            self.add_item(
                PreButton(
                    key,uid,m
                )
            )

    async def on_timeout(self):

        try:
            if self.message:
                await self.message.delete()
        except:
            pass

# =========================
# 토글 버튼
# =========================

class ToggleButton(discord.ui.Button):

    def __init__(self,key,uid,row):

        on=is_on(uid,key)

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

        u=get_user(self.uid)

        ev=u.setdefault(self.key,{})

        new_state=not ev.get("on",False)

        ev["on"]=new_state

        if new_state:

            default_pre=EVENT_DEFAULT_PRE.get(
                self.key,
                []
            )

            ev["pre"]=default_pre.copy()

        else:

            ev["pre"]=[]

        save()

        view=ControlView(self.uid)
        view.message=i.message

        await i.response.edit_message(
            view=view
        )

        if new_state:

            pre_view=PreView(
                self.key,self.uid
            )

            msg=await i.followup.send(

                embed=build_pre_embed(
                    self.key,self.uid
                ),

                view=pre_view,

                ephemeral=True

            )

            pre_view.message=msg

# =========================

class ControlView(discord.ui.View):

    def __init__(self,uid):

        super().__init__(timeout=60)

        self.uid=uid
        self.message=None

        keys=list(EVENT_DEFAULT_PRE.keys())

        row=0
        count=0

        for k in keys:

            self.add_item(
                ToggleButton(
                    k,uid,row
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

agro_next=None

@bot.tree.command(
name="아그로",
description="공용 아그로 시간 설정"
)
async def agro_cmd(
interaction: discord.Interaction,
time:str
):

    global agro_next

    t=time.zfill(4)

    h=int(t[:2])
    m=int(t[2:])

    now=datetime.now(KST)

    start=now.replace(
        hour=h,
        minute=m,
        second=0,
        microsecond=0
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

        f"✅ 공용 아그로 설정 완료\n다음 {start.strftime('%H:%M')}"

    )

# =========================
# LOOP (중요 수정)
# =========================

@tasks.loop(seconds=30)
async def loop_check():

    global agro_next

    now=datetime.now(KST)

    # 아그로 사전알림

    if agro_next:

        diff=int(
            (agro_next-now)
            .total_seconds()/60
        )

        for uid in data["events"]:

            if not is_on(uid,"아그로"):
                continue

            pres=get_pre(uid,"아그로")

            if diff in pres:

                await send_dm_event(
                    "아그로",
                    f"⚔️ 아그로 {diff}분 전"
                )

        if now>=agro_next:

            agro_next+=timedelta(hours=12)

            data["agro"]["next"]\
                =agro_next.isoformat()

            save()

    # 슈고 등장

    if now.minute == 45 and now.second < 30:

        await send_dm_event(
            "슈고45",
            "⏰ 슈고 등장!"
        )

    if now.minute == 15 and now.second < 30:

        await send_dm_event(
            "슈고15",
            "⏰ 슈고 등장!"
        )

# =========================
# READY
# =========================

@bot.event
async def on_ready():

    global agro_next

    try:

        if "agro" in data and "next" in data["agro"]:

            agro_next=datetime.fromisoformat(

                data["agro"]["next"]

            )

    except Exception as e:

        print("아그로 로드 실패:",e)

    await bot.tree.sync()

    if not loop_check.is_running():
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
