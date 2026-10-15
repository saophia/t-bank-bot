import asyncio
import os
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
import threading

# ========== 配置 ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = -1004496994086 # 你的频道

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
price_history = []

# ========== Flask 保活 (Render需要) ==========
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is live - Crypto Navigator"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

threading.Thread(target=run_flask, daemon=True).start()

# ========== 功能3：发币名查信息 (修复版，用CoinGecko，支持小写) ==========
COIN_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "TON": "the-open-network",
    "SOL": "solana", "BNB": "binancecoin", "XRP": "ripple",
    "DOGE": "dogecoin", "ADA": "cardano", "AVAX": "avalanche-2",
    "TRX": "tron", "DOT": "polkadot", "LINK": "chainlink",
    "USDT": "tether", "USDC": "usd-coin"
}

@dp.message()
async def coin_info_handler(message: types.Message):
    text = message.text.strip().upper()
    # 忽略长句子和命令
    if not text or len(text) > 10 or " " in text or text.startswith("/"):
        return

    coin_id = COIN_MAP.get(text, text.lower())

    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
            async with session.get(url) as r:
                if r.status == 200:
                    d = await r.json()
                    name = d['name']
                    symbol = d['symbol'].upper()
                    md = d['market_data']
                    price = md['current_price']['usd']
                    change_24 = md['price_change_percentage_24h'] or 0
                    high_24 = md['high_24h']['usd']
                    low_24 = md['low_24h']['usd']
                    mcap = md['market_cap']['usd']

                    emoji = "🟢" if change_24 >= 0 else "🔴"
                    reply = (
                        f"{emoji} <b>{name} ({symbol})</b>\n\n"
                        f"💰 Цена: <b>${price:,.4f}</b>\n"
                        f"📈 24ч: {change_24:+.2f}%\n"
                        f"🔺 Макс 24ч: ${high_24:,.4f}\n"
                        f"🔻 Мин 24ч: ${low_24:,.4f}\n"
                        f"💎 Капа: ${mcap:,.0f}\n\n"
                        f"#️⃣ #{symbol} #КриптоНавигатор"
                    )
                    await message.reply(reply, parse_mode='HTML')
                    return
    except Exception as e:
        print(f"coin error {text}: {e}")

    # 私聊才提示找不到，群里/频道里不刷屏
    if message.chat.type == 'private':
        await message.reply(f"Не нашел монету {text}. Попробуй BTC, ETH, TON, SOL...")

# ========== 功能1：暴涨暴跌报警 24/7 ==========
async def check_pump():
    global price_history
    print("Pump monitor started")
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                # 用CoinGecko获取BTC价格，更稳定
                url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
                async with session.get(url) as r:
                    data = await r.json()
                    price = float(data['bitcoin']['usd'])
                    now = datetime.now()
                    price_history.append((now, price))
                    # 只保留5分钟
                    price_history = [(t,p) for t,p in price_history if (now - t).seconds < 300]

                    if len(price_history) > 1:
                        old_price = price_history[0][1]
                        change = (price - old_price) / old_price * 100
                        if abs(change) >= 2.5:
                            txt = (
                                f"{'🚀🚀🚀 ВЗЛЕТ!' if change > 0 else '💥💥💥 ПАДЕНИЕ!'}\n\n"
                                f"<b>BTC: ${price:,.2f}</b>\n"
                                f"Изменение за 5 мин: {change:+.2f}%\n\n"
                                f"#BTC #Alert"
                            )
                            await bot.send_message(chat_id=CHANNEL_ID, text=txt, parse_mode='HTML')
                            print(f"ALERT SENT {change:.2f}%")
                            price_history.clear()
        except Exception as e:
            print(f"pump error: {e}")
        await asyncio.sleep(60)

# ========== 功能2：每日新闻 莫斯科 8:00和19:00各5条 ==========
async def send_daily_news(count=5):
    try:
        is_morning = datetime.utcnow().hour == 5
        header = "☀️ <b>Утренний дайджест</b>" if is_morning else "🌙 <b>Вечерний дайджест</b>"
        # 这里你可以以后接真实的新闻API，现在先用模板
        text = f"{header} - Крипто Навигатор\n🕐 Москва: {datetime.now().strftime('%H:%M')}\n\n"
        for i in range(count):
            text += f"{i+1}. Bitcoin удерживает уровень - анализ рынка и прогнозы\n\n"
        text += "➡️ @твой_канал | #Новости"

        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode='HTML')
        print(f"NEWS SENT: {count} items, morning={is_morning}")
    except Exception as e:
        print(f"news error: {e}")

# ========== 主程序 ==========
async def main():
    # 解决你截图里的 Conflict 错误
    await bot.delete_webhook(drop_pending_updates=True)
    print("Webhook cleared, old connections removed")

    scheduler = AsyncIOScheduler(timezone="UTC")
    # 莫斯科 8:00 = UTC 5:00
    scheduler.add_job(send_daily_news, 'cron', hour=5, minute=0, args=[5])
    # 莫斯科 19:00 = UTC 16:00
    scheduler.add_job(send_daily_news, 'cron', hour=16, minute=0, args=[5])
    scheduler.start()
    print("Scheduler OK: MSK 08:00 & 19:00 (5 news each)")

    # 同时跑：价格监控 + 机器人监听
    await asyncio.gather(
        check_pump(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
