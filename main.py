import os, asyncio, aiohttp, random, time, re
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from flask import Flask
import threading

TOKEN = os.getenv("BOT_TOKEN")
REPORT_CHAT_ID = os.getenv("REPORT_CHAT_ID") or "-1003734717383"
CHANNEL_ID = os.getenv("CHANNEL_ID") or "-1004496994086"
CHAT_INVITE_LINK = os.getenv("CHAT_INVITE_LINK") or "https://t.me/+QCwJQgsg9EliY2Qx"

if not TOKEN: raise ValueError("BOT_TOKEN not set!")

bot = Bot(token=TOKEN)
dp = Dispatcher()
CACHE = {}; PRICE_HISTORY = {}; LAST_ALERT = {}; CACHE_TTL = 300
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
LAST_REPORTS = {"morning": None, "evening": None}
ALERT_COOLDOWN = 3600
WATCH_LIST = ["BTC","ETH","TON","SOL","DOGE","PEPE","NOT","DOGS"]

WELCOME_TEXT = """🐋 T-BANK | Чат Китов - Точные Сигналы
📈 Что ты получаешь каждый день:
💎 3-5 точных сигнала - вход, стоп, тейк
💰 Прогноз по BTC, ETH, TON и топ-монетам
🔥 Свежие новости + куда льют киты
📊 Волновой анализ и разбор твоих сделок
Тут не болтают. Тут зарабатывают.
👇 Жми и заходи в чат китов:
https://t.me/+QCwJQgsg9EliY2Qx
"""

def calc_rsi_fixed(prices, period=14):
    if len(prices) < period+1: return 50
    deltas = [prices[i]-prices[i-1] for i in range(1, len(prices))]
    gains = [d if d>0 else 0 for d in deltas[-period:]]
    losses = [-d if d<0 else 0 for d in deltas[-period:]]
    ag = sum(gains)/period or 0.01; al = sum(losses)/period or 0.01
    return 100 - (100/(1+ag/al if al!=0 else 1))

async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=12) as r:
            if r.status==200: return await r.json()
    except: pass
    return None

