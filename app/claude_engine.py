import json
import logging
from typing import Optional

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT_TEMPLATE = """You are the WhatsApp ordering assistant for {restaurant_name}.

RESTAURANT INFO:
- Hours: {opening_hours}
- Delivery areas: {delivery_areas}
- Minimum order: AED {min_order}

COMPLETE MENU:
{menu_text}

RULES:
- When customer sends ANY greeting (Hi, Hello, Salam, etc) — your FIRST response MUST show the complete menu with every item name and AED price. Do not say "feel free to order" without showing the actual menu list.
- Always format menu clearly by category with bullet points and prices
- Be warm and conversational — this is WhatsApp, not a website
- Respond in the same language the customer uses (English, Arabic, Hindi, Urdu)
- Take orders naturally — understand "2 biryanis and a juice"
- Clarify ambiguous items politely (e.g. which biryani?)
- Always confirm the itemised order with quantities and total before finalising
- For delivery orders, always ask for the customer's delivery address before confirming.
- When the customer confirms their order, end your response with EXACTLY this signal on its own line (no text after it):
  Pickup example:
  ORDER_CONFIRMED:{{"items":[{{"name":"Chicken Biryani","qty":2,"price":25.0}},{{"name":"Mango Lassi","qty":1,"price":12.0}}],"total":62.0,"type":"pickup","address":""}}
  Delivery example:
  ORDER_CONFIRMED:{{"items":[{{"name":"Chicken Biryani","qty":1,"price":25.0}}],"total":25.0,"type":"delivery","address":"Al Nahda 2, Building 7, Flat 301"}}
  CRITICAL: the address field MUST contain the exact delivery address the customer gave you. Never leave address empty for a delivery order.
- Never discuss anything unrelated to food ordering
- If asked whether you are an AI, say: "I am the digital ordering assistant for {restaurant_name} 😊"
- Keep responses concise — this is a chat interface
"""


def _format_menu(menu_items: list[dict]) -> str:
    by_category: dict[str, list] = {}
    for item in menu_items:
        cat = item["category"]
        by_category.setdefault(cat, []).append(item)

    lines = []
    for category, items in by_category.items():
        lines.append(f"\n{category.upper()}:")
        for item in items:
            lines.append(
                f"  • {item['name']} — AED {float(item['price']):.0f}"
                + (f" ({item['description']})" if item.get("description") else "")
            )
    return "\n".join(lines)


def _parse_order_confirmation(text: str) -> tuple[str, Optional[dict]]:
    """Strip ORDER_CONFIRMED signal from Claude's reply and parse the JSON payload.

    Finds 'ORDER_CONFIRMED:' then extracts the JSON by counting braces so nested
    objects inside the items array don't confuse the boundary detection.
    """
    marker = "ORDER_CONFIRMED:"
    idx = text.find(marker)
    if idx == -1:
        return text, None

    json_start = text.find("{", idx)
    if json_start == -1:
        return text, None

    # Walk forward counting braces to find the matching closing brace
    depth = 0
    json_end = json_start
    for i, ch in enumerate(text[json_start:], start=json_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_end = i
                break

    raw_json = text[json_start: json_end + 1]
    reply = text[:idx].strip()

    try:
        order_data = json.loads(raw_json)
        logger.info("ORDER_CONFIRMED parsed — type=%s address=%r",
                    order_data.get("type"), order_data.get("address"))
        return reply, order_data
    except json.JSONDecodeError:
        logger.error("Failed to parse ORDER_CONFIRMED JSON: %s", raw_json)
        return reply, None


async def get_ai_response(
    restaurant_name: str,
    opening_hours: str,
    delivery_areas: str,
    min_order: float,
    menu_items: list[dict],
    conversation_history: list[dict],
    user_message: str,
) -> tuple[str, Optional[dict]]:
    system_content = SYSTEM_PROMPT_TEMPLATE.format(
        restaurant_name=restaurant_name,
        opening_hours=opening_hours,
        delivery_areas=delivery_areas,
        min_order=min_order,
        menu_text=_format_menu(menu_items),
    )

    messages = conversation_history + [{"role": "user", "content": user_message}]

    response = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": system_content,
                "cache_control": {"type": "ephemeral"},  # prompt caching
            }
        ],
        messages=messages,
    )

    raw_reply = response.content[0].text
    logger.info(
        "Claude response (input_tokens=%d, output_tokens=%d, cache_read=%d)",
        response.usage.input_tokens,
        response.usage.output_tokens,
        getattr(response.usage, "cache_read_input_tokens", 0),
    )

    reply, order_data = _parse_order_confirmation(raw_reply)
    return reply, order_data
