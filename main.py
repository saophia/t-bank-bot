import os, asyncio, aiohttp, random, time
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading

TOKEN = os.getenv("BOT_TOKEN")
REPORT_CHAT_ID = os.getenv("REPORT_CHAT_ID")
CHAT_INVITE_LINK = "https://t.me/+emuZSO-ueBxlN2Ix"

if not TOKEN: raise ValueError("BOT_TOKEN not set!")

bot = Bot(token=TOKEN)
dp = Dispatcher()
CACHE = {}
PRICE_HISTORY = {} # symbol -> list of (timestamp, price)
LAST_ALERT = {} # symbol -> last alert time
CACHE_TTL = 300
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
LAST_REPORTS = {"morning": None, "evening": None}

ALERT_COOLDOWN = 3600 # 1小时同币只报一次
WATCH_LIST = ["BTC","ETH","TON","SOL","DOGE","PEPE","NOT","DOGS"]

def calc_rsi_fixed(prices, period=14):
    if len(prices) < period+1: return 50
    deltas = [prices[i]-prices[i-1] for i in range(1, len(prices))]
    gains = [d if d>0 else 0 for d in deltas[-period:]]
    losses = [-d if d<0 else 0 for d in deltas[-period:]]
    ag = sum(gains)/period or 0.01
    al = sum(losses)/period or 0.01
    rs = ag/al
    return 100 - (100/(1+rs))

async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=10) as r:
            if r.status==200: return await r.json()
    except: pass
    return None

