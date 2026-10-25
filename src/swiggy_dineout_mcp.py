import logging
import os
from typing import Any
from .mcp_transport import mcp_call, extract_mcp_result
import re

logger = logging.getLogger(__name__)

SWIGGY_DINEOUT_MCP_URL = os.getenv("SWIGGY_DINEOUT_MCP_URL", "https://mcp.swiggy.com/dineout")

async def _mcp_call(access_token: str, tool_name: str, arguments: dict[str, Any]) -> dict:
    return await mcp_call(access_token, SWIGGY_DINEOUT_MCP_URL, tool_name, arguments)

def _extract_result(response: dict, tool_name: str) -> Any:
    return extract_mcp_result(response, tool_name)

async def get_saved_locations(access_token: str) -> dict:
    resp = await _mcp_call(access_token, "get_saved_locations", {})
    return _extract_result(resp, "get_saved_locations")

async def search_restaurants_dineout(access_token: str, query: str, address_id: str = None, lat: float = None, lng: float = None) -> dict:
    args = {"query": query}
    if address_id:
        args["addressId"] = address_id
    elif lat is not None and lng is not None:
        args["latitude"] = lat
        args["longitude"] = lng
    resp = await _mcp_call(access_token, "search_restaurants_dineout", args)
    
    result_data = resp.get("result", {})
    content = result_data.get("content", [])
    text = ""
    for c in content:
        if c.get("type") == "text": text += c.get("text", "")
        
    if not text:
        return _extract_result(resp, "search_restaurants_dineout")
        
    ids = re.findall(r"\(ID: (\d+)\)", text)
    if not ids:
        return {"restaurants": []}
        
    lat_match = re.search(r"latitude=([\d\.]+)", text)
    lng_match = re.search(r"longitude=([\d\.]+)", text)
    search_lat = float(lat_match.group(1)) if lat_match else lat
    search_lng = float(lng_match.group(1)) if lng_match else lng
    
    render_args = {
        "restaurantIds": ids[:15],
        "searches": [{
            "query": query,
            "latitude": search_lat,
            "longitude": search_lng
        }]
    }
    
    render_resp = await _mcp_call(access_token, "render_restaurants_dineout", render_args)
    rendered = _extract_result(render_resp, "render_restaurants_dineout")
    if isinstance(rendered, dict) and search_lat is not None and search_lng is not None:
        rendered.setdefault("_searchLocation", {
            "latitude": float(search_lat),
            "longitude": float(search_lng),
        })
    return rendered

async def get_available_slots(access_token: str, rest_id: str, date: str, lat: float, lng: float) -> dict:
    args = {
        "restaurantId": rest_id,
        "date": date,
        "latitude": lat,
        "longitude": lng
    }
    resp = await _mcp_call(access_token, "get_available_slots", args)

    # Prefer the typed response when the MCP server provides one. The previous
    # implementation only parsed text and silently reported no slots for valid
    # structuredContent responses.
    data = _extract_result(resp, "get_available_slots")
    if isinstance(data, dict):
        slots_data = data.get("slots")
        slots_source = data
        if not isinstance(slots_data, list):
            nested = data.get("data") or data.get("result")
            if isinstance(nested, dict):
                slots_data = nested.get("slots")
                slots_source = nested
        if isinstance(slots_data, list):
            # The current Dineout schema uses displayTime/dateStr and puts
            # booking identifiers on each deal. Adapt it to the stable shape
            # consumed by the Telegram booking flow.
            return _normalize_structured_slots({**slots_source, "slots": slots_data}, date)

    result_data = resp.get("result", {}) if isinstance(resp, dict) else {}
    content = result_data.get("content", []) if isinstance(result_data, dict) else []
    text = "\n".join(
        c.get("text", "") for c in content
        if isinstance(c, dict) and c.get("type") == "text"
    )

    # A text content item can itself be a JSON encoding of a structured result.
    if text:
        try:
            decoded = __import__("json").loads(text)
            if isinstance(decoded, dict):
                decoded = decoded.get("data", decoded)
                if isinstance(decoded, dict) and isinstance(decoded.get("slots"), list):
                    return _normalize_structured_slots(decoded, date)
        except (ValueError, TypeError):
            pass

    if not text:
        # Keep the upstream shape visible to callers rather than hiding a new
        # response format as an empty availability result.
        return data if isinstance(data, dict) else {"slots": []}
        
    # Parse text to build JSON slots!
    # Look for booking params for the requested date
    date_pattern = re.escape(date)
    param_match = re.search(rf"{date_pattern} \[(?:FREE|PAID)\]: slotId=(\d+), itemId=\"([^\"]+)\"", text)
    if not param_match:
        return {"slots": []}
        
    slot_id = int(param_match.group(1))
    item_id = param_match.group(2)
    
    # Extract times for the requested date
    slots = []
    # Find the section starting with "Slots for {date}:"
    date_section_match = re.search(rf"Slots for {date_pattern}:(.*?)(?:\n\nSlots for|\Z)", text, re.DOTALL)
    if not date_section_match:
        return {"slots": []}
        
    date_section = date_section_match.group(1)
    
    # Times look like: "12:00 PM???1787380200" (unicode dash may vary, so we use regex \D+ or similar)
    # Actually just match time string and digits
    time_matches = re.findall(r"(\d{2}:\d{2}\s+(?:AM|PM))\D+(\d{10,})", date_section)
    
    for time_str, res_time in time_matches:
        slots.append({
            "timeString": time_str,
            "reservationTime": int(res_time),
            "deals": [{"slotId": slot_id, "itemId": item_id}]
        })
        
    return {"slots": slots}


def _normalize_structured_slots(data: dict, date: str) -> dict:
    """Normalize the slot shape returned inside text content."""
    slots = data.get("slots", [])
    normalized = []
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        slot_date = slot.get("dateStr") or slot.get("date")
        if slot_date and slot_date != date:
            continue
        deals = []
        for deal in slot.get("deals", []):
            if isinstance(deal, dict):
                slot_id = deal.get("slotId") or slot.get("slotId")
                item_id = deal.get("itemId") or slot.get("itemId")
                if slot_id is not None and item_id is not None:
                    deals.append({**deal, "slotId": slot_id, "itemId": item_id})
        normalized.append({
            **slot,
            "timeString": slot.get("displayTime") or slot.get("timeString") or "Unknown Time",
            "reservationTime": slot.get("reservationTime"),
            "deals": deals,
        })
    return {**data, "slots": normalized}

async def book_table(access_token: str, rest_id: str, slot_id: int, item_id: str, res_time: int, guests: int, lat: float, lng: float) -> dict:
    args = {
        "restaurantId": rest_id,
        "slotId": slot_id,
        "itemId": item_id,
        "reservationTime": res_time,
        "guestCount": guests,
        "latitude": lat,
        "longitude": lng,
        "paymentMethod": "Cash"
    }
    resp = await _mcp_call(access_token, "book_table", args)
    return _extract_result(resp, "book_table")
