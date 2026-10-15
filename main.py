import os, asyncio, aiohttp, random, time, re, io, textwrap
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from flask import Flask
import threading

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except:
    HAS_PIL = False
    print("WARNING: Pillow not installed")

TOKEN = os.getenv("BOT_TOKEN")
REPORT_CHAT_ID = os.getenv("REPORT_CHAT_ID") or "-1004496994086"
CHAT_INVITE_LINK = "https://t.me/+emuZSO-ueBxlN2Ix"

if not TOKEN: raise ValueError("BOT_TOKEN not set!")

bot = Bot(token=TOKEN)
dp = Dispatcher()
CACHE = {}; PRICE_HISTORY = {}; LAST_ALERT = {}; CACHE_TTL = 300
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
LAST_REPORTS = {"morning": None, "evening": None}
ALERT_COOLDOWN = 3600
WATCH_LIST = ["BTC","ETH","TON","SOL","DOGE","PEPE","NOT","DOGS"]

def calc_rsi_fixed(prices, period=14):
    if len(prices) < period+1: return 50
    deltas = [prices[i]-prices[i-1] for i in range(1, len(prices))]
    gains = [d if d>0 else 0 for d in deltas[-period:]]
    losses = [-d if d<0 else 0 for d in deltas[-period:]]
    ag = sum(gains)/period or 0.01; al = sum(losses)/period or 0.01
    return 100 - (100/(1+ag/al if al!=0 else 1))

async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=10) as r:
            if r.status==200: return await r.json()
    except: pass
    return None

async def fetch_og_image(session, url):
    try:
        async with session.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0"}) as r:
            if r.status!=200: return ""
            html = await r.text()
            m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if not m: m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)
            if m:
                img=m.group(1)
                if img.startswith("//"): img="https:"+img
                if any(x in img.lower() for x in ["logo","icon","avatar","sprite"]): return ""
                if img.startswith("http"): return img
    except: pass
    return ""

def generate_news_image(title, source="Crypto"):
    if not HAS_PIL:
        return None
    W,H = 800,450
    img = Image.new('RGB', (W,H), color=(13, 17, 33))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        draw.line([(0,y),(W,y)], fill=(13+int(y*0.15), 17+int(y*0.12), 33+int(y*0.25)))
    draw.rectangle([0,0,W,80], fill=(26,34,66))
    draw.text((25,20), f"{source} | {datetime.now().strftime('%d.%m')}", fill=(120,180,255))
    wrapped = textwrap.wrap(title, width=32)
    y = 120
    for line in wrapped[:4]:
        draw.text((25,y), line, fill=(255,255,255))
        y+=55
    draw.text((25, H-40), "#Крипто Навигатор", fill=(100,100,120))
    draw.ellipse([600,-50,850,200], fill=(255,153,0))
    draw.text((670,60), "B", fill=(0,0,0))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=88)
    buf.seek(0)
    return buf.read()

async def download_image_bytes(session, url):
    try:
        async with session.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0","Referer":"https://cointelegraph.com/"}) as r:
            if r.status==200:
                data = await r.read()
                if len(data) > 8000:
                    return data
    except: pass
    return None