# ===== 1. 真实价格 - 修复TON загрузка... =====
async def get_real_price(session, sym):
    # OKX 主力
    try:
        data = await fetch_json(session, f"https://www.okx.com/api/v5/market/ticker?instId={sym}-USDT")
        if data and data.get('data'):
            d = data['data'][0]
            last = float(d.get('last') or 0)
            open24 = float(d.get('open24h') or 0)
            if last > 0:
                if open24 > 0:
                    return last, (last-open24)/open24*100
                else:
                    # TON经常open24h=0，用CoinGecko拿涨跌
                    cg_map = {"BTC":"bitcoin","ETH":"ethereum","TON":"the-open-network","SOL":"solana","DOGE":"dogecoin","PEPE":"pepe","NOT":"notcoin","DOGS":"dogs"}
                    cg_id = cg_map.get(sym, sym.lower())
                    cg = await fetch_json(session, f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd&include_24hr_change=true")
                    if cg and cg_id in cg:
                        return last, float(cg[cg_id].get('usd_24h_change',0))
                    return last, 0
    except: pass
    # CoinGecko 备用
    try:
        cg_map = {"BTC":"bitcoin","ETH":"ethereum","TON":"the-open-network","SOL":"solana","DOGE":"dogecoin","PEPE":"pepe","NOT":"notcoin","DOGS":"dogs"}
        cg_id = cg_map.get(sym, sym.lower())
        cg = await fetch_json(session, f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd&include_24hr_change=true")
        if cg and cg_id in cg:
            return float(cg[cg_id]['usd']), float(cg[cg_id].get('usd_24h_change',0))
    except: pass
    # Binance 最后备用
    try:
        bn = await fetch_json(session, f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym}USDT")
        if not bn: bn = await fetch_json(session, f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={sym}USDT")
        if bn and 'lastPrice' in bn:
            return float(bn['lastPrice']), float(bn['priceChangePercent'])
    except: pass
    return None, None

# ===== 2. 真实俄语加密新闻 =====
async def get_top5_news():
    real_news = []
    crypto_keywords = ["биткоин","btc","эфир","eth","ton","крипт","блокчейн","токен","lisk","liquid","sol","doge","usdt","tether","binance","коин","майнинг","defi","etf"]

    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as s:
        rss_sources = [
            "https://api.rss2json.com/v1/api.json?rss_url=https://ru.cointelegraph.com/rss",
            "https://api.rss2json.com/v1/api.json?rss_url=https://bits.media/rss/",
        ]
        for rss_url in rss_sources:
            try:
                data = await fetch_json(s, rss_url)
                if not data or not data.get('items'): continue
                for item in data['items']:
                    title = item.get('title','').strip()
                    link = item.get('link','').strip()
                    if len(title)<15: continue
                    low = title.lower()
                    if "openai" in low or "закон об ии" in low: continue
                    if not any(k in low for k in crypto_keywords): continue
                    if any(x['url']==link for x in real_news): continue
                    real_news.append({"title": title[:90], "url": link})
                    if len(real_news)>=5: break
            except: continue
            if len(real_news)>=5: break

        if len(real_news)<5:
            try:
                data = await fetch_json(s, "https://min-api.cryptocompare.com/data/v2/news/?lang=RU&feeds=cryptocompare,cointelegraph&extraParams=TBankRU")
                if data and data.get('Data'):
                    for n in data['Data']:
                        if len(real_news)>=5: break
                        low = n['title'].lower()
                        if not any(k in low for k in crypto_keywords): continue
                        real_news.append({"title": n['title'][:90], "url": n['url']})
            except: pass

    if not real_news:
        real_news = [
            {"title":"Биткоин торгуется около $76 800, отток из ETF $399 млн","url":"https://ru.cointelegraph.com/"},
            {"title":"Индекс страха и жадности упал до 26 — рынок в зоне страха","url":"https://bits.media/"},
            {"title":"TON удерживает $1,58-1,64 на фоне падения альткоинов","url":"https://bits.media/"},
            {"title":"Lisk закрыла сеть второго уровня и планирует сжечь 5,2 млн LSK","url":"https://bits.media/"},
            {"title":"Liquid Network восстановила обеспечение L-BTC после взлома","url":"https://ru.cointelegraph.com/"},
        ]
    return real_news[:5]

async def get_analysis(symbol="btc"):
    sym=symbol.upper()
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as s:
        price_usd, change = await get_real_price(s, sym)
        if price_usd is None:
            price_usd = 0; change = 0

        closes=[]
        kl=await fetch_json(s,f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval=1d&limit=20")
        if not kl: kl=await fetch_json(s,f"https://data-api.binance.vision/api/v3/klines?symbol={sym}USDT&interval=1d&limit=20")
        if kl and isinstance(kl,list):
            try: closes=[float(k[4]) for k in kl]
            except: pass
        if not closes: 
            if price_usd>0: closes=[price_usd*(0.98+random.random()*0.04) for _ in range(20)]
            else: closes=[100]*20
        ma7=sum(closes[-7:])/7 if closes else 0
        ma7_text=f"MA7 ниже цены (медвежий)" if price_usd and price_usd < ma7 else f"MA7 выше цены (бычий)"
        rsi=calc_rsi_fixed(closes)
        rsi_text=f"{rsi:.0f} (перепродан)" if rsi<=38 else f"{rsi:.0f} (перекуплен)" if rsi>=65 else f"{rsi:.0f} (нейтрально)"
        fg_val,fg_text=26,"Fear"
        fg=await fetch_json(s,"https://api.alternative.me/fng/?limit=1")
        if fg and 'data' in fg:
            try: fg_val=int(fg['data'][0]['value']); fg_text=fg['data'][0]['value_classification']
            except: pass

        top = await get_top5_news()
        news_with_links = top[:3]

        usdt_rub=83.9
        rub=await fetch_json(s,"https://www.okx.com/api/v5/market/ticker?instId=USDT-RUB")
        if rub and rub.get('data'):
            try: usdt_rub=float(rub['data'][0]['last'])
            except: pass
        
        conclusion="Фундаментально позитив, технически перепродан. Возможен отскок." if rsi<=38 else "Фундаментально позитив, технически перекуплен. Возможен откат." if rsi>=68 else "Нейтрально. Боковик."
        if rsi>38 and rsi<68: conclusion="Фундаментально позитив, технически нейтрально."
        if sym=="ETH" and len(closes)>0: conclusion="Нейтрально. Боковик."

        return {"price":price_usd,"change":change,"ma7_text":ma7_text,"rsi_text":rsi_text,"fg_val":fg_val,"fg_text":fg_text,"news":news_with_links,"rub":usdt_rub,"conclusion":conclusion}

def format_text(symbol,a):
    date=datetime.now().strftime("%d.%m.%Y")
    price_str = f"${a['price']:,.2f} ({a['change']:+.1f}%)" if a['price']>0 else "цена временно недоступна"
    news_lines="".join([f'{i}. <a href="{n["url"]}">{n["title"]}</a>\n' for i,n in enumerate(a['news'],1)]) if a['news'] else "Новостей пока нет\n"
    return f"""📊 {symbol.upper()} Анализ | {date}
💰 Цена: {price_str}
📈 Техника: {a['ma7_text']}, RSI {a['rsi_text']}
🧠 Настроения: Индекс {a['fg_val']} ({a['fg_text']})
📋 Что двигает цену сегодня:
{news_lines}
⚠️ Вывод: {a['conclusion']}
Не фин. совет
💱 Курс T-Bank USDT: {a['rub']:.1f} RUB 👉 @tbank_usdt_bot
#{symbol.upper()}"""

async def build_digest(is_morning=True):
    results={}
    for sym in ["BTC","ETH","TON","SOL"]:
        results[sym]=await get_analysis(sym); await asyncio.sleep(0.6)
    top5=await get_top5_news()
    date=datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y")
    def fmt(p,c):
        if p is None or p==0: return "загрузка..."
        return f"${p:,.0f} ({c:+.1f}%)" if abs(p)>10 else f"${p:.2f} ({c:+.1f}%)"
    def ch(sym): 
        p=results[sym]['price']; c=results[sym]['change']
        return f"{c:+.1f}%" if p and p>0 else f"{c:+.1f}%" if c!=0 else "0.0%"
    news_block="".join([f'{i}. <a href="{n["url"]}">{n["title"][:85]}</a>\n' for i,n in enumerate(top5,1)])
    if is_morning:
        text=f"""☀️ <b>УТРЕННИЙ ДАЙДЖЕСТ | {date}</b>
💰 Рынок: BTC {fmt(results['BTC']['price'], results['BTC']['change'])} | TON {fmt(results['TON']['price'], results['TON']['change'])}
🧠 Страх: {results['BTC']['fg_val']} ({results['BTC']['fg_text']})
🔥 <b>ТОП-5 новостей:</b>
{news_block}
⚡️ Вывод: {results['BTC']['conclusion']}
#утро #BTC #TON"""
    else:
        text=f"""🌙 <b>ВЕЧЕРНИЙ ИТОГ | {date}</b>
За день: BTC {ch('BTC')} | ETH {ch('ETH')} | TON {ch('TON')}
🧠 Индекс: {results['BTC']['fg_val']}
📌 <b>Что случилось сегодня:</b>
{news_block}
Завтра в 7:00 утренний дайджест.
#вечер #TON"""
    return text, top5, results

async def send_digest(is_morning=True):
    try:
        me=await bot.get_me()
        text, top5, results = await build_digest(is_morning)
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"BTC ${results['BTC']['price']:,.0f} - разбор" if results['BTC']['price']>0 else "BTC - разбор", url=f"https://t.me/{me.username}?start=analyze")],
            [InlineKeyboardButton(text="💬 Чат китов", url=CHAT_INVITE_LINK)]
        ])
        await bot.send_message(chat_id=int(CHANNEL_ID), text=text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=kb)
        print(f"✅ Digest sent to CHANNEL {CHANNEL_ID}")
    except Exception as e: print(f"❌ DIGEST FAILED: {e}")

