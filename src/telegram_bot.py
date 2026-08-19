"""
Telegram Bot integration for MealMind.
Handles /start, OAuth account linking, and command interface to MCP tools.

Supports multi-user data isolation using FoodIQ User.id.
"""
import os
import logging
import urllib.parse
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .database import get_session
from sqlmodel import select
from .models import OAuthState, User, SwiggyConnection
from .security import generate_oauth_state, generate_pkce_verifier, generate_pkce_challenge

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Helper: Check if user is connected
# -------------------------------------------------------------------------

def is_user_connected(telegram_id: str) -> bool:
    """Check if the Telegram user has a connected Swiggy account."""
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        if user:
            conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
            if conn and conn.status == "CONNECTED":
                return True
    return False


def get_user_id(telegram_id: str) -> int | None:
    """Resolve a Telegram ID to a FoodIQ User ID."""
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        if user:
            return user.id
    return None

# -------------------------------------------------------------------------
# Command: /start
# -------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    if not update.effective_user or not update.message:
        return
        
    telegram_id = str(update.effective_user.id)
    
    # Check if already connected
    if is_user_connected(telegram_id):
        keyboard = [
            [InlineKeyboardButton("📊 Insights", callback_data="insights")],
            [InlineKeyboardButton("🍱 Orders", callback_data="orders"), 
             InlineKeyboardButton("🏪 Restaurants", callback_data="restaurants")],
            [InlineKeyboardButton("📈 Analytics", callback_data="analytics"),
             InlineKeyboardButton("🔎 Search", callback_data="search")],
            [InlineKeyboardButton("🔄 Sync", callback_data="sync"),
             InlineKeyboardButton("❓ Help", callback_data="help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👋 Welcome back to MealMind!\n\n"
            "✅ Swiggy connected\n\n"
            "Choose an option below:",
            reply_markup=reply_markup
        )
        return
        
    # User not connected - show Connect Swiggy button
    import hashlib
    # Generate OAuth state and PKCE verifier
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    challenge = generate_pkce_challenge(verifier)
    
    # Store state
    with get_session() as session:
        now_utc = datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(minutes=15)
        # Convert to naive UTC for SQLite storage
        expires_at_naive = expires_at.replace(tzinfo=None)
        
        state_hash = hashlib.sha256(state.encode('utf-8')).hexdigest()[:12]
        from .database import get_engine
        engine_url = str(get_engine().url)
        logger.info("OAuth state CREATED:")
        logger.info(f"  hash={state_hash}")
        logger.info(f"  length={len(state)}")
        logger.info(f"  telegram_id={telegram_id}")
        logger.info(f"  engine_url={engine_url}")
        logger.info(f"  expires_at={expires_at_naive} (naive UTC)")
        
        oauth_state = OAuthState(
            state=state,
            telegram_id=telegram_id,
            code_verifier=verifier,
            expires_at=expires_at_naive
        )
        session.add(oauth_state)
        session.commit()
        logger.info(f"  ✓ State persisted to database")
        
    # Build authorization URL
    from .dcr import get_or_register_client
    try:
        client_id = await get_or_register_client()
    except Exception as e:
        logger.exception("Failed to get or register Swiggy OAuth client")
        await update.message.reply_text("❌ Sorry, there was an internal error setting up the connection. Please try again later.")
        return

    redirect_uri = os.getenv("SWIGGY_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/swiggy/callback")
    
    # Official Swiggy auth endpoint
    auth_base_url = "https://mcp.swiggy.com/auth/authorize"
    
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "mcp:tools"
    }
    
    auth_url = f"{auth_base_url}?{urllib.parse.urlencode(params)}"
    
    parsed_url = urllib.parse.urlparse(auth_url)
    qs = urllib.parse.parse_qs(parsed_url.query)
    auth_state_qs = qs.get("state", [""])[0]
    auth_state_hash = hashlib.sha256(auth_state_qs.encode('utf-8')).hexdigest()[:12]
    
    logger.info(f"  ✓ Authorization URL generated (state_hash={auth_state_hash})")
    
    keyboard = [
        [InlineKeyboardButton("Connect Swiggy", url=auth_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Welcome to MealMind!\n\n"
        "Connect your Swiggy account to get personalized food insights.",
        reply_markup=reply_markup
    )


# -------------------------------------------------------------------------
# Command: /help
# -------------------------------------------------------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command."""
    if not update.effective_user or not update.message:
        return
    
    telegram_id = str(update.effective_user.id)
    
    if not is_user_connected(telegram_id):
        await update.message.reply_text(
            "❌ Please connect your Swiggy account first.\n\n"
            "Use /start to connect."
        )
        return
    
    help_text = (
        "📚 **MealMind Commands**\n\n"
        "🔹 **/start** - Show main menu\n"
        "🔹 **/help** - Show this help message\n"
        "🔹 **/insights** - Get personalized food insights\n"
        "🔹 **/orders** - View recent orders\n"
        "🔹 **/restaurants** - List your favorite restaurants\n"
        "🔹 **/analytics** - Get spending and ordering analytics\n"
        "🔹 **/search <query>** - Search orders by restaurant, cuisine, or item\n"
        "🔹 **/sync** - Sync new orders (requires cookies)\n\n"
        "💡 **Tip**: Use the button menu from /start for quick access!\n\n"
        "⚠️ **Note**: /sync requires manual cookie input (legacy flow)."
    )
    
    await update.message.reply_text(help_text, parse_mode="Markdown")


# -------------------------------------------------------------------------
# Command: /insights
# -------------------------------------------------------------------------

async def insights_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /insights command."""
    if not update.effective_user or not update.message:
        return
    
    telegram_id = str(update.effective_user.id)
    
    if not is_user_connected(telegram_id):
        await update.message.reply_text("❌ Please connect your Swiggy account first. Use /start to connect.")
        return
    
    # Call the MCP tool
    from .mcp_server import get_food_insights
    
    user_id = get_user_id(telegram_id)
    await update.message.reply_text("🔄 Generating insights...")
    
    try:
        result = get_food_insights(user_id=user_id)
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Failed to generate insights")
        await update.message.reply_text("❌ Failed to generate insights. Please try again later.")


# -------------------------------------------------------------------------
# Command: /orders
# -------------------------------------------------------------------------

async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /orders command."""
    if not update.effective_user or not update.message:
        return
    
    telegram_id = str(update.effective_user.id)
    
    if not is_user_connected(telegram_id):
        await update.message.reply_text("❌ Please connect your Swiggy account first. Use /start to connect.")
        return
    
    # Call the MCP tool
    from .mcp_server import get_orders
    
    user_id = get_user_id(telegram_id)
    await update.message.reply_text("🔄 Fetching orders...")
    
    try:
        result = get_orders(limit=10, user_id=user_id)
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Failed to fetch orders")
        await update.message.reply_text("❌ Failed to fetch orders. Please try again later.")


# -------------------------------------------------------------------------
# Command: /restaurants
# -------------------------------------------------------------------------

async def restaurants_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /restaurants command."""
    if not update.effective_user or not update.message:
        return
    
    telegram_id = str(update.effective_user.id)
    
    if not is_user_connected(telegram_id):
        await update.message.reply_text("❌ Please connect your Swiggy account first. Use /start to connect.")
        return
    
    # Call the MCP tool
    from .mcp_server import get_restaurants
    
    user_id = get_user_id(telegram_id)
    await update.message.reply_text("🔄 Fetching restaurants...")
    
    try:
        result = get_restaurants(user_id=user_id)
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Failed to fetch restaurants")
        await update.message.reply_text("❌ Failed to fetch restaurants. Please try again later.")


# -------------------------------------------------------------------------
# Command: /analytics
# -------------------------------------------------------------------------

async def analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /analytics command."""
    if not update.effective_user or not update.message:
        return
    
    telegram_id = str(update.effective_user.id)
    
    if not is_user_connected(telegram_id):
        await update.message.reply_text("❌ Please connect your Swiggy account first. Use /start to connect.")
        return
    
    # Call the MCP tool
    from .mcp_server import get_analytics
    
    user_id = get_user_id(telegram_id)
    await update.message.reply_text("🔄 Generating analytics...")
    
    try:
        result = get_analytics(user_id=user_id)
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Failed to generate analytics")
        await update.message.reply_text("❌ Failed to generate analytics. Please try again later.")


# -------------------------------------------------------------------------
# Command: /search
# -------------------------------------------------------------------------

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /search command."""
    if not update.effective_user or not update.message:
        return
    
    telegram_id = str(update.effective_user.id)
    
    if not is_user_connected(telegram_id):
        await update.message.reply_text("❌ Please connect your Swiggy account first. Use /start to connect.")
        return
    
    # Extract query from command arguments
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a search query.\n\n"
            "Usage: /search <query>\n"
            "Example: /search pizza"
        )
        return
    
    query = " ".join(context.args)
    
    # Call the MCP tool
    from .mcp_server import search_orders
    
    user_id = get_user_id(telegram_id)
    await update.message.reply_text(f"🔄 Searching for '{query}'...")
    
    try:
        result = search_orders(query=query, user_id=user_id)
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Failed to search orders")
        await update.message.reply_text("❌ Failed to search orders. Please try again later.")


# -------------------------------------------------------------------------
# Command: /sync
# -------------------------------------------------------------------------

async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /sync command."""
    if not update.effective_user or not update.message:
        return
    
    telegram_id = str(update.effective_user.id)
    
    if not is_user_connected(telegram_id):
        await update.message.reply_text("❌ Please connect your Swiggy account first. Use /start to connect.")
        return
    
    await update.message.reply_text(
        "Your Swiggy account is connected, but historical order sync is not currently available through the official OAuth integration."
    )


# -------------------------------------------------------------------------
# Callback Query Handler (for inline buttons)
# -------------------------------------------------------------------------

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return
    
    await query.answer()
    
    telegram_id = str(update.effective_user.id) if update.effective_user else None
    if not telegram_id:
        return
    
    # Check authorization for all actions except help
    if query.data != "help" and not is_user_connected(telegram_id):
        await query.message.reply_text(
            "❌ Please connect your Swiggy account first. Use /start to connect."
        )
        return
    
    # Handle each button action
    try:
        if query.data == "insights":
            from .mcp_server import get_food_insights
            await query.message.reply_text("🔄 Generating insights...")
            result = get_food_insights()
            await query.message.reply_text(result, parse_mode="Markdown")
            
        elif query.data == "orders":
            from .mcp_server import get_orders
            await query.message.reply_text("🔄 Fetching orders...")
            result = get_orders(limit=10)
            await query.message.reply_text(result, parse_mode="Markdown")
            
        elif query.data == "restaurants":
            from .mcp_server import get_restaurants
            await query.message.reply_text("🔄 Fetching restaurants...")
            result = get_restaurants()
            await query.message.reply_text(result, parse_mode="Markdown")
            
        elif query.data == "analytics":
            from .mcp_server import get_analytics
            await query.message.reply_text("🔄 Generating analytics...")
            result = get_analytics()
            await query.message.reply_text(result, parse_mode="Markdown")
            
        elif query.data == "search":
            await query.message.reply_text(
                "🔎 **Search Orders**\n\n"
                "To search your orders, use the command:\n"
                "`/search <query>`\n\n"
                "**Examples:**\n"
                "• `/search pizza`\n"
                "• `/search biryani`\n"
                "• `/search Dominos`\n"
                "• `/search Indiranagar`",
                parse_mode="Markdown"
            )
            
        elif query.data == "sync":
            await query.message.reply_text(
                "Your Swiggy account is connected, but historical order sync is not currently available through the official OAuth integration."
            )
            
        elif query.data == "help":
            help_text = (
                "📚 **MealMind Commands**\n\n"
                "🔹 **/start** - Show main menu\n"
                "🔹 **/help** - Show this help message\n"
                "🔹 **/insights** - Get personalized food insights\n"
                "🔹 **/orders** - View recent orders\n"
                "� **/restaurants** - List your favorite restaurants\n"
                "🔹 **/analytics** - Get spending and ordering analytics\n"
                "🔹 **/search <query>** - Search orders by restaurant, cuisine, or item\n"
                "🔹 **/sync** - Sync new orders (requires cookies)\n\n"
                "💡 **Tip**: Use the button menu from /start for quick access!\n\n"
                "⚠️ **Note**: /sync requires manual cookie input (legacy flow)."
            )
            await query.message.reply_text(help_text, parse_mode="Markdown")
            
    except Exception as e:
        logger.exception(f"Failed to handle button callback: {query.data}")
        await query.message.reply_text(
            f"❌ Sorry, I couldn't process your request right now. Please try again later."
        )


# -------------------------------------------------------------------------
# Application Builder
# -------------------------------------------------------------------------

def build_telegram_app() -> Application | None:
    """Build the Telegram application. Returns None if token is missing."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram bot will not start.")
        return None
        
    app = Application.builder().token(token).build()
    
    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("insights", insights_command))
    app.add_handler(CommandHandler("orders", orders_command))
    app.add_handler(CommandHandler("restaurants", restaurants_command))
    app.add_handler(CommandHandler("analytics", analytics_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("sync", sync_command))
    
    # Register callback query handler for inline buttons
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CallbackQueryHandler(button_callback))
    
    return app