async def get_analysis(symbol="btc"):
    sym=symbol.upper()
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as s:
        price_usd=0; change=0
        data=await fetch_json(s,f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={sym}USDT")
        if data and 'lastPrice' in data: price_usd=float(data['lastPrice']); change=float(data['priceChangePercent'])
        if price_usd==0: price_usd={"BTC":80991,"ETH":2375,"SOL":145,"TON":5.2}.get(sym,100); change=-2.9
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
        fg_val,fg_text=53,"Нейтрально"
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

async def price_alert_loop():
    await asyncio.sleep(10)
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as session:
        while True:
            try:
                for sym in WATCH_LIST:
                    data=await fetch_json(session, f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={sym}USDT")
                    if not data or 'lastPrice' not in data: continue
                    price=float(data['lastPrice']); now=time.time()
                    if sym not in PRICE_HISTORY: PRICE_HISTORY[sym]=[]
                    PRICE_HISTORY[sym].append((now,price))
                    PRICE_HISTORY[sym]=[(t,p) for t,p in PRICE_HISTORY[sym] if now-t<=3600]
                    if len(PRICE_HISTORY[sym])<2: continue
                    price_5m=next((p for t,p in reversed(PRICE_HISTORY[sym]) if now-t>=300),None)
                    price_1h=PRICE_HISTORY[sym][0][1]
                    if not price_5m: continue
                    change_5m=(price-price_5m)/price_5m*100; change_1h=(price-price_1h)/price_1h*100
                    should=None
                    if abs(change_5m)>=2.5: should=f"⚡️ <b>{sym} ПАМП</b>" if change_5m>0 else f"⚡️ <b>{sym} ДАМП</b>"
                    elif abs(change_1h)>=4.0: should=f"🚨 <b>{sym} ВЗЛЕТ +{change_1h:.1f}%</b>" if change_1h>0 else f"🚨 <b>{sym} ОБВАЛ {change_1h:.1f}%</b>"
                    if should:
                        if sym in LAST_ALERT and now-LAST_ALERT[sym]<ALERT_COOLDOWN: continue
                        LAST_ALERT[sym]=now
                        me=await bot.get_me()
                        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"📊 Разбор {sym}", url=f"https://t.me/{me.username}?start={sym}")],[InlineKeyboardButton(text="💬 Обсудить в чате", url=CHAT_INVITE_LINK)]])
                        txt=f"""{should} | {datetime.now(MOSCOW_TZ).strftime('%H:%M МСК')}\n\n💰 Сейчас: ${price:,.4f}\n📈 5 мин: {change_5m:+.2f}%\n📈 1 час: {change_1h:+.2f}%\n\nЧто делать? Жми разбор 👇\n#{sym} #alert"""
                        try: await bot.send_message(chat_id=int(REPORT_CHAT_ID), text=txt, parse_mode="HTML", reply_markup=kb)
                        except: pass
                await asyncio.sleep(60)
            except: await asyncio.sleep(60)

async def get_top5_news():
    backup_news = [
        {"title":"BTC удержался выше $80k, киты продолжают покупать","url":"https://cointelegraph.com","source":"BTC"},
        {"title":"TON обновил рекорд по транзакциям, сеть растет","url":"https://ton.org","source":"TON"},
        {"title":"ETF на Bitcoin зафиксировали рекордный приток","url":"https://www.coindesk.com","source":"ETF"},
        {"title":"FED намекнул на снижение ставки в декабре","url":"https://cointelegraph.com","source":"FED"},
        {"title":"Киты перевели 1 млрд USDT на биржи","url":"https://cryptopanic.com","source":"Whales"},
    ]
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as s:
        data=await fetch_json(s,"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&feeds=cryptocompare,cointelegraph,coindesk&extraParams=CryptoRadar300")
        raw=[]; seen=set()
        if data and data.get('Data'):
            for n in data['Data'][:20]:
                title=n['title'].strip()
                if len(title)<20: continue
                key=title[:40].lower()
                if key in seen: continue
                seen.add(key)
                raw.append({"title":title,"url":n['url'],"source":n.get('categories','').split('|')[0] if n.get('categories') else 'Crypto'})
                if len(raw)>=5: break
        if not raw: raw = backup_news
        final=[]; seen_final=set()
        for n in raw+backup_news:
            k=n["title"][:40].lower()
            if k in seen_final: continue
            seen_final.add(k)
            final.append(n)
            if len(final)>=5: break
        return final[:5]

async def build_digest(is_morning=True):
    results={}
    for sym in ["BTC","ETH","TON","SOL"]:
        results[sym]=await get_analysis(sym)
        await asyncio.sleep(0.2)
    top5=await get_top5_news()
    date=datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y")
    if is_morning:
        news_block="".join([f'{i}. <a href="{n["url"]}">{n["title"][:85]}</a>\n' for i,n in enumerate(top5,1)])
        text=f"""☀️ <b>УТРЕННИЙ ДАЙДЖЕСТ | {date}</b> #ton\n💰 Рынок: BTC ${results['BTC']['price']:,.0f} ({results['BTC']['change']:+.1f}%) | TON ${results['TON']['price']:.2f}\n🧠 Страх: {results['BTC']['fg_val']} ({results['BTC']['fg_text']})\n🔥 <b>ТОП-5 главных:</b>\n{news_block}\n⚡️ Вывод: {results['TON']['conclusion']}\nНапиши тикер в чате для разбора 👇\n#утро #BTC #TON\n"""
    else:
        news_block="".join([f'{i}. <a href="{n["url"]}">{n["title"][:80]}</a> [{n["source"]}]\n' for i,n in enumerate(top5,1)])
        text=f"""🌙 <b>ВЕЧЕРНИЙ ИТОГ | {date}</b>\nЗа день: BTC {results['BTC']['change']:+.1f}% | ETH {results['ETH']['change']:+.1f}% | TON {results['TON']['change']:+.1f}%\nИндекс страха: {results['BTC']['fg_val']}\n📌 <b>Что случилось сегодня:</b>\n{news_block}\nЗавтра в 7:00 утренний дайджест.\n#вечер #TON\n"""
    return text, top5, results

