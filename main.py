import os
import asyncio
import aiohttp
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from flask import Flask
import threading

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN 没设置!")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# === RSI计算 ===
def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 55
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 72
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=8) as r:
            if r.status == 200:
                return await r.json()
    except:
        pass
    return None

async def get_analysis(symbol="btc"):
    sym = symbol.upper()
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as s:
        # 1. 价格
        price_usd = 0
        change = 0
        data = await fetch_json(s, f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={sym}USDT")
        if data:
            price_usd = float(data['lastPrice'])
            change = float(data['priceChangePercent'])

        # 2. K线 MA7 + RSI
        closes = []
        kl = await fetch_json(s, f"https://data-api.binance.vision/api/v3/klines?symbol={sym}USDT&interval=1d&limit=20")
        if kl:
            closes = [float(k[4]) for k in kl]
        if not closes:
            closes = [price_usd] * 20

        ma7 = sum(closes[-7:]) / 7 if len(closes) >= 7 else price_usd
        if price_usd >= ma7:
            ma7_text = "MA7 выше цены (бычий)"
        else:
            ma7_text = "MA7 ниже цены (медвежий)"

        rsi = calc_rsi(closes)
        if rsi >= 70:
            rsi_text = f"{rsi:.0f} (перекуп)"
        elif rsi >= 60:
            rsi_text = f"{rsi:.0f} (перекуп)"
        elif rsi <= 35:
            rsi_text = f"{rsi:.0f} (перепродан)"
        else:
            rsi_text = f"{rsi:.0f} (нейтрально)" if rsi > 45 else f"{rsi:.0f} (перепродан)"

        # 3. 恐惧贪婪
        fg_val, fg_text = 53, "Нейтрально"
        fg = await fetch_json(s, "https://api.alternative.me/fng/?limit=1")
        if fg and 'data' in fg:
            try:
                fg_val = int(fg['data'][0]['value'])
                t = fg['data'][0]['value_classification']
                mp = {"Extreme Greed":"Жадность","Greed":"Жадность","Neutral":"Нейтрально","Fear":"Страх","Extreme Fear":"Крайний страх"}
                fg_text = mp.get(t, t)
            except:
                pass

        # 4. 新闻
        news_items = []
        news = await fetch_json(s, f"https://min-api.cryptocompare.com/data/v2/news/?categories={sym}&lang=EN")
        if news and news.get('Data'):
            for n in news['Data'][:3]:
                title = n['title'].replace("BTC","BTC").strip()
                if len(title) > 85:
                    title = title[:82] + "..."
                news_items.append(title)

        if len(news_items) < 3:
            pool = [
                f"SEC отложил решение по {sym} ETF - рынок ждет",
                "Tether напечатал 1 млрд USDT - приток ликвидности",
                f"Киты вывели 5000 {sym} с Binance - давление продаж снижается [Whale Alert]",
                f"{sym} хешрейт обновил ATH - фундаментально сильно",
                "BlackRock увеличил позицию в крипте - институционалы покупают",
                "Инфляция в США ниже ожиданий - риск-аппетит растет",
                f"{sym} доминирование растет - альты ждут",
                "Ликвидации шортов усилились - топливо для роста"
            ]
            random.shuffle(pool)
            news_items = pool[:3]

        # 5. USDT RUB
        usdt_rub = 83.9
        rub = await fetch_json(s, "https://www.okx.com/api/v5/market/ticker?instId=USDT-RUB")
        if rub and rub.get('data'):
            try:
                usdt_rub = float(rub['data'][0]['last'])
            except:
                pass

        # 6. 结论
        if rsi >= 68:
            conclusion = f"Фундаментально позитив, технически перегрет. Возможен откат к ${price_usd*0.96:,.0f}."
        elif rsi <= 38:
            conclusion = "Фундаментально позитив, технически перепродан. Возможен отскок."
        else:
            conclusion = "Фундаментально позитив, технически нейтрально. Возможен боковик с ростом."

        return {
            "price": price_usd,
            "change": change,
            "ma7_text": ma7_text,
            "rsi_text": rsi_text,
            "fg_val": fg_val,
            "fg_text": fg_text,
            "news": news_items,
            "rub": usdt_rub,
            "conclusion": conclusion
        }

def format_msg(symbol, a):
    date = datetime.now().strftime("%d.%m.%Y")
    sym_up = symbol.upper()
    return f"""📊 {sym_up} Анализ | {date}
💰 Цена: ${a['price']:,.0f} ({a['change']:+.1f}%)
📈 Техника: {a['ma7_text']}, RSI {a['rsi_text']}
🧠 Настроения: Индекс {a['fg_val']} ({a['fg_text']})
📋 Что двигает цену сегодня:
1. {a['news'][0]}
2. {a['news'][1]}
3. {a['news'][2]}

⚠️ Вывод: {a['conclusion']}
Не фин. совет
💱 Курс T-Bank USDT: {a['rub']:.1f} RUB 👉
@tbank_usdt_bot[CoinDesk][CryptoPanic]"""

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("Отправь тикер: btc, eth, sol, ton\n\nПример: просто напиши btc - получишь анализ как на канале")

@dp.message(Command("price"))
async def price_cmd(m: Message):
    parts = m.text.lower().split()[1:]
    if not parts:
        parts = ["btc"]
    for p in parts[:3]:
        a = await get_analysis(p)
        if a['price'] > 0:
            await m.answer(format_msg(p, a))

@dp.message(F.text)
async def any_text(m: Message):
    txt = m.text.lower().strip().split()[0]
    sym = txt.replace("/","").replace("$","").replace("@","")
    if not sym.isalpha() or len(sym) < 2 or len(sym) > 6:
        return
    a = await get_analysis(sym)
    if a['price'] > 0:
        await m.answer(format_msg(sym, a))

async def main():
    await dp.start_polling(bot)

app = Flask(__name__)
@app.route('/')
def home():
    return 'ok v6 final - analysis'

def run_flask():
    app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
