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

COINS = {
 "btc":"bitcoin","eth":"ethereum","usdt":"tether","bnb":"binancecoin","sol":"solana",
 "xrp":"ripple","doge":"dogecoin","ada":"cardano","trx":"tron","ton":"the-open-network",
 "avax":"avalanche-2","shib":"shiba-inu","dot":"polkadot","link":"chainlink","bch":"bitcoin-cash",
 "near":"near","ltc":"litecoin","matic":"matic-network","uni":"uniswap","etc":"ethereum-classic",
 "pepe":"pepe","icp":"internet-computer","apt":"aptos","fil":"filecoin","arb":"arbitrum",
 "atom":"cosmos","wif":"dogwifcoin","rndr":"render-token","sui":"sui",
 "xmr":"monero","xlm":"stellar","hbar":"hedera-hashgraph","vet":"vechain",
 "op":"optimism","grt":"the-graph","stx":"stacks","ldo":"lido-dao","inj":"injective-protocol",
 "imx":"immutable-x","aave":"aave","ftm":"fantom","algo":"algorand","qnt":"quant-network",
 "flow":"flow","sand":"the-sandbox","mana":"decentraland","axs":"axie-infinity","chz":"chiliz",
 "eos":"eos","xtz":"tezos","egld":"elrond-erd-2","theta":"theta-token","neo":"neo",
 "kava":"kava","mina":"mina-protocol","cfx":"conflux-token","ron":"ronin","w":"wormhole",
 "sei":"sei-network","bonk":"bonk","floki":"floki","jup":"jupiter-exchange-solana","pyth":"pyth-network",
 "strk":"starknet","wld":"worldcoin-wld","tia":"celestia","ar":"arweave","mkr":"maker"
}

TOP_IDS = ["bitcoin","ethereum","tether","solana","binancecoin","ripple","dogecoin","cardano","tron","avalanche-2",
"shiba-inu","polkadot","chainlink","bitcoin-cash","near","litecoin","matic-network","uniswap","ethereum-classic","pepe"]

async def get_prices(ids):
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids)}&vs_currencies=rub"
    # 尝试2次
    for _ in range(2):
        try:
            async with aiohttp.ClientSession(headers=headers) as s:
                async with s.get(url, timeout=15) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data:
                            return data
        except Exception as e:
            print(f"coingecko fail {e}")
            await asyncio.sleep(1)

    # 备用: 尝试用 binance + usdt价格算
    print("coingecko failed, trying fallback")
    return {}

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("✅ T-Bank Bot 已启动 300币版\n\n/price - 热门20\n/price btc - 单个\n/price btc eth sol - 多个")

@dp.message(Command("price"))
async def price(m: Message):
    parts = m.text.lower().split()[1:]
    if not parts:
        data = await get_prices(TOP_IDS)
        if not data:
            await m.answer("CoinGecko暂时连不上，10秒后再试 /price")
            return
        text = "🔥 热门20 (RUB):\n"
        for sym, cid in list(COINS.items())[:20]:
            p = data.get(cid, {}).get("rub")
            if p:
                text += f"{sym.upper()}: {p:,.2f} ₽\n"
        await m.answer(text)
        return

    ids_to_fetch = []
    sym_to_id = {}
    for sym in parts[:20]:
        cid = COINS.get(sym, sym)
        ids_to_fetch.append(cid)
        sym_to_id[sym] = cid

    data = await get_prices(ids_to_fetch)
    if not data:
        await m.answer("⚠️ CoinGecko接口超时，Render在国外有时会被限，1分钟后再试一次 /price btc 就会好。\n\n如果一直不行，我给你换成 Binance接口版")
        return

    text = "💰 价格 (RUB):\n"
    for sym in parts[:20]:
        cid = sym_to_id[sym]
        p = data.get(cid, {}).get("rub")
        if p:
            text += f"{sym.upper()}: {p:,.2f} ₽\n"
        else:
            text += f"{sym.upper()}: {cid} 未找到\n"
    await m.answer(text)

async def main():
    await dp.start_polling(bot)

app = Flask(__name__)
@app.route('/')
def home(): return 'ok - bot running 300 coins v2'
def run_flask(): app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
