import asyncio, aiohttp, os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.environ.get("TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()
rate = 83.81

async def get_rate():
    global rate
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=rub") as r:
                j = await r.json()
                rate = j['tether']['rub']
    except: pass

@dp.message(Command("start"))
async def start(m: types.Message):
    await get_rate()
    await m.answer(f"🏦 Т-Банк USDT Курс\n\nАктуальный курс: 1 USDT = {rate:.2f} RUB\n\nНапиши сумму в RUB, например 10000\n✅ СБП без 115-ФЗ")

@dp.message()
async def calc(m: types.Message):
    await get_rate()
    try:
        num = float(m.text.replace(",",".").replace("₽","").split()[0])
        await m.answer(f"💰 {num:.0f} RUB = {num/rate:.2f} USDT\nКурс {rate:.2f}")
    except:
        await m.answer(f"Курс: {rate:.2f} RUB")

async def main(): await dp.start_polling(bot)
asyncio.run(main())
