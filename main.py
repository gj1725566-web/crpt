import os
import logging
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CoinGecko API Helpers ---
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

async def fetch_crypto_data(endpoint: str, params: dict = None):
    """Helper to fetch data from CoinGecko with error handling."""
    url = f"{COINGECKO_BASE}/{endpoint}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return None
                return await response.json()
    except Exception as e:
        logger.error(f"CoinGecko API error: {e}")
        return None

async def get_price(coin_id: str):
    data = await fetch_crypto_data("simple/price", {
        "ids": coin_id,
        "vs_currencies": "usd",
        "include_24hr_change": "true"
    })
    if not data or coin_id not in data:
        return None
    return data[coin_id]

async def get_trending():
    data = await fetch_crypto_data("search/trending")
    if not data:
        return []
    return data.get("coins", [])

async def get_market_overview():
    data = await fetch_crypto_data("coins/markets", {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 10,
        "page": 1
    })
    return data or []

async def get_coin_info(coin_id: str):
    data = await fetch_crypto_data(f"coins/{coin_id}")
    return data

# --- Telegram Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the welcome message and inline keyboard shown in the screenshot."""
    welcome_text = (
        "🚀 **Welcome to CryptoBot!**\n\n"
        "Your real-time cryptocurrency companion.\n\n"
        "📊 **Available Commands:**\n"
        "`/price <coin>` - Get current price (e.g., /price bitcoin)\n"
        "`/trending` - See top trending coins\n"
        "`/market` - Top 10 crypto market overview\n"
        "`/coininfo <coin>` - Get detailed coin info\n"
        "`/help` - Show this message\n\n"
        "⚡ *Powered by CoinGecko API*"
    )

    keyboard = [
        [InlineKeyboardButton("📈 Trending", callback_data="trending"),
         InlineKeyboardButton("🪙 Top 10", callback_data="top10")],
        [InlineKeyboardButton("ℹ️ Coin Info", callback_data="coininfo_help"),
         InlineKeyboardButton("📊 CoinGecko", url="https://www.coingecko.com")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: `/price <coin>` (e.g., `/price bitcoin`)", parse_mode="Markdown")
        return

    coin_id = context.args[0].lower()
    data = await get_price(coin_id)

    if not data:
        await update.message.reply_text(f"❌ Could not find price for `{coin_id}`. Check the coin ID (e.g., 'bitcoin', not 'BTC').", parse_mode="Markdown")
        return

    price = data.get("usd", 0)
    change = data.get("usd_24h_change", 0)
    emoji = "🟢" if change >= 0 else "🔴"

    text = (
        f"💰 **{coin_id.capitalize()}**\n"
        f"Price: **${price:,.2f}**\n"
        f"24h Change: {emoji} **{change:.2f}%**"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    coins = await get_trending()
    if not coins:
        await update.message.reply_text("⚠️ Could not fetch trending data right now.")
        return

    text = "🔥 **Trending Coins**\n\n"
    for i, item in enumerate(coins[:10], 1):
        coin = item.get("item", {})
        name = coin.get("name", "Unknown")
        symbol = coin.get("symbol", "?").upper()
        price_btc = coin.get("price_btc", 0)
        text += f"{i}. **{name}** ({symbol}) - {price_btc} BTC\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    coins = await get_market_overview()
    if not coins:
        await update.message.reply_text("⚠️ Could not fetch market data right now.")
        return

    text = "🏆 **Top 10 Market Overview**\n\n"
    for i, coin in enumerate(coins, 1):
        name = coin.get("name", "Unknown")
        symbol = coin.get("symbol", "?").upper()
        price = coin.get("current_price", 0)
        change = coin.get("price_change_percentage_24h", 0)
        emoji = "🟢" if change and change >= 0 else "🔴"
        text += f"{i}. **{name}** ({symbol}) - ${price:,.2f} {emoji} {change:.2f}%\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def coininfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: `/coininfo <coin>` (e.g., `/coininfo ethereum`)", parse_mode="Markdown")
        return

    coin_id = context.args[0].lower()
    data = await get_coin_info(coin_id)

    if not data:
        await update.message.reply_text(f"❌ Could not find info for `{coin_id}`.", parse_mode="Markdown")
        return

    name = data.get("name", "Unknown")
    symbol = data.get("symbol", "?").upper()
    price = data.get("market_data", {}).get("current_price", {}).get("usd", 0)
    market_cap = data.get("market_data", {}).get("market_cap", {}).get("usd", 0)
    volume = data.get("market_data", {}).get("total_volume", {}).get("usd", 0)
    rank = data.get("market_cap_rank", "N/A")

    text = (
        f"📊 **{name} ({symbol})**\n\n"
        f"**Price:** ${price:,.2f}\n"
        f"**Market Cap:** ${market_cap:,.0f}\n"
        f"**24h Volume:** ${volume:,.0f}\n"
        f"**Market Rank:** #{rank}\n\n"
        f"🔗 [View on CoinGecko](https://www.coingecko.com/en/coins/{coin_id})"
    )
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles clicks on the inline buttons."""
    query = update.callback_query
    await query.answer()

    if query.data == "trending":
        await trending_command(update, context)
    elif query.data == "top10":
        await market_command(update, context)
    elif query.data == "coininfo_help":
        await query.message.reply_text("Usage: `/coininfo <coin>` (e.g., `/coininfo bitcoin`)", parse_mode="Markdown")

# --- Main Application ---

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    application = Application.builder().token(token).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("trending", trending_command))
    application.add_handler(CommandHandler("market", market_command))
    application.add_handler(CommandHandler("coininfo", coininfo_command))

    # Button callbacks
    application.add_handler(CallbackQueryHandler(button_callback))

    logger.info("CryptoBot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