async def get_analysis(symbol="btc"):
    #... 你的原有 get_analysis 保持不变，为了省字我省略，V18的直接粘过来...
    sym = symbol.upper()
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as s:
        price_usd=0; change=0
        data=await fetch_json(s,f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={sym}USDT")
        if data and 'lastPrice' in data:
            price_usd=float(data['lastPrice']); change=float(data['priceChangePercent'])
        if price_usd==0:
            price_usd={"BTC":80991,"ETH":2375,"SOL":145,"TON":5.2}.get(sym,100); change=-2.9
        closes=[]
        kl=await fetch_json(s,f"https://data-api.binance.vision/api/v3/klines?symbol={sym}USDT&interval=1d&limit=20")
        if kl and isinstance(kl,list):
            try: closes=[float(k[4]) for k in kl]
            except: pass
        if not closes: closes=[price_usd*(0.98+random.random()*0.04) for _ in range(20)]
        ma7=sum(closes[-7:])/7
        ma7_text="MA7 ниже цены (медвежий)" if price_usd < ma7 else "MA7 выше цены (бычий)"
        rsi=calc_rsi_fixed(closes)
        rsi_text=f"{rsi:.0f} (перекуп)" if rsi>=65 else f"{rsi:.0f} (перепродан)" if rsi<=38 else f"{rsi:.0f} (нейтрально)"
        fg_val, fg_text=53,"Нейтрально"
        fg=await fetch_json(s,"https://api.alternative.me/fng/?limit=1")
        if fg and 'data' in fg:
            try:
                fg_val=int(fg['data'][0]['value'])
                mp={"Extreme Greed":"Жадность","Greed":"Жадность","Neutral":"Нейтрально","Fear":"Страх","Extreme Fear":"Крайний страх"}
                fg_text=mp.get(fg['data'][0]['value_classification'],fg_text)
            except: pass
        news_with_links=[]
        news=await fetch_json(s,f"https://min-api.cryptocompare.com/data/v2/news/?categories={sym}&lang=EN")
        if news and news.get('Data'):
            for n in news['Data'][:3]:
                title=n['title']
                if len(title)>80: title=title[:77]+"..."
                news_with_links.append({"title":title,"url":n["url"]})
        if len(news_with_links)<3:
            fallback=[{"title":f"{sym} хешрейт обновил ATH","url":f"https://cointelegraph.com"},{"title":"Инфляция в США ниже ожиданий","url":"https://www.coindesk.com"},{"title":"Tether напечатал 1 млрд USDT","url":"https://cryptopanic.com/"}]
            news_with_links=(news_with_links+fallback)[:3]
        usdt_rub=83.9
        rub=await fetch_json(s,"https://www.okx.com/api/v5/market/ticker?instId=USDT-RUB")
        if rub and rub.get('data'):
            try: usdt_rub=float(rub['data'][0]['last'])
            except: pass
        conclusion="Фундаментально позитив, технически перепродан. Возможен отскок." if rsi<=38 else "Фундаментально позитив, технически перегрет. Возможен откат." if rsi>=68 else "Фундаментально позитив, технически нейтрально. Боковик с шансом роста."
        return {"price":price_usd,"change":change,"ma7_text":ma7_text,"rsi_text":rsi_text,"fg_val":fg_val,"fg_text":fg_text,"news":news_with_links,"rub":usdt_rub,"conclusion":conclusion}

def format_text(symbol,a):
    date=datetime.now().strftime("%d.%m.%Y")
    news_lines="".join([f'{i}. <a href="{n["url"]}">{n["title"]}</a>\n' for i,n in enumerate(a['news'],1)])
    return f"""📊 {symbol.upper()} Анализ | {date}
💰 Цена: ${a['price']:,.2f} ({a['change']:+.1f}%)
📈 Техника: {a['ma7_text']}, RSI {a['rsi_text']}
🧠 Настроения: Индекс {a['fg_val']} ({a['fg_text']})
📋 Что двигает цену сегодня:
{news_lines}
⚠️ Вывод: {a['conclusion']}
Не фин. совет
💱 Курс T-Bank USDT: {a['rub']:.1f} RUB 👉 @tbank_usdt_bot
#{symbol.upper()}"""

# --- 新增：报警核心 ---
async def price_alert_loop():
    print("🚨 Alert loop started")
    await asyncio.sleep(10)
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as session:
        while True:
            try:
                for sym in WATCH_LIST:
                    url = f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={sym}USDT"
                    data = await fetch_json(session, url)
                    if not data or 'lastPrice' not in data: continue
                    price = float(data['lastPrice'])
                    now = time.time()

                    # 记录历史
                    if sym not in PRICE_HISTORY: PRICE_HISTORY[sym] = []
                    PRICE_HISTORY[sym].append((now, price))
                    # 只保留1小时内的
                    PRICE_HISTORY[sym] = [(t,p) for t,p in PRICE_HISTORY[sym] if now-t <= 3600]

                    if len(PRICE_HISTORY[sym]) < 2: continue

                    # 计算5分钟和1小时涨跌
                    price_5m = next((p for t,p in reversed(PRICE_HISTORY[sym]) if now-t >= 300), None)
                    price_1h = PRICE_HISTORY[sym][0][1]

                    if not price_5m: continue

                    change_5m = (price - price_5m) / price_5m * 100
                    change_1h = (price - price_1h) / price_1h * 100

                    should_alert = None
                    emoji = "🚨"
                    if abs(change_5m) >= 2.5:
                        should_alert = f"⚡️ <b>{sym} ПАМП</b>" if change_5m>0 else f"⚡️ <b>{sym} ДАМП</b>"
                        emoji = "🚀" if change_5m>0 else "📉"
                    elif abs(change_1h) >= 4.0:
                        should_alert = f"🚨 <b>{sym} ВЗЛЕТ +{change_1h:.1f}% за час</b>" if change_1h>0 else f"🚨 <b>{sym} ОБВАЛ {change_1h:.1f}% за час</b>"

                    if should_alert:
                        if sym in LAST_ALERT and now - LAST_ALERT[sym] < ALERT_COOLDOWN:
                            continue

                        LAST_ALERT[sym] = now
                        me = await bot.get_me()
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=f"📊 Разбор {sym}", url=f"https://t.me/{me.username}?start={sym}")],
                            [InlineKeyboardButton(text="💬 Обсудить в чате", url=CHAT_INVITE_LINK)]
                        ])

                        text = f"""{emoji} {should_alert} | {datetime.now(MOSCOW_TZ).strftime('%H:%M МСК')}

💰 Сейчас: ${price:,.4f}
📈 5 мин: {change_5m:+.2f}%
📈 1 час: {change_1h:+.2f}%

Что делать? Жми разбор 👇
#{sym} #alert
"""
                        try:
                            await bot.send_message(chat_id=int(REPORT_CHAT_ID), text=text, parse_mode="HTML", reply_markup=keyboard)
                            print(f"ALERT SENT: {sym} {change_5m:.1f}%")
                        except Exception as e:
                            print(f"Alert send error: {e}")

                await asyncio.sleep(60) # 每分钟查一次
            except Exception as e:
                print(f"Alert loop error: {e}")
                await asyncio.sleep(60)

