import asyncio
import os
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
import threading

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = -1004496994086

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
price_history = []

# ===== Flask 保活，给Render用的 =====
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running"
def run_flask(): app.run(host='0.0.0.0', port=10000)
threading.Thread(target=run_flask, daemon=True).start()

# ===== 功能3：你说的查币功能，找回来了 =====
@dp.message()
async def coin_info_handler(message: types.Message):
    coin = message.text.strip().upper()
    if len(coin) > 10 or " " in coin: return # 忽略长句

    # 只处理像是币名的
    try:
        async with aiohttp.ClientSession() as session:
            # 用 Binance 查价格
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={coin}USDT"
            async with session.get(url) as r:
                if r.status == 200:
                    d = await r.json()
                    price = float(d['lastPrice'])
                    change = float(d['priceChangePercent'])
                    high = float(d['highPrice'])
                    low = float(d['lowPrice'])
                    vol = float(d['volume'])

                    emoji = "🟢" if change >= 0 else "🔴"
                    text = (
                        f"{emoji} <b>{coin}/USDT</b>\n\n"
                        f"💰 Цена: <b>${price:,.4f}</b>\n"
                        f"📈 24ч: {change:+.2f}%\n"
                        f"🔺 Макс: ${high:,.4f}\n"
                        f"🔻 Мин: ${low:,.4f}\n"
                        f"📊 Объем: {vol:,.0f} {coin}\n\n"
                        f"#️⃣ #{coin} #КриптоНавигатор"
                    )
                    await message.reply(text, parse_mode='HTML')
                    return
    except:
        pass

    # 如果 Binance 没有，就试试提示
    if message.chat.type == 'private':
        await message.reply(f"Не нашел монету {coin}. Попробуй BTC, ETH, TON, SOL...")

# ===== 功能1：暴涨报警 =====
async def check_pump():
    global price_history
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT") as r:
                    price = float((await r.json())['price'])
                    now = datetime.now()
                    price_history.append((now, price))
                    price_history = [(t,p) for t,p in price_history if (now-t).seconds < 300]
                    if len(price_history) > 1:
                        change = (price - price_history[0][1]) / price_history[0][1] * 100
                        if abs(change) >= 2.5:
                            txt = f"{'🚀 ВЗЛЕТ!' if change>0 else '💥 ПАДЕНИЕ!'}\n\n<b>BTC: ${price:,.2f}</b>\nЗа 5 мин: {change:+.2f}%"
                            await bot.send_message(chat_id=CHANNEL_ID, text=txt, parse_mode='HTML')
                            price_history.clear()
        except Exception as e:
            print(e)
        await asyncio.sleep(60)

# ===== 功能2：每日5条新闻 =====
async def send_daily_news(count=5):
    try:
        is_morning = datetime.utcnow().hour == 5
        header = "☀️ <b>Утренний дайджест</b>" if is_morning else "🌙 <b>Вечерний дайджест</b>"
        txt = f"{header} - Крипто Навигатор\n\n"
        for i in range(count):
            txt += f"{i+1}. BTC держится выше $... - анализ рынка\n\n"
        txt += "➡️ Подпишись: @crypto_navigator"
        await bot.send_message(chat_id=CHANNEL_ID, text=txt, parse_mode='HTML')
        print(f"NEWS {count} sent")
    except Exception as e:
        print(e)

async def main():
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(send_daily_news, 'cron', hour=5, minute=0, args=[5])
    scheduler.add_job(send_daily_news, 'cron', hour=16, minute=0, args=[5])
    scheduler.start()
    print("Scheduler OK - MSK 8:00 & 19:00")

    # 同时跑3个：报警 + 机器人监听
    await asyncio.gather(
        check_pump(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
