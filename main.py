// @version=5
indicator("BTC 1min V18 Scalp Final - EN", overlay=true, max_labels_count=500)

minBars = 3

ema9 = ta.ema(close, 9)
ema21 = ta.ema(close, 21)
vwap = ta.vwap(close)
rsi5 = ta.rsi(close, 5)
rsi14 = ta.rsi(close, 14)
volSMA = ta.sma(volume, 20)

// 不看EMA50，只看9和21，震荡也能出信号
trendUp = ema9 > ema21
trendDown = ema9 < ema21

// BUY：超短线回调买，3个条件满足1个就买
buy1 = ta.crossover(rsi5, 30) and close > ema9 // RSI快线从超卖拉起
buy2 = trendUp and low <= ema21 and close > ema9 and rsi14 > 40 // 顺势回踩
buy3 = close > open and close[1] < open[1] and rsi5 < 40 and volume > volSMA * 0.6 // 超跌阳包阴

rawBuy = (buy1 or buy2 or buy3) and barstate.isconfirmed

// SELL：反弹卖
sell1 = ta.crossunder(rsi5, 70) and close < ema9
sell2 = trendDown and high >= ema21 and close < ema9 and rsi14 < 60
sell3 = close < open and close[1] > open[1] and rsi5 > 60 and volume > volSMA * 0.6

rawSell = (sell1 or sell2 or sell3) and barstate.isconfirmed

var int last = na
canTrade = na(last) or bar_index - last >= minBars

buySignal = rawBuy and canTrade
sellSignal = rawSell and canTrade

if buySignal or sellSignal
    last := bar_index

plot(vwap, "VWAP", color.yellow, 2)
plot(ema9, "EMA9", color.orange, 2)
plot(ema21, "EMA21", color.purple, 2)

plotshape(buySignal, "BUY", shape.labelup, location.belowbar, color.new(#00C853,0), text="BUY", textcolor=color.white, size=size.small)
plotshape(sellSignal, "SELL", shape.labeldown, location.abovebar, color.new(#D50000,0), text="SELL", textcolor=color.white, size=size.small)

alertcondition(buySignal, "BUY Scalp", "BUY")
alertcondition(sellSignal, "SELL Scalp", "SELL")