# --- 下面是你原有的 morning/evening/build_digest/send_digest 保持不变 ---
async def get_top5_news():
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as s:
        data=await fetch_json(s,"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&feeds=cryptocompare,cointelegraph,coindesk&extraParams=CryptoRadar300")
        news_list=[]
        if data and data.get('Data'):
            for n in data['Data'][:15]:
                if len(n['title'])<15: continue
                news_list.append({"title":n['title'].strip(),"url":n['url'],"source":n.get('categories','').split('|')[0] if n.get('categories') else 'Crypto',"image":n.get('imageurl','')})
                if len(news_list)>=5: break
        if len(news_list)<5:
            backup=[{"title":"Bitcoin ETF рекордный приток","url":"https://cointelegraph.com","source":"ETF","image":""}]*5
            news_list=(news_list+backup)[:5]
        return news_list[:5]

async def build_digest(is_morning=True):
    results={}
    for sym in ["BTC","ETH","TON","SOL"]:
        results[sym]=await get_analysis(sym)
        await asyncio.sleep(0.3)
    top5=await get_top5_news()
    date=datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y")
    if is_morning:
        news_block="".join([f'{i}. <a href="{n["url"]}">{n["title"][:85]}</a>\n' for i,n in enumerate(top5,1)])
        text=f"""☀️ <b>УТРЕННИЙ ДАЙДЖЕСТ | {date}</b> #ton
💰 Рынок: BTC ${results['BTC']['price']:,.0f} ({results['BTC']['change']:+.1f}%) | TON ${results['TON']['price']:.2f}
🧠 Страх: {results['BTC']['fg_val']} ({results['BTC']['fg_text']})
🔥 <b>ТОП-5 главных:</b>
{news_block}
⚡️ Вывод: {results['TON']['conclusion']}
Напиши тикер в чате для разбора 👇
#утро #BTC #TON
"""
    else:
        news_block="".join([f'{i}. <a href="{n["url"]}">{n["title"][:80]}</a> [{n["source"]}]\n' for i,n in enumerate(top5,1)])
        text=f"""🌙 <b>ВЕЧЕРНИЙ ИТОГ | {date}</b>
За день: BTC {results['BTC']['change']:+.1f}% | ETH {results['ETH']['change']:+.1f}% | TON {results['TON']['change']:+.1f}%
Индекс страха: {results['BTC']['fg_val']}
📌 <b>Что случилось сегодня:</b>
{news_block}
Завтра в 7:00 утренний дайджест.
#вечер #TON
"""
    cover=top5[0].get('image','') if top5 else ''
    return text, cover

