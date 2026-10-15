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
rate = 83.81

async def get_rate():
    global rate
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=rub") as r:
                j = await r.json()
                rate = j['tether']['rub']
    except:
        pass

@dp.message(Command("start"))
async def start(m: Message):
    await get_rate()
    await m.answer(f"Bot 已启动! 当前 USDT ≈ {rate} RUB\n输入 /price 看价格")

@dp.message(Command("price"))
async def price(m: Message):
    await get_rate()
    await m.answer(f"USDT ≈ {rate} RUB")

async def main():
    await dp.start_polling(bot)

# --- 让 Render 能检测到端口 ---
app = Flask(__name__)
@app.route('/')
def home():
    return 'ok - bot running'

def run_flask():
    app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
