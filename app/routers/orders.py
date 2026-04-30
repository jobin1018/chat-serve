import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import database as db
from app import whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/orders", tags=["admin – orders"])

VALID_STATUSES = {"new", "confirmed", "preparing", "ready", "completed", "cancelled"}


class StatusUpdate(BaseModel):
    status: str


@router.get("/{restaurant_id}")
async def list_orders(restaurant_id: str):
    """All orders for a restaurant, newest first."""
    restaurant = await db.get_restaurant_by_id(restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return await db.get_orders_for_restaurant(restaurant_id)


@router.get("/{restaurant_id}/today")
async def todays_stats(restaurant_id: str):
    """Today's orders and revenue summary."""
    restaurant = await db.get_restaurant_by_id(restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    orders = await db.get_todays_orders(restaurant_id)
    total_revenue = sum(float(o["total"]) for o in orders)
    by_status: dict[str, int] = {}
    for o in orders:
        by_status[o["status"]] = by_status.get(o["status"], 0) + 1

    return {
        "date": "today",
        "order_count": len(orders),
        "revenue_aed": round(total_revenue, 2),
        "by_status": by_status,
        "orders": orders,
    }


@router.patch("/{order_id}/status")
async def update_status(order_id: str, body: StatusUpdate):
    """Update order status. Sends WhatsApp to customer when status becomes 'ready'."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Choose from: {', '.join(sorted(VALID_STATUSES))}",
        )

    order = await db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    updated = await db.update_order_status(order_id, body.status)

    if body.status == "ready":
        restaurant = await db.get_restaurant_by_id(str(order["restaurant_id"]))
        if restaurant:
            short_id = str(order_id)[:8].upper()
            msg = (
                f"🎉 Great news! Your order #{short_id} is ready!\n\n"
                + ("🛵 Your delivery is on the way!" if order["order_type"] == "delivery"
                   else "🏃 Please come collect your order — it's hot and fresh!")
            )
            await whatsapp.send_text(
                str(order["customer_phone"]),
                str(restaurant["phone_number_id"]),
                msg,
            )
            logger.info("Sent 'ready' notification to %s for order %s", order["customer_phone"], order_id)

    return updated


@router.get("/stats/{restaurant_id}")
async def restaurant_stats(restaurant_id: str):
    """Overall stats: today's orders, revenue, total customers."""
    restaurant = await db.get_restaurant_by_id(restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    todays_orders = await db.get_todays_orders(restaurant_id)
    all_orders = await db.get_orders_for_restaurant(restaurant_id)
    customer_count = await db.get_customer_count(restaurant_id)

    return {
        "restaurant": restaurant["name"],
        "orders_today": len(todays_orders),
        "revenue_today_aed": round(sum(float(o["total"]) for o in todays_orders), 2),
        "total_orders": len(all_orders),
        "total_revenue_aed": round(sum(float(o["total"]) for o in all_orders), 2),
        "total_customers": customer_count,
    }
