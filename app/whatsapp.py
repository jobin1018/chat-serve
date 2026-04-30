import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


async def _post(phone_number_id: str, payload: dict) -> Optional[dict]:
    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload, headers=_headers())
    if response.status_code not in (200, 201):
        logger.error(
            "WhatsApp API error %s: %s", response.status_code, response.text
        )
        return None
    return response.json()


async def send_text(to: str, phone_number_id: str, text: str) -> Optional[dict]:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    return await _post(phone_number_id, payload)


async def send_interactive_list(
    to: str,
    phone_number_id: str,
    header: str,
    body: str,
    button_label: str,
    sections: list[dict],
) -> Optional[dict]:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header},
            "body": {"text": body},
            "action": {
                "button": button_label,
                "sections": sections,
            },
        },
    }
    return await _post(phone_number_id, payload)


async def send_interactive_buttons(
    to: str,
    phone_number_id: str,
    body: str,
    buttons: list[dict],
) -> Optional[dict]:
    """buttons: [{"id": "btn_1", "title": "Yes, confirm"}]"""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons
                ]
            },
        },
    }
    return await _post(phone_number_id, payload)


async def mark_as_read(message_id: str, phone_number_id: str) -> None:
    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        await client.post(url, json=payload, headers=_headers())
