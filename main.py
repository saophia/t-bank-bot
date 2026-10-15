import os
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from flask import Flask
import threading

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN 没设置!")
bot = Bot(token=TOKEN)
dp = Dispatcher()

COINS = ["btc","eth","usdt","bnb","sol","xrp","doge","ada","trx","ton","avax","shib","dot","link","bch","near","ltc","matic","uni","etc","pepe","icp","apt","fil","arb","atom","wif","rndr","sui","xmr","xlm","hbar","vet","op","grt","stx","ldo","inj","imx","aave","ftm","algo","sand","mana","axs","eos","xtz","theta","neo","bonk","floki","wld","tia","ar","mkr","jup","sei","kas","strk","pyth","ron","w"]

async def get_price_single(session, sym):
    sym_up = sym.upper()
    if sym_up == "USDT":
        # USDT-RUB 从 OKX 拿
        try:
            async with session.get("https://www.okx.com/api/v5/market/ticker?instId=USDT-RUB", timeout=8) as r:
                if r.status == 200:
                    j = await r.json()
                    if j.get("data"):
                        return float(j["data"][0]["last"])
        except:
            pass
        return 83.5

    # 1. 尝试 Binance 备用域名 (俄罗斯可访问)
    try:
        url = f"https://data-api.binance.vision/api/v3/ticker/price?symbol={sym_up}USDT"
        async with session.get(url, timeout=6) as r:
            if r.status == 200:
                j = await r.json()
                return float(j["price"])
    except:
        pass

    # 2. 尝试 Bybit
    try:
        url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={sym_up}USDT"
        async with session.get(url, timeout=6) as r:
            if r.status == 200:
                j = await r.json()
                lst = j.get("result", {}).get("list", [])
                if lst:
                    return float(lst[0]["lastPrice"])
    except:
        pass

    # 3. 尝试 OKX
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={sym_up}-USDT"
        async with session.get(url, timeout=6) as r:
            if r.status == 200:
                j = await r.json()
                if j.get("data"):
                    return float(j["data"][0]["last"])
    except:
        pass
    return None

async def get_all_prices(symbols):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        # 先拿USDT/RUB
        usdt_rub = await get_price_single(session, "usdt")

        tasks = [get_price_single(session, s) for s in symbols if s!= "usdt"]
        results = await asyncio.gather(*tasks)

        prices = {}
        prices["usdt"] = usdt_rub
        idx = 0
        for s in symbols:
            if s == "usdt":
                continue
            if idx < len(results) and results[idx]:
                # USDT价格 * RUB汇率
                prices[s] = results[idx] * usdt_rub
            idx += 1
        return prices, usdt_rub

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("✅ T-Bank Bot V4 已启动!\n\n/price - 热门20\n/price btc eth sol")

@dp.message(Command("price"))
async def price(m: Message):
    parts = m.text.lower().split()[1:]
    if not parts:
        parts = COINS[:20]

    prices, usdt_rub = await get_all_prices(parts[:20])

    if not prices or len(prices) <= 1:
        await m.answer(f"接口还在同步，USDT/RUB={usdt_rub} 5秒后重试")
        return

    text = f"💰 实时 (RUB) USDT≈{usdt_rub:.2f}₽\n\n"
    for sym in parts[:20]:
        p = prices.get(sym)
        if p:
            text += f"{sym.upper()}: {p:,.2f} ₽\n"

    await m.answer(text)

async def main():
    await dp.start_polling(bot)

app = Flask(__name__)
@app.route('/')
def home(): return 'ok v4'
def run_flask(): app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
