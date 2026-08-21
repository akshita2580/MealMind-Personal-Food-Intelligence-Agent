import logging
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters, CommandHandler

from src.security import decrypt_token
from src.database import get_session
from src.models import SwiggyConnection
from sqlmodel import select
from src import swiggy_mcp_client
from src import swiggy_dineout_mcp

from src.telegram_bot import get_user_access_token

logger = logging.getLogger(__name__)

(
    SELECT_DO_ADDRESS,
    SEARCH_DINING,
    SELECT_DINING_VENUE,
    SELECT_DATE_TIME,
    SELECT_GUEST_COUNT,
    CONFIRM_BOOKING
) = range(20, 26)

async def cancel_do_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Dineout booking cancelled.")
    
    context.user_data.pop("do_flow", None)
    
    if update.message and update.message.text and update.message.text.startswith("/start"):
        from src.telegram_bot import start_command
        await start_command(update, context)
    elif not query:
        await update.message.reply_text("Dineout booking cancelled. Use /start to return to the main menu.")
        
    return ConversationHandler.END

async def start_dineout_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    telegram_id = str(update.effective_user.id)
    token = get_user_access_token(telegram_id)
    
    try:
        addresses = await swiggy_mcp_client.get_addresses(token)
        if not addresses:
            await query.edit_message_text("❌ No saved addresses found on your Swiggy account.")
            return ConversationHandler.END
            
        context.user_data["do_flow"] = {"token": token, "addresses": addresses}
        
        keyboard = []
        for a in addresses:
            aid = str(a.get("id") or a.get("addressId") or a.get("address_id", ""))
            if not aid: continue
            
            text = a.get("addressTag") or a.get("addressCategory") or a.get("addressLine") or "Unknown Address"
            if len(text) > 30: text = text[:27] + "..."
            keyboard.append([InlineKeyboardButton(text, callback_data=f"doaddr_{aid}")])
            
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_do")])
        
        await query.edit_message_text(
            "🍽️ *Dineout* \n\nPlease select your current location for finding restaurants:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return SELECT_DO_ADDRESS
    except Exception as e:
        logger.exception("Failed to start Dineout flow")
        await query.edit_message_text(f"❌ Error starting Dineout: {e}")
        return ConversationHandler.END

async def handle_do_address_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    addr_id = query.data.replace("doaddr_", "")
    
    # Store lat/lng for slots API
    addresses = context.user_data["do_flow"].get("addresses", [])
    addr = next((a for a in addresses if str(a.get("id", "")) == addr_id), None)
    
    lat = addr.get("latitude") or 0.0 if addr else 0.0
    lng = addr.get("longitude") or 0.0 if addr else 0.0
    
    context.user_data["do_flow"]["address_id"] = addr_id
    context.user_data["do_flow"]["lat"] = lat
    context.user_data["do_flow"]["lng"] = lng
    
    await query.edit_message_text(
        "Location selected!\n\n🔍 Please type the name of the restaurant, vibe, or cuisine you want to search for:"
    )
    return SEARCH_DINING

async def handle_dining_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    search_query = update.message.text
    token = context.user_data["do_flow"]["token"]
    addr_id = context.user_data["do_flow"]["address_id"]
    
    msg = await update.message.reply_text(f"🔍 Searching Dineout for '{search_query}'...")
    
    try:
        results = await swiggy_dineout_mcp.search_restaurants_dineout(token, search_query, address_id=addr_id)
        restaurants = results.get("restaurants", []) if isinstance(results, dict) else []
        
        if not restaurants:
            await msg.edit_text("No restaurants found. Please type another search term:")
            return SEARCH_DINING
            
        keyboard = []
        for rest in restaurants[:15]:
            rid = rest.get("id")
            name = rest.get("name", "Unknown")
            if len(name) > 30: name = name[:27] + "..."
            
            keyboard.append([InlineKeyboardButton(name, callback_data=f"dorest_{rid}")])
            
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_do")])
        
        await msg.edit_text(
            "🍽️ Select a restaurant to book:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_DINING_VENUE
    except Exception as e:
        logger.exception("Dineout search failed")
        await msg.edit_text(f"❌ Search failed: {e}\n\nPlease try another search term:")
        return SEARCH_DINING

async def handle_do_venue_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    rest_id = query.data.replace("dorest_", "")
    context.user_data["do_flow"]["restaurant_id"] = rest_id
    
    token = context.user_data["do_flow"]["token"]
    lat = context.user_data["do_flow"]["lat"]
    lng = context.user_data["do_flow"]["lng"]
    
    # Query today
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    await query.edit_message_text("⏳ Fetching available slots...")
    
    try:
        slots_resp = await swiggy_dineout_mcp.get_available_slots(token, rest_id, today, lat, lng)
        slots = slots_resp.get("slots", []) if isinstance(slots_resp, dict) else []
        
        if not slots:
            await query.edit_message_text("❌ No available slots found for this restaurant today.")
            return ConversationHandler.END
            
        keyboard = []
        # Group by day / just show the next 10 slots
        count = 0
        for slot in slots:
            if count >= 20: break
            deals = slot.get("deals", [])
            if not deals: continue
            
            deal = deals[0]
            slot_id = deal.get("slotId")
            item_id = deal.get("itemId")
            res_time = slot.get("reservationTime")
            time_str = slot.get("timeString", "Unknown Time")
            
            if not slot_id or not item_id or not res_time: continue
            
            cb_data = f"doslt_{slot_id}_{item_id}_{res_time}"
            keyboard.append([InlineKeyboardButton(time_str, callback_data=cb_data)])
            count += 1
            
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_do")])
        
        await query.edit_message_text(
            "📅 *Select a Time Slot:*\n\n(Showing available slots for upcoming days)",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return SELECT_DATE_TIME
    except Exception as e:
        logger.exception("Slot fetch failed")
        await query.edit_message_text(f"❌ Failed to fetch slots: {e}")
        return ConversationHandler.END

async def handle_do_slot_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    data = query.data.replace("doslt_", "")
    parts = data.split("_")
    if len(parts) != 3:
        await query.edit_message_text("❌ Invalid slot selection.")
        return ConversationHandler.END
        
    context.user_data["do_flow"]["slot_id"] = int(parts[0])
    context.user_data["do_flow"]["item_id"] = parts[1]
    context.user_data["do_flow"]["reservation_time"] = int(parts[2])
    
    keyboard = []
    for i in range(1, 11):
        keyboard.append([InlineKeyboardButton(f"{i} Guests", callback_data=f"doguest_{i}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_do")])
    
    await query.edit_message_text(
        "👥 *How many guests?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return SELECT_GUEST_COUNT

async def handle_do_guest_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    guests = int(query.data.replace("doguest_", ""))
    context.user_data["do_flow"]["guests"] = guests
    
    # Show confirmation
    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Book", callback_data="doconfirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_do")]
    ]
    
    await query.edit_message_text(
        f"🍽️ *Booking Summary*\n\n"
        f"Guests: {guests}\n"
        f"⚠️ Please explicitly confirm to finalize this booking.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CONFIRM_BOOKING

async def confirm_do_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("⏳ Booking table...")
    
    token = context.user_data["do_flow"]["token"]
    rest_id = context.user_data["do_flow"]["restaurant_id"]
    slot_id = context.user_data["do_flow"]["slot_id"]
    item_id = context.user_data["do_flow"]["item_id"]
    res_time = context.user_data["do_flow"]["reservation_time"]
    guests = context.user_data["do_flow"]["guests"]
    lat = context.user_data["do_flow"]["lat"]
    lng = context.user_data["do_flow"]["lng"]
    
    try:
        result = await swiggy_dineout_mcp.book_table(token, rest_id, slot_id, item_id, res_time, guests, lat, lng)
        status = result.get("status", "Unknown")
        if status in ["CONFIRMED", "SUCCESS", "PLACED", "success"]:
            await query.edit_message_text("✅ Table Booked Successfully!")
        else:
            await query.edit_message_text(f"⚠️ Booking status: {status}\nResult: {result}")
    except Exception as e:
        logger.exception("Booking failed")
        await query.edit_message_text(f"❌ Failed to book table: {e}")
        
    context.user_data.pop("do_flow", None)
    return ConversationHandler.END

def get_dineout_flow_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_dineout_flow, pattern="^book_dineout$")],
        states={
            SELECT_DO_ADDRESS: [
                CallbackQueryHandler(cancel_do_flow, pattern="^cancel_do$"),
                CallbackQueryHandler(handle_do_address_selection, pattern="^doaddr_")
            ],
            SEARCH_DINING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dining_search)
            ],
            SELECT_DINING_VENUE: [
                CallbackQueryHandler(cancel_do_flow, pattern="^cancel_do$"),
                CallbackQueryHandler(handle_do_venue_selection, pattern="^dorest_")
            ],
            SELECT_DATE_TIME: [
                CallbackQueryHandler(cancel_do_flow, pattern="^cancel_do$"),
                CallbackQueryHandler(handle_do_slot_selection, pattern="^doslt_")
            ],
            SELECT_GUEST_COUNT: [
                CallbackQueryHandler(cancel_do_flow, pattern="^cancel_do$"),
                CallbackQueryHandler(handle_do_guest_selection, pattern="^doguest_")
            ],
            CONFIRM_BOOKING: [
                CallbackQueryHandler(cancel_do_flow, pattern="^cancel_do$"),
                CallbackQueryHandler(confirm_do_booking, pattern="^doconfirm$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_do_flow),
            CommandHandler("start", cancel_do_flow)
        ],
        per_message=False,
    )