# === 唯一修改的地方：只发1张图，不发相册 ===
async def send_digest(is_morning=True):
    try:
        me=await bot.get_me()
        keyboard=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Разобрать монету", url=f"https://t.me/{me.username}?start=analyze")],
            [InlineKeyboardButton(text="💬 Перейти в чат", url=CHAT_INVITE_LINK)]
        ])
        text, top5, results = await build_digest(is_morning)
        cover_bytes = None

        async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as sess:
            n = top5[0] if top5 else None
            if n and n.get("url"):
                og_url = await fetch_og_image(sess, n["url"])
                if og_url:
                    cover_bytes = await download_image_bytes(sess, og_url)
            if not cover_bytes and HAS_PIL and n:
                cover_bytes = generate_news_image(n["title"], n.get("source","Crypto"))

        if cover_bytes:
            photo = BufferedInputFile(cover_bytes, filename="cover.jpg")
            await bot.send_photo(chat_id=int(REPORT_CHAT_ID), photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard)
            print(f"✅ {'MORNING' if is_morning else 'EVENING'} SINGLE IMAGE SENT")
            return

        await bot.send_message(chat_id=int(REPORT_CHAT_ID), text=text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    except Exception as e:
        print(f"❌ DIGEST FAILED: {e}")

async def scheduler_loop():
    print("Scheduler 07:00 and 19:00 MSK SINGLE IMAGE")
    while True:
        try:
            now_msk=datetime.now(MOSCOW_TZ)
            if now_msk.hour==7 and 0 <= now_msk.minute < 2:
                if LAST_REPORTS["morning"]!=now_msk.date():
                    await send_digest(True); LAST_REPORTS["morning"]=now_msk.date()
            if now_msk.hour==19 and 0 <= now_msk.minute < 2:
                if LAST_REPORTS["evening"]!=now_msk.date():
                    await send_digest(False); LAST_REPORTS["evening"]=now_msk.date()
            await asyncio.sleep(30)
        except Exception as e:
            print(f"Scheduler error: {e}"); await asyncio.sleep(60)

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
        key=(m.chat.id, sym.lower()); now=time.time()
        if key in CACHE:
            ts,fid=CACHE[key]
            if now-ts<CACHE_TTL:
                remain=int(CACHE_TTL-(now-ts))
                warn=await m.answer(f"⚠️ {sym.upper()} уже был 5 мин назад. Смотри выше 👆 (еще {remain//60}м {remain%60}с)", reply_to_message_id=fid)
                asyncio.create_task(delete_after(warn,30)); asyncio.create_task(delete_after(m,30)); return
        a=await get_analysis(sym); text=format_text(sym,a)
        sent=await m.answer(text,parse_mode="HTML",disable_web_page_preview=True)
        CACHE[key]=(now, sent.message_id)
    except Exception as e: print(e)

@dp.message(Command("start"))
async def start(m:Message): await m.answer("Привет! Напиши тикер любой монеты: BTC, ETH, TON, SOL, DOGE...")
@dp.message(Command("report"))
async def manual_report(m:Message):
    await m.answer("Отправляю дайджест...")
    await send_digest(False)
@dp.message(F.text)
async def private_msg(m:Message): await handle_any(m)
@dp.channel_post(F.text)
async def channel_msg(m:Message): await handle_any(m)

async def main():
    asyncio.create_task(scheduler_loop()); asyncio.create_task(price_alert_loop())
    await dp.start_polling(bot)

app=Flask(__name__)
@app.route('/')
def home(): return 'ok v31 single image 07:00 19:00'
def run_flask():
    port=int(os.environ.get("PORT",10000)); app.run(host='0.0.0.0',port=port)
if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    asyncio.run(main())
    
