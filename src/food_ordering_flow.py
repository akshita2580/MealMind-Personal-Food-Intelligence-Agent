import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from src import swiggy_mcp_client
from src.telegram_bot import get_user_access_token

logger = logging.getLogger(__name__)

(
    SELECT_ADDRESS, SEARCH_RESTAURANT, SELECT_RESTAURANT, SELECT_MENU_ITEM, 
    CUSTOMIZE_ITEM, VIEW_CART, SELECT_COUPON, SELECT_PAYMENT, CONFIRM_ORDER, 
    PAYMENT_PENDING, ORDER_PLACED, TRACKING
) = range(12)

async def cancel_order_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Ordering cancelled.")
    
    context.user_data.pop("order_flow", None)
    
    if update.message and update.message.text and update.message.text.startswith("/start"):
        from src.telegram_bot import start_command
        await start_command(update, context)
    elif not query:
        await update.message.reply_text("Ordering cancelled. Use /start to return to the main menu.")
        
    return ConversationHandler.END

async def start_order_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    telegram_id = str(update.effective_user.id)
    token = get_user_access_token(telegram_id)
    if not token:
        await query.edit_message_text("Please connect Swiggy first using /start")
        return ConversationHandler.END
        
    context.user_data["order_flow"] = {"token": token}
    await query.edit_message_text("🔄 Fetching your saved addresses...")
    
    try:
        addresses = await swiggy_mcp_client.get_addresses(token)
        if not addresses:
            await query.edit_message_text("No addresses found on your Swiggy account.")
            return ConversationHandler.END
            
        keyboard = []
        for a in addresses:
            aid = str(a.get("id") or a.get("addressId") or a.get("address_id", ""))
            if not aid: continue
            
            # Swiggy uses addressTag, addressCategory, or addressLine
            text = a.get("addressTag") or a.get("addressCategory") or a.get("addressLine") or "Unknown Address"
            if len(text) > 30: text = text[:27] + "..."
            keyboard.append([InlineKeyboardButton(text, callback_data=f"addr_{aid}")])
            
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_order")])
        
        await query.edit_message_text(
            "📍 Please select a delivery address:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_ADDRESS
    except Exception as e:
        logger.exception("Failed to get addresses")
        await query.edit_message_text(f"❌ Error: {e}")
        return ConversationHandler.END

async def handle_address_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    addr_id = query.data.replace("addr_", "")
    context.user_data["order_flow"]["address_id"] = addr_id
    
    await query.edit_message_text(
        "Address selected!\n\n🔍 Please type the name of a restaurant or dish you want to search for:"
    )
    return SEARCH_RESTAURANT

async def handle_restaurant_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    search_query = update.message.text
    token = context.user_data["order_flow"]["token"]
    addr_id = context.user_data["order_flow"]["address_id"]
    
    msg = await update.message.reply_text(f"🔍 Searching for '{search_query}'...")
    
    try:
        results = await swiggy_mcp_client.search_restaurants(token, addr_id, search_query)
        restaurants = results.get("restaurants", []) if isinstance(results, dict) else []
        
        if not restaurants:
            await msg.edit_text("No restaurants found. Please try another search term:")
            return SEARCH_RESTAURANT
            
        keyboard = []
        for r in restaurants[:10]: # show top 10
            rid = str(r.get("id", ""))
            name = r.get("name", "Unknown")
            keyboard.append([InlineKeyboardButton(name, callback_data=f"rest_{rid}")])
            
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_order")])
        
        await msg.edit_text(
            "🏪 Select a restaurant:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_RESTAURANT
    except Exception as e:
        logger.exception("Search failed")
        await msg.edit_text(f"❌ Search failed: {e}\nTry again:")
        return SEARCH_RESTAURANT

async def handle_restaurant_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    rest_id = query.data.replace("rest_", "")
    context.user_data["order_flow"]["restaurant_id"] = rest_id
    token = context.user_data["order_flow"]["token"]
    addr_id = context.user_data["order_flow"]["address_id"]
    
    await query.edit_message_text("📋 Fetching menu...")
    
    try:
        menu = await swiggy_mcp_client.get_restaurant_menu(token, addr_id, rest_id)
        
        items = []
        if isinstance(menu, dict) and "categories" in menu:
            for cat in menu["categories"]:
                if "items" in cat:
                    items.extend(cat["items"])
        elif isinstance(menu, dict) and "items" in menu:
            items = menu["items"]
        
        if not items:
            await query.edit_message_text("Menu is empty.")
            return ConversationHandler.END
            
        keyboard = []
        for item in items[:50]:  # Increased from 15 to 50
            iid = str(item.get("id", ""))
            name = item.get("name", "Unknown")
            
            # Use defaultPrice if price is missing or 0
            raw_price = item.get("price") or item.get("defaultPrice") or 0
            
            # Swiggy MCP usually returns rupees directly (e.g., 119), but occasionally paisa.
            # If it's > 10000, it's likely paisa. For safety, if it's > 10000, divide by 100.
            # But normally it's just rupees.
            price = raw_price / 100 if raw_price > 10000 else raw_price
            
            if len(name) > 25: name = name[:22] + "..."
            
            keyboard.append([InlineKeyboardButton(f"{name} - ₹{price}", callback_data=f"item_{iid}")])
            
        keyboard.append([InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_order")])
        
        await query.edit_message_text(
            "🍔 Select an item to add to cart (showing top 50):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_MENU_ITEM
    except Exception as e:
        logger.exception("Menu fetch failed")
        await query.edit_message_text(f"❌ Failed to fetch menu: {e}")
        return ConversationHandler.END

async def handle_menu_item_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "view_cart":
        return await show_cart(update, context)
        
    item_id = query.data.replace("item_", "")
    
    # Very basic cart implementation - just add 1 quantity of the item
    cart_items = context.user_data["order_flow"].get("cart_items", [])
    
    # Check if item already exists
    existing = next((i for i in cart_items if i.get("menu_item_id") == item_id), None)
    if existing:
        existing["quantity"] += 1
    else:
        cart_items.append({"menu_item_id": item_id, "quantity": 1})
        
    context.user_data["order_flow"]["cart_items"] = cart_items
    
    # Auto-update Swiggy cart
    token = context.user_data["order_flow"]["token"]
    rest_id = context.user_data["order_flow"]["restaurant_id"]
    addr_id = context.user_data["order_flow"]["address_id"]
    
    await query.edit_message_text("🛒 Updating cart on Swiggy...")
    try:
        await swiggy_mcp_client.update_food_cart(token, rest_id, cart_items, addr_id)
        return await show_cart(update, context)
    except Exception as e:
        logger.exception("Cart update failed")
        await query.edit_message_text(f"❌ Cart update failed: {e}")
        return ConversationHandler.END

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    token = context.user_data["order_flow"]["token"]
    addr_id = context.user_data["order_flow"]["address_id"]
    
    try:
        cart_resp = await swiggy_mcp_client.get_food_cart(token, addr_id)
        
        # Swiggy sometimes wraps the cart in 'data'
        cart = cart_resp.get("data") if (isinstance(cart_resp, dict) and "data" in cart_resp) else cart_resp
        
        items = cart.get("items", []) if isinstance(cart, dict) else []
        
        pricing = cart.get("pricing", {}) if isinstance(cart, dict) else {}
        total = pricing.get("to_pay") or cart.get("cartTotal", 0) or 0
        total = total / 100 if total > 10000 else total
        
        if not items:
            await query.edit_message_text("🛒 Your cart is empty.")
            return ConversationHandler.END
            
        msg = "🛒 *Your Cart*\n\n"
        for item in items:
            raw_p = item.get("final_price") or item.get("subtotal") or item.get("price") or item.get("defaultPrice") or 0
            p = raw_p / 100 if raw_p > 10000 else raw_p
            msg += f"• {item.get('quantity', 1)}x {item.get('name', 'Item')} - ₹{p}\n"
            
        msg += f"\n*Total:* ₹{total}"
        
        keyboard = [
            [InlineKeyboardButton("💳 Proceed to Payment", callback_data="proceed_payment")],
            [InlineKeyboardButton("❌ Cancel Order", callback_data="cancel_order")]
        ]
        
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return VIEW_CART
    except Exception as e:
        logger.exception("Get cart failed")
        await query.edit_message_text(f"❌ Failed to get cart: {e}")
        return ConversationHandler.END

async def proceed_to_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    token = context.user_data["order_flow"]["token"]
    addr_id = context.user_data["order_flow"]["address_id"]
    
    # 5. check total < ₹1000
    try:
        cart_resp = await swiggy_mcp_client.get_food_cart(token, addr_id)
        cart = cart_resp.get("data") if (isinstance(cart_resp, dict) and "data" in cart_resp) else cart_resp
        
        pricing = cart.get("pricing", {}) if isinstance(cart, dict) else {}
        total = pricing.get("to_pay") or cart.get("cartTotal", 0) or 0
        total = total / 100 if total > 10000 else total
        
        if total > 1000:
            await query.edit_message_text(f"❌ Cart total ₹{total} exceeds the ₹1000 limit for Swiggy Builders Club.")
            return ConversationHandler.END
            
        # Call get_payment_options
        pay_opts = await swiggy_mcp_client.get_payment_options(token, addr_id)
        
        keyboard = [
            [InlineKeyboardButton("Cash on Delivery", callback_data="pay_Cash")],
            [InlineKeyboardButton("UPI", callback_data="pay_UPI")],
            [InlineKeyboardButton("❌ Cancel Order", callback_data="cancel_order")]
        ]
        
        msg = f"💳 *Select Payment Method*\n\nCart Total: ₹{total}\n\n"
        msg += "⚠️ *Please confirm your payment method to place the order.*"
        
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_PAYMENT
    except Exception as e:
        logger.exception("Payment options failed")
        await query.edit_message_text(f"❌ Failed to load payment options: {e}")
        return ConversationHandler.END

async def confirm_payment_and_place_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    method = query.data.replace("pay_", "")
    token = context.user_data["order_flow"]["token"]
    addr_id = context.user_data["order_flow"]["address_id"]
    
    await query.edit_message_text(f"⏳ Placing order using {method}...")
    
    try:
        order_res = await swiggy_mcp_client.place_food_order(token, addr_id, method)
        
        order_id = order_res.get("orderId") if isinstance(order_res, dict) else None
        status = order_res.get("status") if isinstance(order_res, dict) else None
        
        if status == "PENDING_PAYMENT" and method == "UPI":
            paas_id = order_res.get("paasId")
            context.user_data["order_flow"]["order_id"] = order_id
            context.user_data["order_flow"]["paas_id"] = paas_id
            
            keyboard = [[InlineKeyboardButton("Check Status", callback_data="check_upi_status")]]
            await query.edit_message_text(
                f"UPI Order placed! (Order ID: {order_id})\n\nStatus: PENDING_PAYMENT\n\nPlease approve the request in your UPI app.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return PAYMENT_PENDING
            
        await query.edit_message_text(f"✅ Order Placed Successfully!\n\nOrder ID: {order_id}\nStatus: {status}")
        return ConversationHandler.END
        
    except Exception as e:
        logger.exception("Order placement failed")
        await query.edit_message_text(f"❌ Order placement failed: {e}")
        return ConversationHandler.END

async def check_upi_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    token = context.user_data["order_flow"]["token"]
    addr_id = context.user_data["order_flow"]["address_id"]
    order_id = context.user_data["order_flow"]["order_id"]
    paas_id = context.user_data["order_flow"]["paas_id"]
    
    try:
        status_res = await swiggy_mcp_client.check_payment_status(token, paas_id, order_id, addr_id)
        status = status_res.get("status") if isinstance(status_res, dict) else "UNKNOWN"
        
        if status == "SUCCESS" or status == "PAID":
            await query.edit_message_text("✅ Payment Successful! Confirming order...")
            # Auto confirm
            await swiggy_mcp_client.confirm_order(token, order_id, addr_id, 0.0, 0.0) # We might need real lat/lng
            await query.edit_message_text(f"🎉 Order {order_id} is PLACED successfully!")
            return ConversationHandler.END
        elif status == "FAILED":
            await query.edit_message_text("❌ Payment Failed. Please try again.")
            return ConversationHandler.END
        else:
            keyboard = [[InlineKeyboardButton("Check Status", callback_data="check_upi_status")]]
            await query.edit_message_text(
                f"Status: {status}. Still pending...",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return PAYMENT_PENDING
            
    except Exception as e:
        logger.exception("UPI status check failed")
        await query.edit_message_text(f"❌ Failed to check status: {e}")
        return ConversationHandler.END

def get_order_flow_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_order_flow, pattern="^order_food$")],
        states={
            SELECT_ADDRESS: [
                CallbackQueryHandler(cancel_order_flow, pattern="^cancel_order$"),
                CallbackQueryHandler(handle_address_selection, pattern="^addr_")
            ],
            SEARCH_RESTAURANT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_restaurant_search)
            ],
            SELECT_RESTAURANT: [
                CallbackQueryHandler(cancel_order_flow, pattern="^cancel_order$"),
                CallbackQueryHandler(handle_restaurant_selection, pattern="^rest_")
            ],
            SELECT_MENU_ITEM: [
                CallbackQueryHandler(cancel_order_flow, pattern="^cancel_order$"),
                CallbackQueryHandler(handle_menu_item_selection, pattern="^item_"),
                CallbackQueryHandler(show_cart, pattern="^view_cart$")
            ],
            VIEW_CART: [
                CallbackQueryHandler(cancel_order_flow, pattern="^cancel_order$"),
                CallbackQueryHandler(proceed_to_payment, pattern="^proceed_payment$")
            ],
            SELECT_PAYMENT: [
                CallbackQueryHandler(cancel_order_flow, pattern="^cancel_order$"),
                CallbackQueryHandler(confirm_payment_and_place_order, pattern="^pay_")
            ],
            PAYMENT_PENDING: [
                CallbackQueryHandler(cancel_order_flow, pattern="^cancel_order$"),
                CallbackQueryHandler(check_upi_status, pattern="^check_upi_status$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_order_flow),
            CommandHandler("start", cancel_order_flow)
        ],
        per_message=False,
    )

async def handle_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    telegram_id = str(update.effective_user.id)
    token = get_user_access_token(telegram_id)
    if not token:
        await query.message.reply_text("❌ Please connect your Swiggy account first.")
        return
        
    await query.message.reply_text("🛒 Fetching your cart...")
    
    try:
        # To get cart, we need an address. Let's get the first saved address.
        addresses = await swiggy_mcp_client.get_addresses(token)
        if not addresses:
            await query.message.reply_text("❌ No addresses found on your account. Cannot load cart.")
            return
            
        addr_id = str(addresses[0].get("id") or addresses[0].get("addressId") or addresses[0].get("address_id", ""))
        
        cart_resp = await swiggy_mcp_client.get_food_cart(token, addr_id)
        cart = cart_resp.get("data") if (isinstance(cart_resp, dict) and "data" in cart_resp) else cart_resp
        
        items = cart.get("items", []) if isinstance(cart, dict) else []
        
        pricing = cart.get("pricing", {}) if isinstance(cart, dict) else {}
        total = pricing.get("to_pay") or cart.get("cartTotal", 0) or 0
        total = total / 100 if total > 10000 else total
        
        if not items:
            await query.message.reply_text("🛒 Your cart is currently empty.")
            return
            
        msg = "🛒 *Your Current Cart*\n\n"
        for item in items:
            raw_p = item.get("final_price") or item.get("subtotal") or item.get("price") or item.get("defaultPrice") or 0
            p = raw_p / 100 if raw_p > 10000 else raw_p
            msg += f"• {item.get('quantity', 1)}x {item.get('name', 'Item')} - ₹{p}\n"
            
        msg += f"\n*Total:* ₹{total}\n\n"
        msg += "_Use '🍴 Order Food' from the main menu to modify your cart._"
        
        await query.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Cart fetch failed")
        await query.message.reply_text(f"❌ Failed to fetch cart: {e}")

async def handle_active_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    telegram_id = str(update.effective_user.id)
    token = get_user_access_token(telegram_id)
    if not token:
        await query.message.reply_text("❌ Please connect your Swiggy account first.")
        return
        
    await query.message.reply_text("📦 Checking active orders...")
    
    try:
        addresses = await swiggy_mcp_client.get_addresses(token)
        if not addresses:
            await query.message.reply_text("❌ No addresses found.")
            return
            
        active_orders = []
        # Since active orders can be on any address, we might need to check them.
        # But for brevity, let's just check the first 3 addresses.
        for a in addresses[:3]:
            aid = str(a.get("id") or a.get("addressId") or a.get("address_id", ""))
            if not aid: continue
            
            # Use undocumented activeOnly? The user prompt said:
            # activeOnly=true -> active/in-progress only
            orders_resp = await swiggy_mcp_client._mcp_call(token, "get_food_orders", {"addressId": aid, "activeOnly": True})
            orders = swiggy_mcp_client._extract_result(orders_resp, "get_food_orders")
            
            items = orders.get("orders", []) if isinstance(orders, dict) else (orders if isinstance(orders, list) else [])
            for o in items:
                if o.get("isActiveOrder"):
                    active_orders.append(o)
                    
            if active_orders:
                break # Found one
                
        if not active_orders:
            await query.message.reply_text("You have no active Swiggy food orders at the moment.")
            return
            
        o = active_orders[0]
        order_id = o.get("orderId", "Unknown")
        rest_name = o.get("restaurantName", "Restaurant")
        status = o.get("orderStatus", "PENDING")
        total = o.get("orderTotal", 0)
        if isinstance(total, int): total = total / 100
        
        msg = f"📦 *Active Order: {order_id}*\n\n"
        msg += f"🏪 *{rest_name}*\n"
        msg += f"📊 Status: {status}\n"
        msg += f"💰 Total: ₹{total}\n"
        
        await query.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception("Active order fetch failed")
        await query.message.reply_text(f"❌ Failed to fetch active order: {e}")

