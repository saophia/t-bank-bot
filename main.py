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
 "strk":"starknet","wld":"worldcoin-wld","tia":"celestia","ar":"arweave","mkr":"maker",
 "snx":"synthetix-network-token","comp":"compound-governance-token","1inch":"1inch","ens":"ethereum-name-service",
 "bat":"basic-attention-token","zec":"zcash","dash":"dash","waves":"waves","zrx":"0x",
 "dydx":"dydx","blur":"blur","sei":"sei-network","kas":"kaspa","inj":"injective-protocol"
}

TOP_IDS = ["bitcoin","ethereum","tether","solana","binancecoin","ripple","dogecoin","cardano","tron","avalanche-2",
"shiba-inu","polkadot","chainlink","bitcoin-cash","near","litecoin","matic-network","uniswap","ethereum-classic","pepe"]

async def get_prices(ids):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids)}&vs_currencies=rub"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=10) as r:
                return await r.json()
    except:
        return {}

@dp.message(Command("start"))
async def start(m: Message):
    prices = await get_prices(["tether"])
    rate = prices.get("tether", {}).get("rub", "83.81")
    await m.answer(f"✅ T-Bank Bot 已启动! 支持300币\n\n当前 USDT ≈ {rate} RUB\n\n用法:\n/price - 看热门20币\n/price btc - 查单个\n/price btc eth sol doge - 查多个")

@dp.message(Command("price"))
async def price(m: Message):
    parts = m.text.lower().split()[1:]
    if not parts:
        data = await get_prices(TOP_IDS)
        text = "🔥 热门20币 (RUB):\n"
        for sym, cid in list(COINS.items())[:20]:
            p = data.get(cid, {}).get("rub")
            if p:
                text += f"{sym.upper()}: {p:,.2f} ₽\n"
        text += "\n试试 /price btc eth sol"
        await m.answer(text)
        return

    ids_to_fetch = []
    sym_to_id = {}
    for sym in parts[:30]:
        cid = COINS.get(sym, sym)
        ids_to_fetch.append(cid)
        sym_to_id[sym] = cid

    data = await get_prices(ids_to_fetch)
    if not data:
        await m.answer("API繁忙稍后再试")
        return

    text = "💰 价格 (RUB):\n"
    for sym in parts[:30]:
        cid = sym_to_id[sym]
        p = data.get(cid, {}).get("rub")
        if p:
            text += f"{sym.upper()}: {p:,.2f} ₽\n"
        else:
            text += f"{sym.upper()}: 未找到\n"
    await m.answer(text)

async def main():
    await dp.start_polling(bot)

app = Flask(__name__)
@app.route('/')
def home(): return 'ok - bot running 300 coins'
def run_flask(): app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