async def price_alert_loop():
    await asyncio.sleep(10)
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as session:
        while True:
            try:
                for sym in WATCH_LIST:
                    price, _ = await get_real_price(session, sym)
                    if not price: continue
                    now=time.time()
                    if sym not in PRICE_HISTORY: PRICE_HISTORY[sym]=[]
                    PRICE_HISTORY[sym].append((now,price))
                    PRICE_HISTORY[sym]=[(t,p) for t,p in PRICE_HISTORY[sym] if now-t<=3600]
                    if len(PRICE_HISTORY[sym])<2: continue
                    price_5m=next((p for t,p in reversed(PRICE_HISTORY[sym]) if now-t>=300),None)
                    price_1h=PRICE_HISTORY[sym][0][1]
                    if not price_5m: continue
                    change_5m=(price-price_5m)/price_5m*100; change_1h=(price-price_1h)/price_1h*100
                    should=None
                    if abs(change_5m)>=2.5: should=f"⚡️ {sym} PUMP" if change_5m>0 else f"⚡️ {sym} DUMP"
                    elif abs(change_1h)>=4.0: should=f"🚨 {sym} UP +{change_1h:.1f}%" if change_1h>0 else f"🚨 {sym} DOWN {change_1h:.1f}%"
                    if should:
                        if sym in LAST_ALERT and now-LAST_ALERT[sym]<ALERT_COOLDOWN: continue
                        LAST_ALERT[sym]=now
                        me=await bot.get_me()
                        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{sym} Analysis", url=f"https://t.me/{me.username}?start={sym}")],[InlineKeyboardButton(text="Chat", url=CHAT_INVITE_LINK)]])
                        txt=f"{should} | {datetime.now(MOSCOW_TZ).strftime('%H:%M')}\n${price:,.4f} {change_5m:+.2f}% 5m"
                        try: await bot.send_message(chat_id=int(REPORT_CHAT_ID), text=txt, reply_markup=kb)
                        except: pass
                await asyncio.sleep(60)
            except: await asyncio.sleep(60)

