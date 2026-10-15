def format_msg_and_kb(symbol, a):
    date=datetime.now().strftime("%d.%m.%Y")
    news_lines = ""
    for i, n in enumerate(a['news'], 1):
        news_lines += f'{i}. <a href="{n["url"]}">{n["title"]}</a>\n'

    text = f"""📊 {symbol.upper()} Анализ | {date}
💰 Цена: ${a['price']:,.2f} ({a['change']:+.1f}%)
📈 Техника: {a['ma7_text']}, RSI {a['rsi_text']}
🧠 Настроения: Индекс {a['fg_val']} ({a['fg_text']})
📋 Что двигает цену сегодня:
{news_lines}
⚠️ Вывод: {a['conclusion']}
Не фин. совет
💱 Курс T-Bank USDT: {a['rub']:.1f} RUB 👉 @tbank_usdt_bot"""
    return text # 不再返回按钮

async def handle_any(m: Message):
    try:
        if m.text and "Анализ" in m.text and "Курс T-Bank" in m.text:
            return
        txt = (m.text or "").lower().strip().split()[0]
        if not txt: return
        sym = ''.join(filter(str.isalnum, txt))[:10]
        if len(sym)<2: return
        a=await get_analysis(sym)
        text = format_msg_and_kb(sym, a)
        # 去掉了 reply_markup=kb，按钮就没了
        await m.answer(text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        print(f"err {e}")
