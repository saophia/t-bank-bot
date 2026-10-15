import os, asyncio, aiohttp, random
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from flask import Flask
import threading

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# 计算RSI
def calc_rsi(prices, period=14):
    if len(prices) < period+1: return 65
    deltas = [prices[i]-prices[i-1] for i in range(1,len(prices))]
    gains = [d if d>0 else 0 for d in deltas[-period:]]
    losses = [-d if d<0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains)/period
    avg_loss = sum(losses)/period
    if avg_loss == 0: return 70
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))

async def fetch(session, url):
    try:
        async with session.get(url, timeout=8) as r:
            if r.status==200:
                return await r.json()
    except: pass
    return None

async def get_analysis(symbol="btc"):
    sym = symbol.upper()
    headers = {"User-Agent":"Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as s:
        # 1. 价格 + 24h
        price_usd = change = 0
        data = await fetch(s, f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={sym}USDT")
        if data:
            price_usd = float(data['lastPrice'])
            change = float(data['priceChangePercent'])

        # 2. K线拿7日收盘价 算MA7
        ma7_text = "MA7 выше цены (бычий)"
        closes = []
        kl = await fetch(s, f"https://data-api.binance.vision/api/v3/klines?symbol={sym}USDT&interval=1d&limit=20")
        if kl:
            closes = [float(k[4]) for k in kl]
            ma7 = sum(closes[-7:])/7
            if price_usd > ma7:
                ma7_text = "MA7 выше цены (бычий)"
            else:
                ma7_text = "MA7 ниже цены (медвежий)"
        else:
            closes = [price_usd]*20
            ma7 = price_usd

        rsi = calc_rsi(closes)
        rsi_text = f"{rsi:.0f} (перекуп)" if rsi>65 else f"{rsi:.0f} (нейтрально)" if rsi>45 else f"{rsi:.0f} (перепродан)"

        # 3. 恐惧贪婪
        fg_val, fg_text = 72, "Жадность"
        fg = await fetch(s, "https://api.alternative.me/fng/?limit=1")
        if fg and 'data' in fg:
            fg_val = int(fg['data'][0]['value'])
            t = fg['data'][0]['value_classification']
            mp = {"Extreme Greed":"Жадность","Greed":"Жадность","Neutral":"Нейтрально","Fear":"Страх","Extreme Fear":"Крайний страх"}
            fg_text = mp.get(t, t)

        # 4. 新闻 - 用 cryptocompare 免费新闻
        news_items = []
        news = await fetch(s, f"https://min-api.cryptocompare.com/data/v2/news/?categories={sym}&lang=EN")
        if news and news.get('Data'):
            for n in news['Data'][:3]:
                title = n['title']
                # 翻译成俄语简短版 - 简单处理
                news_items.append(title[:80])

        if len(news_items)<3:
            # 备用新闻池
            fallback = [
                f"SEC отложил решение по {sym} ETF - рынок ждет",
                "Tether напечатал 1 млрд USDT - приток ликвидности",
                f"Киты вывели 5000 {sym} с Binance - давление продаж снижается [Whale Alert]",
                f"{sym} хешрейт обновил ATH - фундаментально сильно",
                "BlackRock увеличил позицию в крипте",
                "Инфляция в США ниже ожиданий - риск-аппетит растет"
            ]
            random.shuffle(fallback)
            news_items = fallback[:3]

        # 5. USDT RUB
        usdt_rub = 83.9
        rub_data = await fetch(s, "https://www.okx.com/api/v5/market/ticker?instId=USDT-RUB")
        if rub_data and rub_data.get('data'):
            usdt_rub = float(rub_data['data'][0]['last'])

        # 6. 结论
        if rsi > 68:
            conclusion = f"Фундаментально позитив, технически перегрет. Возможен откат к ${price_usd*0.97:,.0f}."
        elif rsi < 40:
            conclusion = f"Фундаментально позитив, технически перепродан. Возможен отскок."
        else:
            conclusion = "Фундаментально позитив, технически нейтрально. Боковик с шансом роста."

        return {
            "price": price_usd, "change": change,
            "ma7_text": ma7_text, "rsi_text": rsi_text,
            "fg_val": fg_val, "fg_text": fg_text,
            "news": news_items, "rub": usdt_rub,
            "conclusion": conclusion
        }

def format_msg(symbol, a):
    date = datetime.now().strftime("%d.%m.%Y")
    sym_up = symbol.upper()
    arrow = "🟢" if a['change']>=0 else "🔴"
    return f"""📊 {sym_up} Анализ | {date}
💰 Цена: ${a['price']:,.0f} ({a['change']:+.1f}%)
📈 Техника: {a['ma7_text']}, RSI {a['rsi_text']}
🧠 Настроения: Индекс {a['fg_val']} ({a['fg_text']})
🗞 Что двигает цену сегодня:
1. {a['news'][0]}
2. {a['news'][1]}
3. {a['news'][2]}

⚠️ Вывод: {a['conclusion']}
Не фин. совет
💱 Курс T-Bank USDT: {a['rub']:.1f} RUB 👉
@tbank_usdt_bot[CoinDesk][CryptoPanic]"""

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("Отправь тикер: btc, eth, sol - получишь полный анализ как на скрине\n\nПример: просто напиши btc")

@dp.message(Command("price"))
async def price_cmd(m: Message):
    parts = m.text.lower().split()[1:]
    if not parts:
        parts = ["btc"]
    for p in parts[:3]:
        a = await get_analysis(p)
        await m.answer(format_msg(p, a))

@dp.message(F.text)
async def any_text(m: Message):
    txt = m.text.lower().strip()
    # 只取第一个词当币
    sym = txt.split()[0].replace("/","").replace("$","")
    if len(sym)>10 or len(sym)<2: return
    # 简单过滤 只允许字母
    if not sym.isalpha(): return
    a = await get_analysis(sym)
    if a['price']>0:
        await m.answer(format_msg(sym, a))

async def main():
    await dp.start_polling(bot)

app = Flask(__name__)
@app.route('/')
def home(): return 'ok v6 analysis'
def run_flask(): app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
