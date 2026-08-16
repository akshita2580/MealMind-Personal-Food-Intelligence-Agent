"""
Telegram Bot integration for FoodIQ.
Handles /start and Swiggy OAuth account linking.
"""
import os
import logging
import urllib.parse
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

from .database import get_session
from sqlmodel import select
from .models import OAuthState, User, SwiggyConnection
from .security import generate_oauth_state, generate_pkce_verifier, generate_pkce_challenge

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    if not update.effective_user or not update.message:
        return
        
    telegram_id = str(update.effective_user.id)
    
    # Check if already connected
    is_connected = False
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        if user:
            conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
            if conn and conn.status == "CONNECTED":
                is_connected = True
                
    if is_connected:
        await update.message.reply_text(
            "👋 Welcome back to FoodIQ!\n\n"
            "Your Swiggy account is already connected. "
            "You can use FoodIQ to understand your food habits and get personalized insights."
        )
        return
        
    # Generate OAuth state and PKCE verifier
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    challenge = generate_pkce_challenge(verifier)
    
    # Store state
    with get_session() as session:
        now_utc = datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(minutes=15)
        
        logger.info(f"OAuth state created:")
        logger.info(f"  created_at: {now_utc}")
        logger.info(f"  expires_at: {expires_at}")
        logger.info(f"  lifetime_seconds: {(expires_at - now_utc).total_seconds()}")
        
        oauth_state = OAuthState(
            state=state,
            telegram_id=telegram_id,
            code_verifier=verifier,
            expires_at=expires_at
        )
        session.add(oauth_state)
        session.commit()
        
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
    
    keyboard = [
        [InlineKeyboardButton("Connect Swiggy", url=auth_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Welcome to FoodIQ!\n\n"
        "Connect your Swiggy account to get personalized food insights.",
        reply_markup=reply_markup
    )

def build_telegram_app() -> Application | None:
    """Build the Telegram application. Returns None if token is missing."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram bot will not start.")
        return None
        
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    return app
