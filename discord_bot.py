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
    "나흐마": [10],
    "카이라": [2],
    "아티쟁": [30],
    "슈고45": [0],
    "슈고15": [0],
    "아그로": [10]
}

EVENT_DESCRIPTION = {
    "나흐마": "매 주 토, 일요일 오후 10시",
    "카이라": "매 시각",
    "아티쟁": "매 주 화, 목, 토요일 오후 9시",
    "슈고45": "매 시각 45분",
    "슈고15": "매 시각 15분",
    "아그로": "처치 후 12시간 간격"
}

# =========================
# 데이터
# =========================

def load():
    if not os.path.exists(DATA_FILE):
        return {"events": {}, "agro": {}}
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)

data = load()

def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(uid):
    data["events"].setdefault(uid, {})
    return data["events"][uid]

def is_on(uid, key):
    return get_user(uid).get(key, {}).get("on", False)

def get_pre(uid, key):
    # 사용자 지정 pre가 없으면 기본값 사용
    user_pre = get_user(uid).get(key, {}).get("pre", None)
    if user_pre is None:
        return EVENT_DEFAULT_PRE.get(key, [0])
    return user_pre

# =========================
# DM 전송
# =========================

async def send_dm_event(key, text):
    for uid, udata in data["events"].items():
        if not udata.get(key, {}).get("on"):
            continue
        try:
            user = await bot.fetch_user(int(uid))
            await user.send(text)
            print(f"DM 성공 → {uid} ({key})")
        except Exception as e:
            print(f"DM 실패 → {uid} ({key}) : {e}")

# 개별 유저에게 DM 전송
async def send_dm_user(uid, text):
    try:
        user = await bot.fetch_user(int(uid))
        await user.send(text)
        print(f"DM 성공 → {uid}")
    except Exception as e:
        print(f"DM 실패 → {uid} : {e}")

# =========================
# 아그로 변수 (필수)
# =========================

agro_next = None

# 이미 발송한 알림 추적 (중복 방지)
# key: "이벤트키_YYYYMMDDHHMM" → set of uid
sent_cache: dict[str, bool] = {}

def make_cache_key(key, dt: datetime) -> str:
    return f"{key}_{dt.strftime('%Y%m%d%H%M')}"

# =========================
# LOOP
# =========================

@tasks.loop(seconds=30)
async def loop_check():
    global agro_next

    try:
        now = datetime.now(KST)
        weekday = now.weekday()
        hour = now.hour
        minute = now.minute
        second = now.second

        # --------------------------------------------------
        # [수정] 사전 알림(pre)을 반영한 이벤트 발송 헬퍼
        # --------------------------------------------------
        async def check_and_send(key, msg, target_dt: datetime):
            """
            target_dt: 이벤트 발생 예정 시각 (KST, aware)
            pre 분 전에 개별 DM 발송. 중복 방지 캐시 사용.
            """
            for uid in list(data["events"].keys()):
                if not is_on(uid, key):
                    continue
                pres = get_pre(uid, key)
                for pre in pres:
                    send_at = target_dt - timedelta(minutes=pre)
                    diff_sec = (now - send_at).total_seconds()
                    # 발송 윈도우: send_at 기준 ±30초
                    if -30 < diff_sec <= 30:
                        cache_key = make_cache_key(f"{key}_{uid}_{pre}", send_at)
                        if cache_key not in sent_cache:
                            sent_cache[cache_key] = True
                            label = f"{pre}분 전 " if pre > 0 else ""
                            await send_dm_user(uid, f"{label}{msg}")

        # --------------------------------------------------
        # 카이라 — 매 시 정각
        # --------------------------------------------------
        next_kaira = now.replace(minute=0, second=0, microsecond=0)
        if minute > 0:
            next_kaira += timedelta(hours=1)
        await check_and_send("카이라", "⏰ 카이라 등장!", next_kaira)

        # --------------------------------------------------
        # 나흐마 — 토(5), 일(6) 22:00
        # --------------------------------------------------
        if weekday in [5, 6]:
            nahma_dt = now.replace(hour=22, minute=0, second=0, microsecond=0)
            await check_and_send("나흐마", "🔥 나흐마 등장!", nahma_dt)

        # --------------------------------------------------
        # 아티쟁 — 화(1), 목(3), 토(5) 21:00
        # --------------------------------------------------
        if weekday in [1, 3, 5]:
            artisan_dt = now.replace(hour=21, minute=0, second=0, microsecond=0)
            await check_and_send("아티쟁", "⚔️ 아티쟁 등장!", artisan_dt)

        # --------------------------------------------------
        # 슈고45 — 매 시각 45분
        # --------------------------------------------------
        next_45 = now.replace(minute=45, second=0, microsecond=0)
        if minute > 45 or (minute == 45 and second > 30):
            next_45 += timedelta(hours=1)
        await check_and_send("슈고45", "⏰ 슈고 등장! (45분)", next_45)

        # --------------------------------------------------
        # 슈고15 — 매 시각 15분
        # --------------------------------------------------
        next_15 = now.replace(minute=15, second=0, microsecond=0)
        if minute > 15 or (minute == 15 and second > 30):
            next_15 += timedelta(hours=1)
        await check_and_send("슈고15", "⏰ 슈고 등장! (15분)", next_15)

        # --------------------------------------------------
        # 아그로 — 처치 후 12시간 간격
        # [수정] 중복 발송 버그 제거 + timezone 안전 처리
        # --------------------------------------------------
        if agro_next:
            # [버그3 수정] naive datetime이면 KST로 강제 변환
            if agro_next.tzinfo is None:
                agro_next = KST.localize(agro_next)

            await check_and_send("아그로", "⚔️ 아그로 등장!", agro_next)

            # 아그로 시각이 지났으면 12시간 후로 갱신
            if now >= agro_next:
                agro_next += timedelta(hours=12)
                data["agro"]["next"] = agro_next.isoformat()
                save()

        # --------------------------------------------------
        # 오래된 캐시 정리 (1시간 초과 항목 제거)
        # --------------------------------------------------
        expired = [
            k for k in sent_cache
            if _cache_age_minutes(k, now) > 60
        ]
        for k in expired:
            del sent_cache[k]

    except Exception as e:
        print("loop 오류:", e)


def _cache_age_minutes(cache_key: str, now: datetime) -> float:
    """캐시 키에서 시각을 파싱해 현재와의 차이(분)를 반환."""
    try:
        # 형식: "key_uid_pre_YYYYMMDDHHMM"
        dt_str = cache_key[-12:]
        dt = KST.localize(datetime.strptime(dt_str, "%Y%m%d%H%M"))
        return abs((now - dt).total_seconds() / 60)
    except Exception:
        return 0

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    global agro_next

    try:
        if "agro" in data and "next" in data["agro"]:
            parsed = datetime.fromisoformat(data["agro"]["next"])
            # [버그3 수정] timezone 보장
            if parsed.tzinfo is None:
                parsed = KST.localize(parsed)
            agro_next = parsed
    except Exception as e:
        print("아그로 로드 실패:", e)

    await bot.tree.sync()

    # [버그4 수정] 루프 중복 실행 방지
    if not loop_check.is_running():
        loop_check.start()

    ch = bot.get_channel(CHANNEL_ID)
    if ch:
        await ch.send("🔔 알림 설정 완료")

    print("🔥 시작 완료")


bot.run(BOT_TOKEN)
