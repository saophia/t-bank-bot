import asyncio
import os
import aiohttp
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

# ========== 配置 ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = -1004496994086 # 你的频道ID

bot = Bot(token=BOT_TOKEN)

# ========== 1. 暴涨暴跌报警 (24/7) ==========
price_history = []
ALERT_THRESHOLD = 2.5 # 5分钟内涨跌2.5%就报警

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
                    # 只保留5分钟内
                    price_history = [(t,p) for t,p in price_history if (now-t).seconds < 300]

                    if len(price_history) > 1:
                        old_price = price_history[0][1]
                        change = (price - old_price) / old_price * 100
                        if abs(change) >= ALERT_THRESHOLD:
                            emoji = "🚀🚀🚀 ВЗЛЕТ!" if change > 0 else "💥💥💥 ПАДЕНИЕ!"
                            msg = f"{emoji}\n\n<b>BTC: ${price:,.2f}</b>\nИзменение за 5 мин: {change:+.2f}%\n\n#BTC #Alert"
                            await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode='HTML')
                            price_history.clear() # 发完清空避免刷屏
                            print(f"ALERT SENT: {change:.2f}%")
        except Exception as e:
            print(f"check_pump error: {e}")
        await asyncio.sleep(60)

# ========== 2. 每日新闻 (莫斯科 8:00 和 19:00) ==========
async def send_daily_news(count=5):
    try:
        # 这里用 CryptoPanic 免费API示例，你也可以换成你的新闻源
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={os.getenv('CRYPTOPANIC_TOKEN')}&public=true&kind=news"
        # 如果你没有 token，先用假数据测试
        news_list = []
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                if r.status == 200:
                    data = await r.json()
                    news_list = data.get('results', [])[:count]

        if not news_list:
            # 测试用备用新闻
            news_list = [{"title": f"Тестовая новость {i+1} - BTC анализ"} for i in range(count)]

        header = "☀️ <b>Утренний дайджест - Крипто Навигатор</b>\n" if datetime.utcnow().hour == 5 else "🌙 <b>Вечерний дайджест - Крипто Навигатор</b>\n"
        text = header + f"🕐 Москва: {datetime.now().strftime('%H:%M')}\n\n"
        for i, news in enumerate(news_list, 1):
            title = news.get('title', 'Новость')
            text += f"{i}. {title}\n\n"
        text += "➡️ @твой_канал | #Новости"

        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode='HTML')
        print(f"DAILY NEWS SENT: {count} items")
    except Exception as e:
        print(f"send_daily_news error: {e}")

# ========== 3. 主程序 ==========
async def main():
    print("Бот запущен...")

    # 启动定时器 - 莫斯科时间
    scheduler = AsyncIOScheduler(timezone="UTC")
    # 莫斯科 8:00 = UTC 5:00
    scheduler.add_job(send_daily_news, 'cron', hour=5, minute=0, args=[5])
    # 莫斯科 19:00 = UTC 16:00
    scheduler.add_job(send_daily_news, 'cron', hour=16, minute=0, args=[5])
    scheduler.start()
    print("Scheduler started: 05:00 UTC and 16:00 UTC (Moscow 08:00 & 19:00)")

    # 同时跑报警循环
    await check_pump()

if __name__ == "__main__":
    asyncio.run(main())
