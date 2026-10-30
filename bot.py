# ============================================================
# تثبيت المكتبات المطلوبة تلقائياً
# ============================================================
import sys
import subprocess
import importlib

def _install_package(pip_name):
    print(f"📦 جاري تثبيت {pip_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
    except Exception as e:
        print(f"⚠️ فشل تثبيت {pip_name}: {e}")

def _ensure_packages(packages):
    for pkg in packages:
        try:
            importlib.import_module(pkg["import_name"])
        except ImportError:
            _install_package(pkg["pip_name"])

_ensure_packages([
    {"import_name": "requests", "pip_name": "requests"},
])

# ============================================================
# الاستيرادات بعد التثبيت
# ============================================================
import requests
import time
from datetime import datetime

# ============================================================
# الإعدادات
# ============================================================
TOKEN = "8086608166:AAHE6ZOLiRr37TUCE1oVJQAdPCFZuYKIHTw"
CHAT_ID = "1248313592"

TIMEFRAME = "15m"           
EMA_SHORT = 3
EMA_MID = 5
EMA_LONG = 20               
RSI_PERIOD = 14
KLINES_LIMIT = 100
SCAN_INTERVAL = 60          
COOLDOWN_MINUTES = 30       

# ⚙️ مفتاح التحكم بالشرط:
# True = يشترط أن تكون EMA3 أصغر من EMA20 (الشرط الصارم)
# False = يكتفي بأن تكون EMA3 أكبر من EMA5 فقط
USE_EMA20_FILTER = False  

BINANCE = "https://api.binance.com"

# ============================================================
# قائمة العملات الحلال (بدون USDT)
# ============================================================
HALAL_COINS = {
    "BTC","ETH","SOL","ADA","XRP","MATIC","DOT","AVAX","LINK","ATOM",
    "LTC","BCH","XLM","ALGO","D","TOWN","ENSO","LUMIA","EIGEN","ONE",
    "BIO","EPIC","AIXBT","DOGE","RIF","AXL","INIT","NIL","CHR","DUSK",
    "MANTA","AR","MAGIC","ANKR","TRB","ZKC","ETC","FIL","XTZ","PARTI",
    "POL","ESP","PROM","OPEN","AVA","CGPT","AMP","ACT","PHB","GTC",
    "IO","ORDI","AT","ARKM","LUNA","ZK","MOVR","ACH","METIS","TAO",
    "RSR","FLUX","ATA","SAGA","CELO","PYTH","OP","DASH","TON","ZEN",
    "KAITO","TIA","BMT","COOKIE","SIGN","STEEM","STRAX","ME","ICP","GALA",
    "WAL","MANA","SENT","GRT","LSK","SUI","HIGH","HYPER","SAPIEN","BAT",
    "DCR","VIRTUAL","XEC","PIVX","XPL","RONIN","TNSR","DENT","DREYAI","HEI",
    "PORTAL","FIDA","CTSI","DGB","DIA","ENS","TRX","GMT","DEXE","KONET",
    "FET","CVC","KSM","WLD","ZAMA","VANRY","GPS"
}

# ============================================================
# تتبع حالة التنبيهات
# ============================================================
alert_states = {}

# ============================================================
# إرسال رسالة تيليجرام
# ============================================================
def send_telegram(text):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=20
        )
        if r.status_code != 200:
            print(f"❌ خطأ تيليجرام ({r.status_code}): {r.text}")
            return False
        return True
    except Exception as e:
        print(f"❌ خطأ اتصال تيليجرام: {e}")
        return False

# ============================================================
# جلب شموع Binance
# ============================================================
def get_klines(symbol, interval, limit=100):
    try:
        r = requests.get(
            f"{BINANCE}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10
        ).json()
        
        if not isinstance(r, list):
            return []
            
        return [
            (float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))
            for k in r
        ]
    except Exception as e:
        return []

def get_24h_tickers():
    try:
        return requests.get(f"{BINANCE}/api/v3/ticker/24hr", timeout=20).json()
    except Exception as e:
        print(f"⚠️ خطأ جلب الأسعار: {e}")
        return []