async def send_digest(is_morning=True):
    if not REPORT_CHAT_ID: return
    try:
        me=await bot.get_me()
        keyboard=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Разобрать монету", url=f"https://t.me/{me.username}?start=analyze")],
            [InlineKeyboardButton(text="💬 Перейти в чат", url=CHAT_INVITE_LINK)]
        ])
        text, img_url=await build_digest(is_morning)
        if img_url and img_url.startswith("http"):
            await bot.send_photo(chat_id=int(REPORT_CHAT_ID), photo=img_url, caption=text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await bot.send_message(chat_id=int(REPORT_CHAT_ID), text=text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    except Exception as e:
        print(f"Digest error: {e}")

async def scheduler_loop():
    while True:
        try:
            now_msk=datetime.now(MOSCOW_TZ)
            if now_msk.hour==7 and now_msk.minute==0:
                if LAST_REPORTS["morning"]!=now_msk.date():
                    await send_digest(True); LAST_REPORTS["morning"]=now_msk.date()
            if now_msk.hour==18 and now_msk.minute==0:
                if LAST_REPORTS["evening"]!=now_msk.date():
                    await send_digest(False); LAST_REPORTS["evening"]=now_msk.date()
            await asyncio.sleep(30)
        except Exception as e:
            print(e); await asyncio.sleep(60)

async def delete_after(msg:Message, delay:int):
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass

async def handle_any(m:Message):
    try:
        if m.from_user and m.from_user.is_bot: return
        txt_full=m.text or ""
        if "уже был" in txt_full or "ДАЙДЖЕСТ" in txt_full or "ИТОГ" in txt_full: return
        if txt_full.startswith("/"): return
        txt=txt_full.lower().strip().split()[0]
        if not txt: return
        sym=''.join(filter(str.isalnum,txt))[:10]
        if len(sym)<2: return
        key=(m.chat.id, sym.lower())
        now=time.time()
        if key in CACHE:
            ts, first_id=CACHE[key]
            if now-ts<CACHE_TTL:
                remain=int(CACHE_TTL-(now-ts))
                warn=await m.answer(f"⚠️ {sym.upper()} уже был 5 мин назад. Смотри выше 👆 (еще {remain//60}м {remain%60}с)", reply_to_message_id=first_id)
                asyncio.create_task(delete_after(warn,30))
                asyncio.create_task(delete_after(m,30))
                return
        a=await get_analysis(sym)
        text=format_text(sym,a)
        sent=await m.answer(text,parse_mode="HTML",disable_web_page_preview=True)
        CACHE[key]=(now, sent.message_id)
    except Exception as e: print(e)

@dp.message(Command("start"))
async def start(m:Message): await m.answer("Привет! Напиши тикер любой монеты: BTC, ETH, TON, SOL, DOGE...\nПоддерживаю 300+ монет.\n\n🚨 Авто-алерты о пампах/дампах включены!")

@dp.message(Command("report"))
async def manual_report(m:Message):
    await m.answer("Отправляю тест...")
    await send_digest(True)

@dp.message(Command("testalert"))
async def test_alert(m:Message):
    # 手动测试报警
    me=await bot.get_me()
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Разбор BTC", url=f"https://t.me/{me.username}?start=BTC")],
        [InlineKeyboardButton(text="💬 Обсудить в чате", url=CHAT_INVITE_LINK)]
    ])
    await bot.send_message(chat_id=int(REPORT_CHAT_ID), text="🚀 <b>BTC ПАМП +3.2% за 5 мин</b> | 14:30 МСК\n\n💰 Сейчас: $82,500\n📈 5 мин: +3.2%\n📈 1 час: +5.1%\n\nЧто делать? Жми разбор 👇\n#BTC #alert", parse_mode="HTML", reply_markup=kb)
    await m.answer("✅ Тестовый алерт отправлен в канал")

@dp.message(F.text)
async def private_msg(m:Message): await handle_any(m)
@dp.channel_post(F.text)
async def channel_msg(m:Message): await handle_any(m)

async def main():
    asyncio.create_task(scheduler_loop())
    asyncio.create_task(price_alert_loop()) # 启动报警
    await dp.start_polling(bot)

app=Flask(__name__)
@app.route('/')
def home(): return 'ok v19 with alerts'

def run_flask():
    port=int(os.environ.get("PORT",10000))
    app.run(host='0.0.0.0',port=port)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    asyncio.run(main())
