import logging
from typing import Any
from src.mcp_transport import mcp_call, extract_mcp_result
import re

logger = logging.getLogger(__name__)

SWIGGY_DINEOUT_MCP_URL = "https://mcp.swiggy.com/dineout"

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
    return _extract_result(render_resp, "render_restaurants_dineout")

async def get_available_slots(access_token: str, rest_id: str, date: str, lat: float, lng: float) -> dict:
    args = {
        "restaurantId": rest_id,
        "date": date,
        "latitude": lat,
        "longitude": lng
    }
    resp = await _mcp_call(access_token, "get_available_slots", args)
    
    result_data = resp.get("result", {})
    content = result_data.get("content", [])
    text = ""
    for c in content:
        if c.get("type") == "text": text += c.get("text", "")
        
    if not text:
        return {"slots": []}
        
    # Parse text to build JSON slots!
    # Look for booking params for the requested date
    param_match = re.search(rf"{date} \[FREE\]: slotId=(\d+), itemId=\"([^\"]+)\"", text)
    if not param_match:
        return {"slots": []}
        
    slot_id = int(param_match.group(1))
    item_id = param_match.group(2)
    
    # Extract times for the requested date
    slots = []
    # Find the section starting with "Slots for {date}:"
    date_section_match = re.search(rf"Slots for {date}:(.*?)(?:\n\nSlots for|\Z)", text, re.DOTALL)
    if not date_section_match:
        return {"slots": []}
        
    date_section = date_section_match.group(1)
    
    # Times look like: "12:00 PM???1787380200" (unicode dash may vary, so we use regex \D+ or similar)
    # Actually just match time string and digits
    time_matches = re.findall(r"(\d{2}:\d{2}\s+[AMPM]{2})\D+(\d{10,})", date_section)
    
    for time_str, res_time in time_matches:
        slots.append({
            "timeString": time_str,
            "reservationTime": int(res_time),
            "deals": [{"slotId": slot_id, "itemId": item_id}]
        })
        
    return {"slots": slots}

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
