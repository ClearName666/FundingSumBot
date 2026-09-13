
import asyncio
import logging
import time
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ВСТАВЬ СЮДА ТОКЕН СВОЕГО БОТА
BOT_TOKEN = "8769315975:AAEt9o0YF42S6pfftp4eXth4G4mrq_lUXd4"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class FundingForm(StatesGroup):
    exchange = State()
    coin = State()
    period = State()

# --- ОБНОВЛЕННАЯ КЛАВИАТУРА ---
def get_exchanges_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔹 MEXC", callback_data="ex_mexc"),
         InlineKeyboardButton(text="🔹 Gate.io", callback_data="ex_gate")],
        [InlineKeyboardButton(text="🔹 Bitget", callback_data="ex_bitget"),
         InlineKeyboardButton(text="🔸 OKX", callback_data="ex_okx")],
        [InlineKeyboardButton(text="🦄 Hyperliquid (DEX)", callback_data="ex_hyperliquid")]
    ])

def get_period_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="24 часа", callback_data="p_1"),
         InlineKeyboardButton(text="3 дня", callback_data="p_3")],
        [InlineKeyboardButton(text="7 дней", callback_data="p_7"),
         InlineKeyboardButton(text="30 дней", callback_data="p_30")]
    ])

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет, felix! 🤙 Я чекер фандинга.\n\n"
        "Выбери биржу (CEX или DEX), на которой будем считать накопленный фандинг:",
        reply_markup=get_exchanges_kb()
    )

@dp.callback_query(F.data.startswith("ex_"))
async def process_exchange(callback: types.CallbackQuery, state: FSMContext):
    exchange = callback.data.split("_")[1]
    await state.update_data(exchange=exchange)
    await callback.message.edit_text(
        f"✅ Биржа: **{exchange.upper()}**\n\n"
        f"Напиши тикер монеты (например: `BTC`, `SOL`, `ETH`):",
        parse_mode="Markdown"
    )
    await state.set_state(FundingForm.coin)

@dp.message(FundingForm.coin)
async def process_coin(message: types.Message, state: FSMContext):
    coin = message.text.strip().upper()
    await state.update_data(coin=coin)
    await message.answer(
        f"🪙 Монета: **{coin}**\n\n"
        f"Выбери период, за который посчитать начисленный фандинг:",
        parse_mode="Markdown",
        reply_markup=get_period_kb()
    )
    await state.set_state(FundingForm.period)

@dp.callback_query(F.data.startswith("p_"))
async def process_period(callback: types.CallbackQuery, state: FSMContext):
    period_days = int(callback.data.split("_")[1])
    data = await state.get_data()
    exchange = data['exchange']
    coin = data['coin']
    
    await callback.message.edit_text("⏳ *Подключаюсь к API, собираю данные...*", parse_mode="Markdown")
    
    try:
        total_funding = await fetch_funding(exchange, coin, period_days)
        
        if total_funding is None:
            await callback.message.edit_text(
                f"❌ Ошибка: не удалось найти данные для **{coin}** на бирже **{exchange.upper()}**.\n",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Считать заново 🔄", callback_data="restart")]
                ])
            )
        else:
            await callback.message.edit_text(
                f"📊 **Отчет по фандингу**\n\n"
                f"🏛 Биржа: `{exchange.upper()}`\n"
                f"🪙 Монета: `{coin}`\n"
                f"📅 Период: `{period_days} дн.`\n\n"
                f"💰 **Накопленный фандинг: {total_funding:.4f}%**",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Считать заново 🔄", callback_data="restart")]
                ])
            )
    except Exception as e:
        logging.error(f"Error fetching: {e}")
        await callback.message.edit_text("❌ Ошибка при вычислении. Попробуй позже.")

@dp.callback_query(F.data == "restart")
async def restart_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выбери биржу:", reply_markup=get_exchanges_kb())

# --- ФУНКЦИИ API (AIOHTTP) ---
async def fetch_funding(exchange: str, coin: str, days: int) -> float | None:
    now_ms = int(time.time() * 1000)
    limit_ms = now_ms - (days * 24 * 60 * 60 * 1000)
    
    async with aiohttp.ClientSession() as session:
        if exchange == "mexc": return await fetch_mexc(session, coin, limit_ms)
        elif exchange == "gate": return await fetch_gate(session, coin, limit_ms)
        elif exchange == "bitget": return await fetch_bitget(session, coin, limit_ms)
        elif exchange == "okx": return await fetch_okx(session, coin, limit_ms)
        elif exchange == "hyperliquid": return await fetch_hyperliquid(session, coin, limit_ms)
    return None

async def fetch_mexc(session, coin, limit_ms):
    url = f"https://contract.mexc.com/api/v1/contract/funding_rate/history?symbol={coin}_USDT&page_size=1000"
    async with session.get(url) as resp:
        if resp.status != 200: return None
        data = await resp.json()
        rates = data.get("data", {}).get("resultList", [])
        return sum(float(i["fundingRate"]) for i in rates if i["settleTime"] >= limit_ms) * 100 if rates else None

async def fetch_gate(session, coin, limit_ms):
    url = f"https://api.gateio.ws/api/v4/futures/usdt/funding_rate?contract={coin}_USDT&limit=1000"
    async with session.get(url) as resp:
        if resp.status != 200: return None
        rates = await resp.json()
        return sum(float(i["r"]) for i in rates if i["t"] >= limit_ms / 1000) * 100 if rates else None

async def fetch_bitget(session, coin, limit_ms):
    url = f"https://api.bitget.com/api/v2/mix/market/history-fund-rate?symbol={coin}USDT&productType=USDT-FUTURES&pageSize=100"
    async with session.get(url) as resp:
        if resp.status != 200: return None
        data = await resp.json()
        rates = data.get("data", [])
        return sum(float(i["fundingRate"]) for i in rates if int(i["fundingTime"]) >= limit_ms) * 100 if rates else None

async def fetch_okx(session, coin, limit_ms):
    # У OKX формат тикеров: BTC-USDT-SWAP
    url = f"https://www.okx.com/api/v5/public/funding-rate-history?instId={coin}-USDT-SWAP&limit=100"
    async with session.get(url) as resp:
        if resp.status != 200: return None
        data = await resp.json()
        if data.get("code") != "0": return None
        rates = data.get("data", [])
        return sum(float(i["fundingRate"]) for i in rates if int(i["fundingTime"]) >= limit_ms) * 100 if rates else None

async def fetch_hyperliquid(session, coin, limit_ms):
    # Hyperliquid API работает через POST запросы
    url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "fundingHistory", "coin": coin, "startTime": limit_ms}
    async with session.post(url, json=payload) as resp:
        if resp.status != 200: return None
        try:
            rates = await resp.json()
            # API может вернуть пустой массив или ошибку, если монеты нет
            if not isinstance(rates, list): return None 
            return sum(float(i["fundingRate"]) for i in rates if i["time"] >= limit_ms) * 100
        except Exception:
            return None

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())