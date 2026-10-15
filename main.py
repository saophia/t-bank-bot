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

COINS = ["btc","eth","usdt","bnb","sol","xrp","doge","ada","trx","ton","avax","shib","dot","link","bch","near","ltc","matic","uni","etc","pepe","icp","apt","fil","arb","atom","wif","rndr","sui","xmr","xlm","hbar","vet","op","grt","stx","ldo","inj","imx","aave","ftm","algo","sand","mana","axs","eos","xtz","theta","neo","bonk","floki","wld","tia","ar","mkr","jup","sei","kas","strk","pyth","ron","w","sui"]

# 获取 RUB 汇率 + 币价
async def get_binance_prices(symbols):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as s:
        # 1. 先拿 USDT/RUB 汇率
        usdt_rub = 83.54
        try:
            async with s.get("https://api.binance.com/api/v3/ticker/price?symbol=USDTRUB", timeout=10) as r:
                if r.status == 200:
                    j = await r.json()
                    usdt_rub = float(j['price'])
        except:
            try:
                async with s.get("https://api.binance.com/api/v3/ticker/price?symbol=USDTRUB", timeout=10) as r:
                    if r.status == 200:
                        j = await r.json()
                        usdt_rub = float(j['price'])
            except:
                pass # 用默认 83.54

        # 2. 批量拿 USDT 价格
        result = {}
        for sym in symbols:
            bin_sym = sym.upper() + "USDT"
            if sym == "usdt":
                result[sym] = usdt_rub
                continue
            try:
                async with s.get(f"https://api.binance.com/api/v3/ticker/price?symbol={bin_sym}", timeout=8) as r:
                    if r.status == 200:
                        j = await r.json()
                        usdt_price = float(j['price'])
                        result[sym] = usdt_price * usdt_rub
            except:
                continue
        return result, usdt_rub

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("✅ T-Bank Bot Binance版 已启动!\n\n/price - 热门20币 RUB实时价\n/price btc eth sol - 查多个\n/price doge ton - 任意币")

@dp.message(Command("price"))
async def price(m: Message):
    parts = m.text.lower().split()[1:]
    if not parts:
        parts = COINS[:20]

    prices, usdt_rub = await get_binance_prices(parts[:20])

    if not prices:
        await m.answer("Binance接口繁忙，5秒后再试")
        return

    text = f"💰 实时价格 (RUB) USDT≈{usdt_rub:.2f}₽\n\n"
    for sym in parts[:20]:
        p = prices.get(sym)
        if p:
            if p > 1000:
                text += f"{sym.upper()}: {p:,.2f} ₽\n"
            else:
                text += f"{sym.upper()}: {p:.2f} ₽\n"
        else:
            text += f"{sym.upper()}: 暂无交易对\n"

    text += "\n输入 /price btc sol doge 查任意币"
    await m.answer(text)

async def main():
    await dp.start_polling(bot)

app = Flask(__name__)
@app.route('/')
def home(): return 'ok - binance 300 coins'
def run_flask(): app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
