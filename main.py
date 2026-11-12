import os, asyncio, aiohttp
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher
from flask import Flask
import threading

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID") or "-1004496994086"

if not TOKEN: raise ValueError("BOT_TOKEN not set!")
bot = Bot(token=TOKEN)
dp = Dispatcher()
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
LAST_REPORTS = {"morning": None, "evening": None}

async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=10) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        print(f"fetch fail {url} {e}")
    return None

async def get_top5_news():
    real_news = []
    crypto_keywords = ["биткоин","btc","эфир","eth","ton","крипт","блокчейн","токен","lisk","liquid","sol","doge","usdt","tether","binance","коин","майнинг","defi","etf"]
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as s:
        rss_sources = [
            "https://api.rss2json.com/v1/api.json?rss_url=https://ru.cointelegraph.com/rss",
            "https://api.rss2json.com/v1/api.json?rss_url=https://bits.media/rss/",
        ]
        for rss_url in rss_sources:
            try:
                data = await fetch_json(s, rss_url)
                if not data or not data.get('items'): continue
                for item in data['items']:
                    title = item.get('title','').strip()
                    link = item.get('link','').strip()
                    if len(title) < 15: continue
                    low = title.lower()
                    if "openai" in low or "закон об ии" in low: continue
                    if not any(k in low for k in crypto_keywords): continue
                    if any(x['url'] == link for x in real_news): continue
                    real_news.append({"title": title[:90], "url": link})
                    if len(real_news) >= 5: break
            except: continue
            if len(real_news) >= 5: break
    return real_news[:5]

async def get_price(session, sym):
    try:
        data = await fetch_json(session, f"https://www.okx.com/api/v5/market/ticker?instId={sym}-USDT")
        if data and data.get('data'):
            d = data['data'][0]
            last = float(d.get('last') or 0)
            open24 = float(d.get('open24h') or 0)
            if last > 0 and open24 > 0:
                return last, (last-open24)/open24*100
    except: pass
    try:
        data = await fetch_json(session, f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={sym}USDT")
        if data and data['result'].get('list'):
            d = data['result']['list'][0]
            last = float(d.get('lastPrice') or 0)
            change = float(d.get('price24hPcnt') or 0)*100
            if last > 0: return last, change
    except: pass
    return None, None

async def build_digest(is_morning=True):
    async with aiohttp.ClientSession(headers={"User-Agent":"Mozilla/5.0"}) as s:
        btc_price, btc_change = await get_price(s, "BTC")
        ton_price, ton_change = await get_price(s, "TON")
        eth_price, eth_change = await get_price(s, "ETH")

        fg_val, fg_text = 26, "Fear"
        fg = await fetch_json(s, "https://api.alternative.me/fng/?limit=1")
        if fg and 'data' in fg:
            try:
                fg_val = int(fg['data'][0]['value'])
                fg_text = fg['data'][0]['value_classification']
            except: pass

    top5 = await get_top5_news()
    date = datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y")

    def fmt(p, c):
        if p is None or p == 0: return "загрузка..."
        return f"${p:,.0f} ({c:+.2f}%)" if abs(p) > 10 else f"${p:.3f} ({c:+.2f}%)"

    def ch(c):
        return f"{c:+.2f}%" if c is not None else "0.00%"

    news_block = "".join([f'{i}. <a href="{n["url"]}">{n["title"][:85]}</a>\n' for i, n in enumerate(top5, 1)])
    if not news_block:
        news_block = "Новостей пока нет\n"

    if is_morning:
        text = f"""☀️ <b>УТРЕННИЙ ДАЙДЖЕСТ | {date}</b>
💰 Рынок: BTC {fmt(btc_price, btc_change)} | TON {fmt(ton_price, ton_change)}
🧠 Страх: {fg_val} ({fg_text})
🔥 <b>ТОП-5 новостей:</b>
{news_block}
#утро #BTC #TON"""
    else:
        text = f"""🌙 <b>ВЕЧЕРНИЙ ИТОГ | {date}</b>
За день: BTC {ch(btc_change)} | ETH {ch(eth_change)} | TON {ch(ton_change)}
🧠 Индекс: {fg_val}
📌 <b>Что случилось сегодня:</b>
{news_block}
Завтра в 7:00 утренний дайджест.
#вечер #TON"""
    return text

async def send_digest(is_morning=True):
    try:
        text = await build_digest(is_morning)
        await bot.send_message(chat_id=int(CHANNEL_ID), text=text, parse_mode="HTML", disable_web_page_preview=True)
        print(f"✅ Digest sent morning={is_morning}")
    except Exception as e:
        print(f"❌ DIGEST FAILED: {e}")

async def scheduler_loop():
    print("Scheduler - only morning/evening digest")
    while True:
        try:
            now_msk = datetime.now(MOSCOW_TZ)
            if now_msk.hour == 7 and 0 <= now_msk.minute < 2:
                if LAST_REPORTS["morning"] != now_msk.date():
                    await send_digest(True)
                    LAST_REPORTS["morning"] = now_msk.date()
            if now_msk.hour == 19 and 0 <= now_msk.minute < 2:
                if LAST_REPORTS["evening"] != now_msk.date():
                    await send_digest(False)
                    LAST_REPORTS["evening"] = now_msk.date()
            await asyncio.sleep(30)
        except:
            await asyncio.sleep(60)

async def main():
    asyncio.create_task(scheduler_loop())
    await dp.start_polling(bot, allowed_updates=[])

app = Flask(__name__)
@app.route('/')
def home(): return 'ok - only digest'

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
