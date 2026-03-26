import discord
from discord.ext import commands, tasks
import os, json
from datetime import datetime, timedelta
import pytz

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # 경고 해결용

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# =====================
# 데이터
# =====================

def load():
    if not os.path.exists(DATA_FILE):
        return {"events": {}}
    return json.load(open(DATA_FILE))

data = load()
dirty = False

def save():
    global dirty
    dirty = True

# =====================
# 기본 이벤트 (🔥 전부 통일)
# =====================

DEFAULT_EVENTS = {
    "나흐마": {"time": [(22,0)], "weekdays":[5,6]},
    "아티쟁": {"time": [(21,0)], "weekdays":[1,3,5]},

    "카이라": {"time": [(h,0) for h in range(24)]},
    "슈고15": {"time": [(h,15) for h in range(24)]},
    "슈고45": {"time": [(h,45) for h in range(24)]},
}

# =====================
# 유저 데이터
# =====================

def get_user(uid):
    data["events"].setdefault(uid, {})
    return data["events"][uid]

def is_on(uid, key):
    return get_user(uid).get(key, {}).get("on", False)

def get_pre(uid, key):
    return get_user(uid).get(key, {}).get("pre", [])

# =====================
# UI - 사전 알림
# =====================

class PreButton(discord.ui.Button):
    def __init__(self, key, uid, m):
        selected = m in get_pre(uid, key)
        style = discord.ButtonStyle.success if selected else discord.ButtonStyle.secondary
        super().__init__(label=f"{m}분", style=style)

        self.key=key; self.uid=uid; self.m=m

    async def callback(self, i):
        if not is_on(self.uid,self.key):
            await i.response.send_message("❌ ON 먼저",ephemeral=True)
            return

        u=get_user(self.uid)
        u.setdefault(self.key,{}).setdefault("pre",[])

        arr=u[self.key]["pre"]

        if self.m in arr: arr.remove(self.m)
        else: arr.append(self.m)

        save()

        await i.response.edit_message(view=PreView(self.key,self.uid))

class PreView(discord.ui.View):
    def __init__(self,key,uid):
        super().__init__(timeout=120)
        for m in [2,5,10,20,30,60]:
            self.add_item(PreButton(key,uid,m))

# =====================
# ON/OFF 버튼
# =====================

class ToggleButton(discord.ui.Button):
    def __init__(self,key,uid):
        style=discord.ButtonStyle.success if is_on(uid,key) else discord.ButtonStyle.danger
        super().__init__(label=f"{key}",style=style)

        self.key=key; self.uid=uid

    async def callback(self,i):
        u=get_user(self.uid)
        u.setdefault(self.key,{})

        u[self.key]["on"]=not is_on(self.uid,self.key)

        save()

        if u[self.key]["on"]:
            await i.response.send_message(
                f"{self.key} 사전알림 설정",
                view=PreView(self.key,self.uid),
                ephemeral=True
            )
        else:
            await i.response.edit_message(view=ControlView(self.uid))

class ControlView(discord.ui.View):
    def __init__(self,uid):
        super().__init__(timeout=120)

        keys = list(DEFAULT_EVENTS.keys()) + list(get_user(uid).keys())

        for k in keys:
            self.add_item(ToggleButton(k,uid))

# =====================
# 커스텀
# =====================

class CustomNameModal(discord.ui.Modal,title="커스텀 이름"):
    name=discord.ui.TextInput(label="이름")

    async def on_submit(self,i):
        uid=str(i.user.id)
        name=self.name.value

        u=get_user(uid)
        u[name]={"on":True,"time":[],"pre":[]}

        save()

        await i.response.send_modal(CustomTimeModal(name))

class CustomTimeModal(discord.ui.Modal,title="시간 설정"):
    time=discord.ui.TextInput(label="예:0930")

    def __init__(self,name):
        super().__init__()
        self.name=name

    async def on_submit(self,i):
        uid=str(i.user.id)

        t=self.time.value.zfill(4)
        h,m=int(t[:2]),int(t[2:])

        get_user(uid)[self.name]["time"]=[(h,m)]

        save()

        await i.response.send_message(
            "사전알림 설정",
            view=PreView(self.name,uid),
            ephemeral=True
        )

# =====================
# 메인 UI
# =====================

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⚙️ ON/OFF",custom_id="toggle")
    async def t(self,i,b):
        await i.response.send_message(
            view=ControlView(str(i.user.id)),
            ephemeral=True
        )

    @discord.ui.button(label="➕ 커스텀",custom_id="custom")
    async def c(self,i,b):
        await i.response.send_modal(CustomNameModal())

# =====================
# 알림
# =====================

async def send(key):
    for g in bot.guilds:
        for m in g.members:
            uid=str(m.id)
            if is_on(uid,key):
                try:
                    await m.send(f"🔔 {key}")
                except:
                    pass

async def send_pre(key):
    for g in bot.guilds:
        for m in g.members:
            uid=str(m.id)
            if is_on(uid,key):
                for mins in get_pre(uid,key):
                    await m.send(f"⏱ {key} {mins}분 전")

# =====================
# 스케줄
# =====================

@tasks.loop(minutes=1)
async def loop():
    now=datetime.now(KST)

    # 기본 이벤트
    for k,v in DEFAULT_EVENTS.items():
        for h,m in v["time"]:
            if now.hour==h and now.minute==m:
                if not v.get("weekdays") or now.weekday() in v["weekdays"]:
                    await send(k)

    # 커스텀
    for uid,u in data["events"].items():
        for k,v in u.items():
            if v.get("time"):
                for h,m in v["time"]:
                    if now.hour==h and now.minute==m:
                        if v.get("on"):
                            user=bot.get_user(int(uid))
                            if user:
                                try:
                                    await user.send(f"🔔 {k}")
                                except:
                                    pass

# =====================
# 저장
# =====================

@tasks.loop(seconds=10)
async def save_loop():
    global dirty
    if dirty:
        json.dump(data,open(DATA_FILE,"w"))
        dirty=False

# =====================
# 실행
# =====================

@bot.event
async def on_ready():
    if not hasattr(bot,"ready"):
        ch=bot.get_channel(CHANNEL_ID)
        await ch.send("🔔 알림 설정",view=MainView())

        loop.start()
        save_loop.start()

        bot.ready=True

    print("🔥 완전 최종 코드 실행")

bot.run(BOT_TOKEN)