# ============================================================
# حساب EMA و RSI
# ============================================================
def calc_ema(values, period):
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(values[:period]) / period]
    for v in values[period:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - (100 / (1 + rs))

# ============================================================
# دالة تحديد حالة الفريم (للرسالة)
# ============================================================
def get_trend(klines):
    """صاعد 🟢 = 1 | محايد 🟡 = 0 | هابط 🔴 = -1"""
    if len(klines) < 3:
        return "غير معروف ⚪", 0
    o, h, l, c = klines[-2][0], klines[-2][1], klines[-2][2], klines[-2][3]
    prev_c = klines[-3][3]
    if c > o and c > prev_c:
        return "صاعد 🟢", 1
    if c < o and c < prev_c:
        return "هابط 🔴", -1
    return "محايد 🟡", 0

# ============================================================
# فحص عملة واحدة
# ============================================================
def check_symbol(symbol, price, change24):
    # جلب شموع الفريمات
    k15m = get_klines(symbol, "15m", KLINES_LIMIT)
    k1h  = get_klines(symbol, "1h", 3)
    k4h  = get_klines(symbol, "4h", 3)
    k1d  = get_klines(symbol, "1d", 3)
    k1w  = get_klines(symbol, "1w", 3)

    if not k15m or len(k15m) < EMA_LONG + 5:
        return None

    # استخراج الاتجاهات
    t15m = get_trend(k15m)
    t1h  = get_trend(k1h)
    t4h  = get_trend(k4h)
    t1d  = get_trend(k1d)
    t1w  = get_trend(k1w)

    # ✅ الشرط الجديد: فريم 15 دقيقة غير هابط (يُرفض إذا كان هابطاً)
    if t15m[1] == -1:
        return None

    closes = [k[3] for k in k15m]

    ema3 = calc_ema(closes, EMA_SHORT)
    ema5 = calc_ema(closes, EMA_MID)
    ema20 = calc_ema(closes, EMA_LONG)

    if not ema3 or not ema5 or not ema20:
        return None

    e3 = ema3[-1]
    e5 = ema5[-1]
    e20 = ema20[-1]

    # ===== التحقق من شرط EMA =====
    if USE_EMA20_FILTER:
        if not (e3 > e5 and e3 < e20):
            return None
    else:
        if not (e3 > e5):
            return None

    rsi = calc_rsi(closes, RSI_PERIOD)

    return {
        "symbol": symbol,
        "price": price,
        "change24": change24,
        "ema3": e3,
        "ema5": e5,
        "ema20": e20,
        "rsi": rsi,
        "t15m": t15m[0],
        "t1h": t1h[0],
        "t4h": t4h[0],
        "t1d": t1d[0],
        "t1w": t1w[0],
    }

# ============================================================
# تنسيق الرسالة
# ============================================================
def format_message(data, alert_num, rise_pct):
    rsi = data["rsi"]
    if rsi is None:
        rsi_txt = "غير متاح"
    else:
        if rsi >= 70:
            rsi_txt = f"{rsi:.2f} (تشبع شراء ⚠️)"
        elif rsi <= 30:
            rsi_txt = f"{rsi:.2f} (تشبع بيع 💡)"
        else:
            rsi_txt = f"{rsi:.2f}"

    if alert_num == 1:
        rise_txt = "بداية الإشارة (الرسالة الأولى) 📍"
    else:
        rise_txt = f"<b>+{rise_pct:.2f}%</b> من الرسالة الأولى 📈"

    return f"""🚨 <b>إشارة EMA - تنبيه #{alert_num}</b> 🚨

📌 العملة: <b>{data['symbol'].replace('USDT','')}</b>

💵 السعر: <b>{data['price']:.8f}</b>
📉 تغيير 24س: <b>{data['change24']:.2f}%</b>
📈 RSI({RSI_PERIOD}): <b>{rsi_txt}</b>

📊 <b>حالة الفريمات:</b>
• 15M: {data['t15m']}
• 1H: {data['t1h']}
• 4H: {data['t4h']}
• 1D: {data['t1d']}
• 1W: {data['t1w']}

📊 <b>قيم EMA (15m):</b>
• EMA{EMA_SHORT}: {data['ema3']:.8f}
• EMA{EMA_MID}: {data['ema5']:.8f}
• EMA{EMA_LONG}: {data['ema20']:.8f}

📊 <b>الأداء:</b>
{rise_txt}

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

# ============================================================
# الفحص الرئيسي
# ============================================================
def scan_all():
    print(f"\n🔍 بدء الفحص: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    tickers = get_24h_tickers()
    if not tickers:
        return

    ticker_map = {t["symbol"]: t for t in tickers if t.get("symbol", "").endswith("USDT")}

    now = time.time()
    sent_count = 0
    checked_count = 0
    cooldown_seconds = COOLDOWN_MINUTES * 60

    for coin in HALAL_COINS:
        pair = f"{coin}USDT"

        if pair not in ticker_map:
            continue

        t = ticker_map[pair]

        try:
            price = float(t["lastPrice"])
            change24 = float(t["priceChangePercent"])
        except:
            continue

        checked_count += 1

        # 1. التحقق من الشروط
        result = check_symbol(pair, price, change24)
        if not result:
            continue

        # 2. منطق الترقيم والرسائل
        if pair not in alert_states:
            msg = format_message(result, 1, 0.0)
            if send_telegram(msg):
                alert_states[pair] = {
                    "count": 1,
                    "last_price": price,
                    "first_price": price,
                    "next_check_time": now + cooldown_seconds
                }
                sent_count += 1
                print(f"✅ أُرسلت #1: {pair} | السعر: {price:.8f}")
                time.sleep(0.3)
        else:
            state = alert_states[pair]
            
            # التحقق من الهبوط 3% (إعادة تصفير)
            if price <= state["last_price"] * 0.97:
                msg = format_message(result, 1, 0.0)
                if send_telegram(msg):
                    alert_states[pair] = {
                        "count": 1,
                        "last_price": price,
                        "first_price": price,
                        "next_check_time": now + cooldown_seconds
                    }
                    sent_count += 1
                    print(f"🔄 إعادة تصفير (هبوط 3%): {pair} | السعر: {price:.8f}")
                    time.sleep(0.3)
                continue

            # التحقق من مرور 30 دقيقة
            if now < state["next_check_time"]:
                continue 
            
            # حان وقت الفحص
            if price >= state["last_price"] * 1.01:
                alert_num = state["count"] + 1
                rise_pct = ((price - state["first_price"]) / state["first_price"]) * 100
                msg = format_message(result, alert_num, rise_pct)
                
                if send_telegram(msg):
                    state["count"] = alert_num
                    state["last_price"] = price
                    state["next_check_time"] = now + cooldown_seconds
                    sent_count += 1
                    print(f"✅ أُرسلت #{alert_num}: {pair} | السعر: {price:.8f} | +{rise_pct:.2f}%")
                    time.sleep(0.3)
            else:
                # تأجيل الفحص 30 دقيقة أخرى
                state["next_check_time"] = now + cooldown_seconds
                print(f"⏳ {pair}: مرت 30 دقيقة ولم يصعد 1%. تأجيل.")

    print(f"📊 فُحصت {checked_count} عملة، أُرسلت {sent_count} تنبيه")

# ============================================================
# التشغيل
# ============================================================
if __name__ == "__main__":
    print(f"🚀 بدء البوت...")
    print(f"⚙️ فلتر 15m: غير هابط")
    
    send_telegram(
        f"✅ بدء تشغيل البوت (محدث)\n"
        f"⚙️ الشرط: EMA{EMA_SHORT} > EMA{EMA_MID} (فريم 15m)\n"
        f"📉 فلتر: فريم 15m غير هابط\n"
        f"⏳ كولداون: {COOLDOWN_MINUTES} دقيقة + صعود 1%"
    )

    while True:
        try:
            scan_all()
        except Exception as e:
            print(f"❌ خطأ في الفحص: {e}")
        time.sleep(SCAN_INTERVAL)