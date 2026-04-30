import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import PlainTextResponse

from app import database as db
from app import redis_client as rc
from app import whatsapp
from app.claude_engine import get_ai_response
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


# ── Webhook verification ──────────────────────────────────────────────────────

@router.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return PlainTextResponse(content=challenge)

    logger.warning("Webhook verification failed — token mismatch")
    return Response(status_code=403)


# ── Incoming messages ─────────────────────────────────────────────────────────

@router.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """Return 200 to Meta immediately; process in background."""
    body = await request.json()
    background_tasks.add_task(process_webhook, body)
    return {"status": "ok"}


async def process_webhook(body: dict):
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Ignore delivery/read status updates
                if "statuses" in value:
                    continue

                messages = value.get("messages", [])
                if not messages:
                    continue

                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id", "")

                for message in messages:
                    await _handle_message(message, phone_number_id)

    except Exception:
        logger.exception("Unhandled error in process_webhook")


async def _handle_message(message: dict, phone_number_id: str):
    message_id = message.get("id", "")
    customer_phone = message.get("from", "")
    message_type = message.get("type", "")

    logger.info(
        "Incoming message id=%s from=%s type=%s phone_number_id=%s",
        message_id, customer_phone, message_type, phone_number_id,
    )

    # ── Deduplicate ────────────────────────────────────────────────────────────
    if await rc.is_duplicate(message_id):
        logger.info("Duplicate message %s — skipping", message_id)
        return

    # ── Mark as read immediately (double blue tick) ───────────────────────────
    await whatsapp.mark_as_read(message_id, phone_number_id)

    # ── Extract text ──────────────────────────────────────────────────────────
    if message_type == "text":
        text = message.get("text", {}).get("body", "").strip()
    elif message_type == "interactive":
        # Button/list replies
        interactive = message.get("interactive", {})
        if interactive.get("type") == "button_reply":
            text = interactive["button_reply"]["title"]
        elif interactive.get("type") == "list_reply":
            text = interactive["list_reply"]["title"]
        else:
            text = ""
    else:
        # Voice notes, images, stickers, etc.
        await whatsapp.send_text(
            customer_phone,
            phone_number_id,
            "Please type your order — I can only read text messages 😊",
        )
        return

    if not text:
        return

    # ── Look up restaurant ────────────────────────────────────────────────────
    restaurant = await db.get_restaurant_by_phone_number_id(phone_number_id)
    if not restaurant:
        logger.warning("No active restaurant found for phone_number_id=%s", phone_number_id)
        return

    # ── Load menu ─────────────────────────────────────────────────────────────
    menu_items = await db.get_menu_items(restaurant["id"], available_only=True)

    # ── Conversation history ──────────────────────────────────────────────────
    conv_key = f"conv:{restaurant['id']}:{customer_phone}"
    history = await rc.get_conversation_history(conv_key)

    # ── Call Claude ───────────────────────────────────────────────────────────
    try:
        reply, order_data = await get_ai_response(
            restaurant_name=restaurant["name"],
            opening_hours=str(restaurant.get("opening_hours", "9am – 11pm")),
            delivery_areas=str(restaurant.get("delivery_areas", "Al Nahda, Sharjah")),
            min_order=float(restaurant.get("min_order", 0)),
            menu_items=menu_items,
            conversation_history=history,
            user_message=text,
        )
    except Exception:
        logger.exception("Claude error for restaurant %s", restaurant["id"])
        await whatsapp.send_text(
            customer_phone,
            phone_number_id,
            "Sorry, I'm having a little trouble right now. Please try again in a moment 🙏",
        )
        return

    # ── Order confirmed ───────────────────────────────────────────────────────
    if order_data:
        try:
            order = await db.create_order(
                restaurant_id=str(restaurant["id"]),
                customer_phone=customer_phone,
                items=order_data.get("items", []),
                total=float(order_data.get("total", 0)),
                order_type=order_data.get("type", "pickup"),
                delivery_address=order_data.get("address", ""),
            )
            await db.upsert_customer(
                restaurant_id=str(restaurant["id"]),
                phone=customer_phone,
                spent=float(order_data.get("total", 0)),
            )
            # Notify kitchen
            kitchen_msg = _format_kitchen_notification(order, order_data)
            await whatsapp.send_text(
                str(restaurant["kitchen_num"]), phone_number_id, kitchen_msg
            )

            # Confirm to customer
            confirm_text = (
                (reply + "\n\n" if reply else "")
                + f"✅ Order #{str(order['id'])[:8].upper()} confirmed!\n"
                "We'll start preparing it now. You'll hear from us when it's ready 👨‍🍳"
            )
            await whatsapp.send_text(customer_phone, phone_number_id, confirm_text)

            # Clear conversation for this customer
            await rc.clear_conversation(conv_key)

            logger.info(
                "Order %s created for restaurant %s customer %s total=AED %.2f",
                order["id"], restaurant["id"], customer_phone, order["total"],
            )
        except Exception:
            logger.exception("Failed to save order for restaurant %s", restaurant["id"])
            await whatsapp.send_text(
                customer_phone,
                phone_number_id,
                "Your order was received but I had trouble saving it. The kitchen has been notified. Sorry for the inconvenience! 🙏",
            )
    else:
        # Regular conversation turn
        await whatsapp.send_text(customer_phone, phone_number_id, reply)
        await rc.update_conversation_history(conv_key, text, reply)


def _format_kitchen_notification(order: dict, order_data: dict) -> str:
    short_id = str(order["id"])[:8].upper()
    lines = [f"🔔 *NEW ORDER #{short_id}*", f"📱 Customer: {order['customer_phone']}"]

    items = order_data.get("items", [])
    for item in items:
        lines.append(f"  • {item.get('qty', 1)}x {item.get('name')} — AED {item.get('price', 0):.0f}")

    lines.append(f"\n💰 *Total: AED {float(order['total']):.2f}*")
    lines.append(f"🛵 Type: {order['order_type'].upper()}")
    if order["order_type"] == "delivery" and order.get("delivery_address"):
        lines.append(f"📍 Deliver to: {order['delivery_address']}")
    return "\n".join(lines)
