import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters, CommandHandler

from src.security import decrypt_token
from src.database import get_session
from src.models import SwiggyConnection
from sqlmodel import select
from src import swiggy_mcp_client
from src import swiggy_instamart_mcp

from src.telegram_bot import get_user_access_token

logger = logging.getLogger(__name__)

(
    SELECT_IM_ADDRESS,
    SEARCH_GROCERY,
    SELECT_GROCERY_ITEM,
    VIEW_IM_CART,
    SELECT_IM_PAYMENT,
    IM_PAYMENT_PENDING
) = range(10, 16)

async def cancel_im_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Instamart order cancelled.")
    
    context.user_data.pop("im_order_flow", None)
    
    if update.message and update.message.text and update.message.text.startswith("/start"):
        from src.telegram_bot import start_command
        await start_command(update, context)
    elif not query:
        await update.message.reply_text("Instamart order cancelled. Use /start to return to the main menu.")
        
    return ConversationHandler.END

async def start_instamart_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    telegram_id = str(update.effective_user.id)
    token = get_user_access_token(telegram_id)
    
    try:
        addresses = await swiggy_mcp_client.get_addresses(token)
        if not addresses:
            await query.edit_message_text("❌ No saved addresses found on your Swiggy account.")
            return ConversationHandler.END
            
        context.user_data["im_order_flow"] = {"token": token, "cart_items": []}
        
        keyboard = []
        for a in addresses:
            aid = str(a.get("id") or a.get("addressId") or a.get("address_id", ""))
            if not aid: continue
            
            text = a.get("addressTag") or a.get("addressCategory") or a.get("addressLine") or "Unknown Address"
            if len(text) > 30: text = text[:27] + "..."
            keyboard.append([InlineKeyboardButton(text, callback_data=f"imaddr_{aid}")])
            
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_im_order")])
        
        await query.edit_message_text(
            "🥦 *Instamart* \n\nPlease select a delivery address:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return SELECT_IM_ADDRESS
    except Exception as e:
        logger.exception("Failed to start Instamart flow")
        await query.edit_message_text(f"❌ Error starting Instamart: {e}")
        return ConversationHandler.END

async def handle_im_address_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    addr_id = query.data.replace("imaddr_", "")
    context.user_data["im_order_flow"]["address_id"] = addr_id
    
    await query.edit_message_text(
        "Address selected!\n\n🔍 Please type the name of the grocery product you want to search for:"
    )
    return SEARCH_GROCERY

async def handle_grocery_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    search_query = update.message.text
    token = context.user_data["im_order_flow"]["token"]
    addr_id = context.user_data["im_order_flow"]["address_id"]
    
    msg = await update.message.reply_text(f"🔍 Searching Instamart for '{search_query}'...")
    
    try:
        results = await swiggy_instamart_mcp.search_products(token, addr_id, search_query)
        products = results.get("products", []) if isinstance(results, dict) else []
        
        if not products:
            await msg.edit_text("No products found. Please type another search term:")
            return SEARCH_GROCERY
            
        # Flatten variations
        items = []
        for prod in products:
            for var in prod.get("variations", []):
                items.append({
                    "spinId": var.get("spinId"),
                    "name": f"{prod.get('displayName')} - {var.get('quantityDescription')}",
                    "price": var.get("price", {}).get("offerPrice", var.get("price", {}).get("mrp", 0))
                })
        
        if not items:
            await msg.edit_text("No items available. Please try another search term:")
            return SEARCH_GROCERY
            
        keyboard = []
        for item in items[:50]:
            spin_id = item["spinId"]
            name = item["name"]
            price = item["price"]
            if len(name) > 30: name = name[:27] + "..."
            
            keyboard.append([InlineKeyboardButton(f"{name} - ₹{price}", callback_data=f"imitem_{spin_id}")])
            
        keyboard.append([InlineKeyboardButton("🛒 View Cart", callback_data="view_im_cart")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_im_order")])
        
        await msg.edit_text(
            "🥦 Select an item to add to cart (showing top 50):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_GROCERY_ITEM
    except Exception as e:
        logger.exception("Grocery search failed")
        await msg.edit_text(f"❌ Search failed: {e}\n\nPlease try another search term:")
        return SEARCH_GROCERY

async def handle_im_item_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "view_im_cart":
        return await show_im_cart(update, context)
        
    spin_id = query.data.replace("imitem_", "")
    
    cart_items = context.user_data["im_order_flow"].get("cart_items", [])
    
    existing = next((i for i in cart_items if i.get("spinId") == spin_id), None)
    if existing:
        existing["quantity"] += 1
    else:
        cart_items.append({"spinId": spin_id, "quantity": 1})
        
    context.user_data["im_order_flow"]["cart_items"] = cart_items
    
    token = context.user_data["im_order_flow"]["token"]
    addr_id = context.user_data["im_order_flow"]["address_id"]
    
    await query.edit_message_text("🛒 Updating Instamart cart...")
    try:
        await swiggy_instamart_mcp.update_cart(token, addr_id, cart_items)
        return await show_im_cart(update, context)
    except Exception as e:
        logger.exception("Instamart Cart update failed")
        await query.edit_message_text(f"❌ Cart update failed: {e}")
        return ConversationHandler.END

async def show_im_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    token = context.user_data["im_order_flow"]["token"]
    addr_id = context.user_data["im_order_flow"]["address_id"]
    
    try:
        cart = await swiggy_instamart_mcp.get_cart(token, addr_id)
        
        if isinstance(cart, dict) and cart.get("success") is False:
            await query.edit_message_text(f"🛒 Your Instamart cart is empty or out of stock.")
            return ConversationHandler.END
            
        items = cart.get("items", []) if isinstance(cart, dict) else []
        total = cart.get("billBreakdown", {}).get("toPay", {}).get("value", "₹0")
        
        if not items:
            await query.edit_message_text("🛒 Your Instamart cart is empty.")
            return ConversationHandler.END
            
        msg = "🛒 *Your Instamart Cart*\n\n"
        for item in items:
            msg += f"• {item.get('quantity', 1)}x {item.get('itemName', 'Item')} ({item.get('itemVariant', '')}) - ₹{item.get('discountedFinalPrice', 0)}\n"
            
        msg += f"\n*Total:* {total}"
        
        keyboard = [
            [InlineKeyboardButton("💳 Proceed to Payment", callback_data="im_proceed_payment")],
            [InlineKeyboardButton("❌ Cancel Order", callback_data="cancel_im_order")]
        ]
        
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return VIEW_IM_CART
    except Exception as e:
        logger.exception("Instamart cart fetch failed")
        await query.edit_message_text(f"❌ Error fetching cart: {e}")
        return ConversationHandler.END

async def proceed_to_im_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    token = context.user_data["im_order_flow"]["token"]
    addr_id = context.user_data["im_order_flow"]["address_id"]
    
    try:
        cart = await swiggy_instamart_mcp.get_cart(token, addr_id)
        total = cart.get("billBreakdown", {}).get("toPay", {}).get("value", "₹0")
        
        opts = await swiggy_instamart_mcp.get_payment_options(token, addr_id)
        methods = opts.get("paymentMethods", [])
        
        msg = f"💳 *Select Payment Method*\n\nCart Total: {total}\n\n"
        msg += "⚠️ *Please confirm your payment method to place the Instamart order.*"
        
        keyboard = []
        for method in methods:
            if method["type"] == "Cash":
                keyboard.append([InlineKeyboardButton("💵 Cash on Delivery", callback_data="impay_Cash")])
            elif method["type"] == "UPI":
                apps = method.get("intentApps", [])
                for app in apps:
                    keyboard.append([InlineKeyboardButton(f"📱 UPI - {app['name']}", callback_data=f"impay_UPI_{app['id']}")])
        
        if not keyboard:
            keyboard.append([InlineKeyboardButton("💵 Cash on Delivery (Fallback)", callback_data="impay_Cash")])
            
        keyboard.append([InlineKeyboardButton("❌ Cancel Order", callback_data="cancel_im_order")])
        
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return SELECT_IM_PAYMENT
    except Exception as e:
        logger.exception("Instamart payment options failed")
        await query.edit_message_text(f"❌ Error loading payment options: {e}")
        return ConversationHandler.END

async def confirm_im_payment_and_place_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    token = context.user_data["im_order_flow"]["token"]
    addr_id = context.user_data["im_order_flow"]["address_id"]
    
    data = query.data.replace("impay_", "")
    
    payment_method = "Cash"
    intent_app = ""
    if data.startswith("UPI_"):
        payment_method = "UPI"
        intent_app = data.replace("UPI_", "")
    elif data == "Cash":
        payment_method = "Cash"
        
    await query.edit_message_text("🔄 Placing your Instamart order...")
    
    try:
        result = await swiggy_instamart_mcp.checkout(token, addr_id, payment_method)
        
        if result.get("status") == "PENDING_PAYMENT":
            paas_id = result.get("paasId")
            order_id = result.get("orderId")
            context.user_data["im_order_flow"]["paas_id"] = paas_id
            context.user_data["im_order_flow"]["order_id"] = order_id
            
            keyboard = [[InlineKeyboardButton("Check Payment Status", callback_data="im_check_upi_status")]]
            await query.edit_message_text(
                f"⏳ *Payment Pending*\n\nPlease complete the payment on your UPI app.\nOrder ID: {order_id}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return IM_PAYMENT_PENDING
            
        elif result.get("status") in ["PLACED", "CONFIRMED", "success", "SUCCESS"]:
            await query.edit_message_text("✅ Instamart Order Placed Successfully!")
            context.user_data.pop("im_order_flow", None)
            return ConversationHandler.END
        else:
            await query.edit_message_text(f"⚠️ Order status: {result.get('status', 'Unknown')}\nResult: {result}")
            return ConversationHandler.END
            
    except Exception as e:
        logger.exception("Instamart order placement failed")
        await query.edit_message_text(f"❌ Failed to place Instamart order: {e}")
        return ConversationHandler.END

async def check_im_upi_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    token = context.user_data["im_order_flow"]["token"]
    addr_id = context.user_data["im_order_flow"]["address_id"]
    paas_id = context.user_data["im_order_flow"].get("paas_id")
    order_id = context.user_data["im_order_flow"].get("order_id")
    
    try:
        status_resp = await swiggy_instamart_mcp.check_payment_status(token, paas_id, order_id, addr_id)
        status = status_resp.get("status")
        
        if status in ["SUCCESS", "PAID"]:
            await query.edit_message_text("✅ Payment Successful! Confirming order...")
            await swiggy_instamart_mcp.confirm_order(token, order_id, addr_id)
            await query.edit_message_text("✅ Instamart Order Placed Successfully!")
            context.user_data.pop("im_order_flow", None)
            return ConversationHandler.END
        elif status == "FAILED":
            await query.edit_message_text("❌ Payment Failed. Order was not placed.")
            context.user_data.pop("im_order_flow", None)
            return ConversationHandler.END
        else:
            keyboard = [[InlineKeyboardButton("Check Status Again", callback_data="im_check_upi_status")]]
            await query.edit_message_text(
                f"⏳ Payment is still {status}. Please check your UPI app.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return IM_PAYMENT_PENDING
            
    except Exception as e:
        logger.exception("Instamart payment status check failed")
        await query.edit_message_text(f"❌ Error checking payment status: {e}")
        return ConversationHandler.END

def get_instamart_flow_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_instamart_flow, pattern="^order_instamart$")],
        states={
            SELECT_IM_ADDRESS: [
                CallbackQueryHandler(cancel_im_flow, pattern="^cancel_im_order$"),
                CallbackQueryHandler(handle_im_address_selection, pattern="^imaddr_")
            ],
            SEARCH_GROCERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_grocery_search)
            ],
            SELECT_GROCERY_ITEM: [
                CallbackQueryHandler(cancel_im_flow, pattern="^cancel_im_order$"),
                CallbackQueryHandler(handle_im_item_selection, pattern="^view_im_cart$"),
                CallbackQueryHandler(handle_im_item_selection, pattern="^imitem_")
            ],
            VIEW_IM_CART: [
                CallbackQueryHandler(cancel_im_flow, pattern="^cancel_im_order$"),
                CallbackQueryHandler(proceed_to_im_payment, pattern="^im_proceed_payment$")
            ],
            SELECT_IM_PAYMENT: [
                CallbackQueryHandler(cancel_im_flow, pattern="^cancel_im_order$"),
                CallbackQueryHandler(confirm_im_payment_and_place_order, pattern="^impay_")
            ],
            IM_PAYMENT_PENDING: [
                CallbackQueryHandler(cancel_im_flow, pattern="^cancel_im_order$"),
                CallbackQueryHandler(check_im_upi_status, pattern="^im_check_upi_status$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_im_flow),
            CommandHandler("start", cancel_im_flow)
        ],
        per_message=False,
    )
