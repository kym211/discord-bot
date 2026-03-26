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
# DM 전송
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
# LOOP
# =========================

@tasks.loop(seconds=30)
async def loop_check():

    global agro_next

    now=datetime.now(KST)

    weekday=now.weekday()
    hour=now.hour
    minute=now.minute
    second=now.second

    # =========================
    # 카이라 (매시)
    # =========================

    if minute==0 and second<30:

        for uid in data["events"]:

            if not is_on(uid,"카이라"):
                continue

            pres=get_pre(uid,"카이라")

            for p in pres:

                target=now.replace(
                    minute=0,
                    second=0
                )-timedelta(minutes=p)

                if abs(
                    (now-target).total_seconds()
                )<30:

                    await send_dm_event(
                        "카이라",
                        f"⏰ 카이라 {p}분 전"
                    )

        await send_dm_event(
            "카이라",
            "⏰ 카이라 등장!"
        )

    # =========================
    # 나흐마
    # =========================

    if weekday in [5,6]:

        target=now.replace(
            hour=22,
            minute=0,
            second=0
        )

        for uid in data["events"]:

            if not is_on(uid,"나흐마"):
                continue

            pres=get_pre(uid,"나흐마")

            for p in pres:

                if abs(
                    (now-(target-timedelta(minutes=p)))
                    .total_seconds()
                )<30:

                    await send_dm_event(
                        "나흐마",
                        f"🔥 나흐마 {p}분 전"
                    )

        if hour==22 and minute==0 and second<30:

            await send_dm_event(
                "나흐마",
                "🔥 나흐마 등장!"
            )

    # =========================
    # 아티쟁
    # =========================

    if weekday in [1,3,5]:

        target=now.replace(
            hour=21,
            minute=0,
            second=0
        )

        for uid in data["events"]:

            if not is_on(uid,"아티쟁"):
                continue

            pres=get_pre(uid,"아티쟁")

            for p in pres:

                if abs(
                    (now-(target-timedelta(minutes=p)))
                    .total_seconds()
                )<30:

                    await send_dm_event(
                        "아티쟁",
                        f"⚔️ 아티쟁 {p}분 전"
                    )

        if hour==21 and minute==0 and second<30:

            await send_dm_event(
                "아티쟁",
                "⚔️ 아티쟁 등장!"
            )

    # =========================
    # 슈고
    # =========================

    if minute==45 and second<30:

        await send_dm_event(
            "슈고45",
            "⏰ 슈고 등장!"
        )

    if minute==15 and second<30:

        await send_dm_event(
            "슈고15",
            "⏰ 슈고 등장!"
        )

    # =========================
    # 아그로
    # =========================

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
            "🔔 알림 설정"
        )

    print("🔥 시작 완료")

bot.run(BOT_TOKEN)
