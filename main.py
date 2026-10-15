import os, asyncio, aiohttp, random, time
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from flask import Flask
import threading

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set!")
bot = Bot(token=TOKEN)
dp = Dispatcher()

CACHE = {}
CACHE_TTL = 300

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
    sym = symbol.upper()
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as s:
        price_usd=0; change=0
        for url in [f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={sym}USDT"]:
            data=await fetch_json(s,url)
            if data and 'lastPrice' in data:
                price_usd=float(data['lastPrice']); change=float(data['priceChangePercent']); break
        if price_usd==0: price_usd={"BTC":80991,"ETH":2375,"SOL":145}.get(sym,100); change=-2.9
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
                news_with_links.append({"title":title,"url":n['url']})
        if len(news_with_links)<3:
            fallback=[{"title":f"{sym} хешрейт обновил ATH","url":f"https://cointelegraph.com/search?query={sym}"},{"title":"Инфляция в США ниже ожиданий","url":"https://www.coindesk.com/markets/"},{"title":"Tether напечатал 1 млрд USDT","url":"https://cryptopanic.com/"}]
            random.shuffle(fallback); news_with_links=(news_with_links+fallback)[:3]
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
💱 Курс T-Bank USDT: {a['rub']:.1f} RUB 👉 @tbank_usdt_bot"""

# 新增：30秒后删除
async def delete_after(msg: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except: pass

async def handle_any(m:Message):
    try:
        if m.from_user and m.from_user.is_bot:
            return
        txt_full = m.text or ""
        if "Анализ" in txt_full or "уже был" in txt_full or "Курс T-Bank" in txt_full:
            return
        txt=txt_full.lower().strip().split()[0]
        if not txt: return
        sym=''.join(filter(str.isalnum,txt))[:10]
        if len(sym)<2: return
        key = (m.chat.id, sym.lower())
        now = time.time()
        if key in CACHE:
            ts, first_msg_id = CACHE[key]
            if now - ts < CACHE_TTL:
                remain = int(CACHE_TTL - (now - ts))
                warn = await m.answer(
                    f"⚠️ {sym.upper()} уже был 5 мин назад. Смотри выше 👆 (еще {remain//60}м {remain%60}с)",
                    reply_to_message_id=first_msg_id
                )
                # 30秒后自动删除这条提示
                asyncio.create_task(delete_after(warn, 30))
                return
        a=await get_analysis(sym)
        text=format_text(sym,a)
        sent = await m.answer(text,parse_mode="HTML",disable_web_page_preview=True)
        CACHE[key] = (now, sent.message_id)
    except Exception as e: print(f"handle error: {e}")

@dp.message(Command("start"))
async def start(m:Message): await m.answer("Бот работает! Отправь btc/eth")

@dp.message(F.text)
async def private_msg(m:Message): await handle_any(m)
@dp.channel_post(F.text)
async def channel_msg(m:Message): await handle_any(m)

async def main(): await dp.start_polling(bot)

app=Flask(__name__)
@app.route('/')
def home(): return 'ok v13 delete after 30s'

def run_flask():
    port=int(os.environ.get("PORT",10000))
    app.run(host='0.0.0.0',port=port)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    asyncio.run(main())
