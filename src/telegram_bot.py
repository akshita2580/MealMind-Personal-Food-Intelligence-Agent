"""
Telegram Bot integration for MealMind.
Handles /start, OAuth account linking, and command interface to MCP tools.

Supports multi-user data isolation using FoodIQ User.id.
"""
import os
import hashlib
import json
import logging
import urllib.parse
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .database import get_session
from sqlmodel import select
from .models import OAuthState, User, SwiggyConnection
from .security import generate_oauth_state, generate_pkce_verifier, generate_pkce_challenge, decrypt_token

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Helper: Check if user is connected
# -------------------------------------------------------------------------

def is_user_connected(telegram_id: str) -> bool:
    """Check if the Telegram user has a connected Swiggy account (does not check expiry)."""
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        if user:
            conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
            if conn and conn.status == "CONNECTED":
                return True
    return False

def is_token_expired(telegram_id: str) -> bool:
    """Check if the user's Swiggy connection token is expired."""
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        if user:
            conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
            if conn and conn.expires_at:
                now = datetime.now(timezone.utc)
                expires_at = conn.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if now > expires_at - timedelta(seconds=60):
                    return True
    return False


def get_user_id(telegram_id: str) -> int | None:
    """Resolve a Telegram ID to a FoodIQ User ID."""
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        if user:
            return user.id
    return None


def get_user_access_token(telegram_id: str) -> str | None:
    """Retrieve and decrypt the stored Swiggy access token for a Telegram user."""
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        if not user:
            return None
        conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
        if not conn or conn.status != "CONNECTED" or not conn.access_token:
            return None
        return decrypt_token(conn.access_token)


# -------------------------------------------------------------------------
# Helper: Build OAuth URL (reused by /start and /sync)
# -------------------------------------------------------------------------

async def _build_oauth_url(telegram_id: str) -> str | None:
    """
    Generate a Swiggy OAuth authorization URL for the given Telegram user.
    Returns the URL string, or None on failure.
    """
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    challenge = generate_pkce_challenge(verifier)

    with get_session() as session:
        now_utc = datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(minutes=15)
        expires_at_naive = expires_at.replace(tzinfo=None)

        state_hash = hashlib.sha256(state.encode('utf-8')).hexdigest()[:12]
        
        from .database import get_engine
        engine_url = str(get_engine().url)
        
        logger.info(
            "OAuth state CREATION: created_state_hash=%s created_state_length=%s telegram_id=%s db_path=%s created_at=%s expires_at=%s",
            state_hash, len(state), telegram_id, engine_url, now_utc, expires_at
        )

        oauth_state = OAuthState(
            state=state,
            telegram_id=telegram_id,
            code_verifier=verifier,
            expires_at=expires_at_naive
        )
        session.add(oauth_state)
        session.commit()

    with get_session() as session2:
        check = session2.exec(select(OAuthState).where(OAuthState.state == state)).first()
        logger.info(
            "OAuth state COMMITTED: exists=%s",
            bool(check)
        )

    from .dcr import get_or_register_client
    try:
        client_id = await get_or_register_client()
    except Exception:
        logger.exception("Failed to get or register Swiggy OAuth client")
        return None

    redirect_uri = os.getenv("SWIGGY_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/swiggy/callback")
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
    logger.info("OAuth URL generated: authorize_state_hash=%s authorize_state_length=%s", state_hash, len(state))
    return auth_url


# -------------------------------------------------------------------------
# Helper: Perform real sync via Swiggy MCP
# -------------------------------------------------------------------------

