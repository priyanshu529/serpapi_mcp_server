import os
from typing import Optional

import requests
from fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

mcp = FastMCP("travelpayouts-custom")  # tool names kept as-is so mcp_client.py doesn't need to change its lookups

BASE_URL = "https://serpapi.com/search"


def _run_search(params: dict) -> dict:
    """Shared call into SerpApi's google_flights engine."""
    if not SERPAPI_API_KEY:
        raise RuntimeError(
            "SERPAPI_API_KEY is not set. Add it as an environment variable "
            "(locally via .env, or in the FastMCP Cloud project settings)."
        )
    params = {**params, "engine": "google_flights", "api_key": SERPAPI_API_KEY}
    resp = requests.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"SerpApi error: {data['error']}")
    return data


def _simplify_flights(data: dict, limit: int) -> list[dict]:
    """
    SerpApi returns itineraries under best_flights / other_flights, each holding a list of
    individual legs under "flights". We flatten that into one price-sorted list so the rest
    of the app doesn't need to know about SerpApi's nested shape.
    """
    itineraries = data.get("best_flights", []) + data.get("other_flights", [])
    simplified = []
    for itinerary in itineraries:
        legs = itinerary.get("flights", [])
        if not legs:
            continue
        first_leg = legs[0]
        last_leg = legs[-1]
        simplified.append({
            "price": itinerary.get("price"),
            "airline": first_leg.get("airline"),
            "flight_number": first_leg.get("flight_number"),
            "stops": len(legs) - 1,
            "total_duration_minutes": itinerary.get("total_duration"),
            "departure_airport": first_leg.get("departure_airport", {}).get("id"),
            "departure_time": first_leg.get("departure_airport", {}).get("time"),
            "arrival_airport": last_leg.get("arrival_airport", {}).get("id"),
            "arrival_time": last_leg.get("arrival_airport", {}).get("time"),
        })
    simplified.sort(key=lambda f: (f["price"] is None, f["price"]))
    return simplified[:limit]


@mcp.tool()
def search_flights_prices(
    origin: str,
    destination: str,
    departure_at: Optional[str] = None,
    return_at: Optional[str] = None,
    one_way: bool = True,
    currency: str = "INR",
    limit: int = 10,
) -> dict:
    """Search cheap flight tickets by route, dates, and currency."""
    params = {
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure_at,
        "currency": currency,
        "type": 2 if one_way else 1,
    }
    if not one_way and return_at:
        params["return_date"] = return_at

    data = _run_search(params)
    flights = _simplify_flights(data, limit)
    price_insights = data.get("price_insights", {})

    return {
        "flights": flights,
        "lowest_price": price_insights.get("lowest_price"),
        "price_level": price_insights.get("price_level"),
    }


if __name__ == "__main__":
    # Ignored by FastMCP Cloud (it imports the `mcp` object directly),
    # but useful for running the server locally: `python mcp_server.py`
    mcp.run()
