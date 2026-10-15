import asyncio
import os
import aiohttp
from datetime import datetime
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = -1004496994086

bot = Bot(token=BOT_TOKEN)
price_history = []

async def check_pump():
    global price_history
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT") as r:
                    data = await r.json()
                    price = float(data['price'])
                    now = datetime.now()
                    price_history.append((now, price))
                    price_history = [(t,p) for t,p in price_history if (now-t).seconds < 300]
                    if len(price_history) > 1:
                        change = (price - price_history[0][1]) / price_history[0][1] * 100
                        if abs(change) >= 2.5:
                            text = f"{'🚀 ВЗЛЕТ!' if change>0 else '💥 ПАДЕНИЕ!'}\n\n<b>BTC: ${price:,.2f}</b>\nЗа 5 мин: {change:+.2f}%"
                            await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode='HTML')
                            price_history.clear()
        except Exception as e:
            print(e)
        await asyncio.sleep(60)

async def send_daily_news(count=5):
    try:
        text = f"{'☀️ Утренний' if datetime.utcnow().hour==5 else '🌙 Вечерний'} дайджест - Крипто Навигатор\n\n"
        for i in range(count):
            text += f"{i+1}. BTC анализ - новость {i+1}\n\n"
        text += "#Новости"
        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode='HTML')
        print(f"NEWS SENT {count}")
    except Exception as e:
        print(e)

async def main():
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(send_daily_news, 'cron', hour=5, minute=0, args=[5]) # МСК 8:00
    scheduler.add_job(send_daily_news, 'cron', hour=16, minute=0, args=[5]) # МСК 19:00
    scheduler.start()
    print("Scheduler OK: MSK 8:00 & 19:00")
    await check_pump()

if __name__ == "__main__":
    asyncio.run(main())