async def _do_sync(telegram_id: str) -> str:
    """
    Attempt to sync orders from the official Swiggy Food MCP using the
    user's stored OAuth access token.

    Returns a user-facing message string.
    """
    from . import swiggy_mcp_client, repository
    from datetime import datetime, timezone

    logger.info("SYNC START")

    user_id = get_user_id(telegram_id)
    if user_id is None:
        return "❌ User account not found. Use /start to set up."
        
    logger.info("USER RESOLVED")

    with get_session() as session:
        conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user_id)).first()
        if not conn or conn.status != "CONNECTED" or not conn.access_token:
            return "❌ No valid Swiggy connection found. Use /start or /sync to connect."
            
        logger.info("CONNECTION FOUND")
            
        if conn.expires_at:
            # Check if token is expired
            now = datetime.now(timezone.utc)
            # Make sure conn.expires_at is timezone aware
            expires_at = conn.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at - timedelta(seconds=60):
                logger.warning(f"LOCAL EXPIRY: now={now} > expires_at={expires_at}")
                return "🔐 Your Swiggy connection has expired locally. Please reconnect."
                
        access_token = decrypt_token(conn.access_token)
        logger.info(
            "TOKEN STATUS: user_id=%s token_exists=%s token_length=%s expires_at=%s token_expired=%s",
            user_id,
            bool(access_token),
            len(access_token) if access_token else 0,
            conn.expires_at,
            (datetime.now(timezone.utc) > conn.expires_at.replace(tzinfo=timezone.utc)) if conn.expires_at else False
        )
        
    logger.info("TOKEN READY")

    # Step 1: Get the user's addresses
    try:
        logger.info("CALLING get_addresses")
        addresses = await swiggy_mcp_client.get_addresses(access_token)
        logger.info("get_addresses RETURNED")
    except Exception as exc:
        logger.exception("Sync: get_addresses failed")
        err_msg = str(exc).lower()
        
        if "http 401" in err_msg or "http 419" in err_msg:
            return "🔐 Your Swiggy connection was rejected by Swiggy (HTTP 401). Please reconnect."
            
        if "timeout" in err_msg or "network error" in err_msg or "dns" in err_msg:
            return "❌ Swiggy service unreachable. Please try again."
            
        return "❌ Swiggy service unreachable. Please try again."

    if not addresses:
        return "No supported Swiggy data is currently available."

    # Use up to 5 recent addresses to find all historical orders
    address_ids = []
    for addr in addresses:
        if isinstance(addr, dict):
            aid = addr.get("id") or addr.get("addressId") or addr.get("address_id")
            if aid and aid not in address_ids:
                address_ids.append(aid)
        if len(address_ids) >= 5:
            break

    if not address_ids:
        return "No supported Swiggy data is currently available."

    # Step 2: Fetch orders using the addresses
    raw_orders = []
    try:
        logger.info(f"CALLING get_food_orders for {len(address_ids)} addresses")
        
        import asyncio
        tasks = [swiggy_mcp_client.get_food_orders(access_token, str(aid)) for aid in address_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in results:
            if isinstance(res, Exception):
                raise res
            if isinstance(res, list):
                raw_orders.extend(res)
                
        logger.info(f"get_food_orders RETURNED {len(raw_orders)} total orders")
    except Exception as exc:
        logger.exception("Sync: get_food_orders failed")
        err_msg = str(exc).lower()
        
        if "http 401" in err_msg or "http 419" in err_msg:
            return "🔐 Your Swiggy connection was rejected by Swiggy (HTTP 401). Please reconnect."
            
        if "timeout" in err_msg or "network error" in err_msg or "dns" in err_msg:
            return "❌ Swiggy service unreachable. Please try again."
            
        return "❌ Swiggy service unreachable. Please try again."

    if not raw_orders:
        return "No supported Swiggy data is currently available."

    # Step 2: Normalize and save orders with user_id
    normalized = []
    for raw in raw_orders:
        if not isinstance(raw, dict):
            continue
        oid = str(raw.get("order_id") or raw.get("orderId") or raw.get("id", ""))
        if not oid:
            continue

        # Map Swiggy MCP fields to our internal format
        normalized.append({
            "order_id": oid,
            "restaurant_id": str(raw.get("restaurant_id") or raw.get("restaurantId") or ""),
            "restaurant_name": raw.get("restaurant_name") or raw.get("restaurantName") or "",
            "restaurant_locality": raw.get("restaurant_locality") or raw.get("restaurantLocality") or raw.get("restaurantAreaName") or "",
            "restaurant_city_name": raw.get("restaurant_city_name") or raw.get("restaurantCity") or "",
            "restaurant_cuisine": raw.get("restaurant_cuisine") or raw.get("cuisines") or [],
            "order_time": raw.get("order_time") or raw.get("orderedTime") or raw.get("orderTime") or raw.get("created_at") or "",
            "order_total": raw.get("order_total") or raw.get("orderTotal") or raw.get("totalAmount") or 0,
            "order_status": raw.get("order_status") or raw.get("orderStatus") or "Delivered",
            "payment_method": raw.get("payment_method") or raw.get("paymentMethod") or "",
            "delivery_address": raw.get("delivery_address") or {},
            "order_discount": raw.get("order_discount") or raw.get("discount") or 0,
            "order_delivery_charge": raw.get("order_delivery_charge") or raw.get("deliveryCharge") or 0,
            "order_tax": raw.get("order_tax") or raw.get("gst") or 0,
            "order_items": [],
        })
        
        # Try to parse items from Swiggy's action.reorderMeta
        actions = raw.get("actions", [])
        if isinstance(actions, list):
            for action in actions:
                if action.get("type") == "PAST_ORDER_CTA_ENUM_REORDER":
                    meta = action.get("reorderMeta", {})
                    normalized[-1]["order_items"] = meta.get("orderItems", [])
                    break

    if not normalized:
        return "No supported Swiggy data is currently available."

    logger.info("PERSISTING ORDERS")
    with get_session() as session:
        new_count = repository.upsert_orders(normalized, session, user_id=user_id)
        session.commit()

    logger.info("SYNC COMPLETE")
    return "✅ Swiggy data retrieved successfully."



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
        if is_token_expired(telegram_id):
            auth_url = await _build_oauth_url(telegram_id)
            if not auth_url:
                await update.message.reply_text("❌ Sorry, there was an internal error setting up the connection. Please try again later.")
                return

            keyboard = [
                [InlineKeyboardButton("Reconnect Swiggy", url=auth_url)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "🔐 Swiggy connection expired.\n\n"
                "Please reconnect your account to continue using MealMind.",
                reply_markup=reply_markup
            )
            return
            
        keyboard = [
            [InlineKeyboardButton("📊 Insights", callback_data="insights")],
            [InlineKeyboardButton("🍱 Orders", callback_data="orders"),
             InlineKeyboardButton("🏪 Restaurants", callback_data="restaurants")],
            [InlineKeyboardButton("📈 Analytics", callback_data="analytics"),
             InlineKeyboardButton("🔎 Search", callback_data="search")],
            [InlineKeyboardButton("🔄 Sync", callback_data="sync"),
             InlineKeyboardButton("❓ Help", callback_data="help")],
            [InlineKeyboardButton("🍴 Order Food", callback_data="order_food"),
             InlineKeyboardButton("🥦 Instamart", callback_data="order_instamart")],
            [InlineKeyboardButton("🍽️ Book Dineout", callback_data="book_dineout")],
            [InlineKeyboardButton("🛒 Cart", callback_data="cart"),
             InlineKeyboardButton("📦 Active Order", callback_data="active_order")]
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
    auth_url = await _build_oauth_url(telegram_id)
    if not auth_url:
        await update.message.reply_text("❌ Sorry, there was an internal error setting up the connection. Please try again later.")
        return

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
        "🔹 **/sync** - Sync your Swiggy orders\n\n"
        "💡 **Tip**: Use the button menu from /start for quick access!"
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

    from .mcp_server import get_orders

    user_id = get_user_id(telegram_id)
    await update.message.reply_text("🔄 Fetching orders...")

    try:
        result = get_orders(limit=50, user_id=user_id)
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

    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a search query.\n\n"
            "Usage: /search <query>\n"
            "Example: /search pizza"
        )
        return

    query = " ".join(context.args)

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
    """Handle the /sync command.

    If not connected: launch OAuth flow.
    If connected: fetch real orders from Swiggy MCP.
    """
    if not update.effective_user or not update.message:
        return

    telegram_id = str(update.effective_user.id)

    # CASE 1: Not connected -> offer OAuth
    if not is_user_connected(telegram_id):
        auth_url = await _build_oauth_url(telegram_id)
        if not auth_url:
            await update.message.reply_text("❌ Internal error setting up OAuth. Please try again later.")
            return

        keyboard = [
            [InlineKeyboardButton("🔗 Connect Swiggy", url=auth_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🔄 To sync your orders, connect your Swiggy account first:",
            reply_markup=reply_markup
        )
        return

    # CASE 2: Connected -> perform real sync
    await update.message.reply_text("🔄 Syncing your Swiggy orders...")
    result = await _do_sync(telegram_id)
    
    if "expired locally" in result or "rejected by Swiggy" in result:
        auth_url = await _build_oauth_url(telegram_id)
        if auth_url:
            keyboard = [[InlineKeyboardButton("Reconnect Swiggy", url=auth_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(result, reply_markup=reply_markup, parse_mode="Markdown")
            return
            
    await update.message.reply_text(result, parse_mode="Markdown")


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

    user_id = get_user_id(telegram_id)

    # Check authorization for all actions except help and sync
    # (sync handles its own auth check to offer OAuth)
    if query.data not in ("help", "sync") and not is_user_connected(telegram_id):
        await query.message.reply_text(
            "❌ Please connect your Swiggy account first. Use /start to connect."
        )
        return

    # Handle each button action
    try:
        if query.data == "insights":
            from .mcp_server import get_food_insights
            await query.message.reply_text("🔄 Generating insights...")
            result = get_food_insights(user_id=user_id)
            await query.message.reply_text(result, parse_mode="Markdown")

        elif query.data == "orders":
            from .mcp_server import get_orders
            await query.message.reply_text("🔄 Fetching orders...")
            result = get_orders(limit=50, user_id=user_id)
            await query.message.reply_text(result, parse_mode="Markdown")

        elif query.data == "restaurants":
            from .mcp_server import get_restaurants
            await query.message.reply_text("🔄 Fetching restaurants...")
            result = get_restaurants(user_id=user_id)
            await query.message.reply_text(result, parse_mode="Markdown")

        elif query.data == "analytics":
            from .mcp_server import get_analytics
            await query.message.reply_text("🔄 Generating analytics...")
            result = get_analytics(user_id=user_id)
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
            # Same logic as /sync command
            if not is_user_connected(telegram_id):
                auth_url = await _build_oauth_url(telegram_id)
                if not auth_url:
                    await query.message.reply_text("❌ Internal error setting up OAuth. Please try again later.")
                    return
                keyboard = [
                    [InlineKeyboardButton("🔗 Connect Swiggy", url=auth_url)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.reply_text(
                    "🔄 To sync your orders, connect your Swiggy account first:",
                    reply_markup=reply_markup
                )
            else:
                await query.message.reply_text("🔄 Syncing your Swiggy orders...")
                result = await _do_sync(telegram_id)
                
                if "expired locally" in result or "rejected by Swiggy" in result:
                    auth_url = await _build_oauth_url(telegram_id)
                    if auth_url:
                        keyboard = [[InlineKeyboardButton("Reconnect Swiggy", url=auth_url)]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await query.message.reply_text(result, reply_markup=reply_markup, parse_mode="Markdown")
                        return
                        
                await query.message.reply_text(result, parse_mode="Markdown")

        elif query.data == "help":
            help_text = (
                "📚 **MealMind Commands**\n\n"
                "🔹 **/start** - Show main menu\n"
                "🔹 **/help** - Show this help message\n"
                "🔹 **/insights** - Get personalized food insights\n"
                "🔹 **/orders** - View recent orders\n"
                "🔹 **/restaurants** - List your favorite restaurants\n"
                "🔹 **/analytics** - Get spending and ordering analytics\n"
                "🔹 **/search <query>** - Search orders by restaurant, cuisine, or item\n"
                "🔹 **/sync** - Sync your Swiggy orders\n\n"
                "💡 **Tip**: Use the button menu from /start for quick access!"
            )
            await query.message.reply_text(help_text, parse_mode="Markdown")

    except Exception as e:
        logger.exception(f"Failed to handle button callback: {query.data}")
        await query.message.reply_text(
            f"❌ Sorry, I couldn't process your request right now. Please try again later."
        )


# -------------------------------------------------------------------------
# Command: /disconnect (Development Only)
# -------------------------------------------------------------------------

async def disconnect_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /disconnect command for local development testing."""
    if os.getenv("ENVIRONMENT") != "development":
        return

    if not update.effective_user or not update.message:
        return

    telegram_id = str(update.effective_user.id)
    
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        if user:
            conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
            if conn:
                session.delete(conn)
                session.commit()
    
    await update.message.reply_text("Swiggy disconnected. Use /start to connect again.")


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

    from telegram.ext import CallbackQueryHandler
    from src.food_ordering_flow import get_order_flow_handler, handle_cart_callback, handle_active_order_callback
    from src.instamart_ordering_flow import get_instamart_flow_handler
    from src.dineout_booking_flow import get_dineout_flow_handler
    
    # Must be added BEFORE standard CommandHandlers so that its state machine
    # can intercept commands like /start as fallbacks when active.
    app.add_handler(get_order_flow_handler())
    app.add_handler(get_instamart_flow_handler())
    app.add_handler(get_dineout_flow_handler())

    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("insights", insights_command))
    app.add_handler(CommandHandler("orders", orders_command))
    app.add_handler(CommandHandler("restaurants", restaurants_command))
    app.add_handler(CommandHandler("analytics", analytics_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("sync", sync_command))
    
    if os.getenv("ENVIRONMENT") == "development":
        app.add_handler(CommandHandler("disconnect", disconnect_command))

    app.add_handler(CallbackQueryHandler(handle_cart_callback, pattern="^cart$"))
    app.add_handler(CallbackQueryHandler(handle_active_order_callback, pattern="^active_order$"))

    # Register callback query handler for inline buttons
    app.add_handler(CallbackQueryHandler(button_callback))

    return app
