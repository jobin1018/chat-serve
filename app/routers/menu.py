import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/menu", tags=["admin – menu"])


class MenuItemCreate(BaseModel):
    name: str
    price: float
    category: str
    description: str = ""
    sort_order: int = 0


@router.get("/{restaurant_id}")
async def list_menu(restaurant_id: str):
    """Full menu for a restaurant including unavailable items."""
    return await db.get_menu_items(restaurant_id, available_only=False)


@router.post("/{restaurant_id}", status_code=201)
async def add_menu_item(restaurant_id: str, item: MenuItemCreate):
    """Add a new menu item."""
    restaurant = await db.get_restaurant_by_id(restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return await db.create_menu_item(
        restaurant_id=restaurant_id,
        name=item.name,
        price=item.price,
        category=item.category,
        description=item.description,
        sort_order=item.sort_order,
    )


@router.patch("/item/{item_id}/toggle")
async def toggle_item(item_id: str):
    """Flip a menu item's availability on/off."""
    result = await db.toggle_menu_item(item_id)
    if not result:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"id": item_id, "available": result["available"]}