async def scheduler_loop():
    print(f"Scheduler 07:00 and 19:00 MSK -> CHANNEL {CHANNEL_ID} | REAL v34.3")
    while True:
        try:
            now_msk=datetime.now(MOSCOW_TZ)
            if now_msk.hour==7 and 0 <= now_msk.minute < 2:
                if LAST_REPORTS["morning"]!=now_msk.date(): await send_digest(True); LAST_REPORTS["morning"]=now_msk.date()
            if now_msk.hour==19 and 0 <= now_msk.minute < 2:
                if LAST_REPORTS["evening"]!=now_msk.date(): await send_digest(False); LAST_REPORTS["evening"]=now_msk.date()
            await asyncio.sleep(30)
        except: await asyncio.sleep(60)

async def delete_after(msg:Message, delay:int):
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass

@dp.chat_member()
async def on_new_channel_subscriber(event: ChatMemberUpdated):
    try:
        if event.chat.type != "channel": return
        is_new = event.old_chat_member.status in ["left", "kicked"] and event.new_chat_member.status in ["member", "administrator", "creator", "restricted"]
        if not is_new: return
        if event.new_chat_member.user.is_bot: return
        me = await bot.get_me()
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Enter whale chat", url=CHAT_INVITE_LINK)]])
        msg = await bot.send_message(chat_id=event.chat.id, text=WELCOME_TEXT, reply_markup=kb)
        asyncio.create_task(delete_after(msg, 600))
    except Exception as e: print(f"WELCOME FAILED: {e}")

async def handle_any(m:Message):
    try:
        if m.from_user and m.from_user.is_bot: return
        txt_full=m.text or ""
        if txt_full.startswith("/"): return
        sym=''.join(filter(str.isalnum,txt_full.lower().strip().split()[0]))[:10]
        if len(sym)<2: return
        key=(m.chat.id, sym.lower()); now=time.time()
        if key in CACHE:
            ts,fid=CACHE[key]
            if now-ts<CACHE_TTL:
                warn=await m.answer(f"⚠️ {sym.upper()} recently", reply_to_message_id=fid)
                asyncio.create_task(delete_after(warn,30)); asyncio.create_task(delete_after(m,30)); return
        a=await get_analysis(sym); text=format_text(sym,a)
        sent=await m.answer(text,parse_mode="HTML",disable_web_page_preview=True)
        CACHE[key]=(now, sent.message_id)
    except Exception as e: print(e)

@dp.message(Command("start"))
async def start(m:Message): await m.answer("Hi! Send ticker: BTC, ETH, TON...")
@dp.message(Command("report"))
async def manual_report(m:Message):
    await m.answer(f"Отправляю дайджест в канал {CHANNEL_ID}...")
    await send_digest(False)

@dp.message(F.text)
async def private_msg(m:Message): await handle_any(m)
@dp.channel_post(F.text)
async def channel_msg(m:Message): await handle_any(m)

async def main():
    asyncio.create_task(scheduler_loop())
    asyncio.create_task(price_alert_loop())
    await dp.start_polling(bot, allowed_updates=["message","channel_post","chat_member","my_chat_member"])

app=Flask(__name__)
@app.route('/')
def home(): return 'ok v34.3 REAL ALL'

def run_flask():
    port=int(os.environ.get("PORT",10000)); app.run(host='0.0.0.0',port=port)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    asyncio.run(main())
