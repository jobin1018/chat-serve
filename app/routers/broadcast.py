import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app import database as db
from app import whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/broadcast", tags=["admin – broadcast"])

RATE_LIMIT = 20  # messages per second burst
RATE_SLEEP = 1.0  # seconds to sleep after each burst


class BroadcastPayload(BaseModel):
    message: str


@router.post("/{restaurant_id}")
async def broadcast(restaurant_id: str, payload: BroadcastPayload, background_tasks: BackgroundTasks):
    """Send a WhatsApp message to all opted-in customers. Runs in background — returns immediately."""
    restaurant = await db.get_restaurant_by_id(restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    customers = await db.get_opted_in_customers(restaurant_id)
    if not customers:
        return {"queued": 0, "message": "No opted-in customers"}

    background_tasks.add_task(
        _do_broadcast,
        restaurant=restaurant,
        customers=customers,
        message=payload.message,
    )
    return {"queued": len(customers), "status": "sending in background"}


async def _do_broadcast(restaurant: dict, customers: list[dict], message: str):
    phone_number_id = str(restaurant["phone_number_id"])
    sent = 0
    failed = 0

    for i, customer in enumerate(customers):
        try:
            await whatsapp.send_text(str(customer["phone"]), phone_number_id, message)
            sent += 1
        except Exception:
            logger.exception("Broadcast failed for customer %s", customer["phone"])
            failed += 1

        # Rate limit: pause every 20 messages
        if (i + 1) % RATE_LIMIT == 0:
            await asyncio.sleep(RATE_SLEEP)

    logger.info(
        "Broadcast complete for restaurant %s — sent=%d failed=%d",
        restaurant["id"], sent, failed,
    )
