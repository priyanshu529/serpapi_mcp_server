import os
import json
from typing import Optional

import requests
from fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

mcp = FastMCP("travelpayouts-custom")

BASE_URL = "https://serpapi.com/search"


def _run_search(params: dict) -> dict:
    """Shared call into SerpApi's google_flights engine."""

    if not SERPAPI_API_KEY:
        raise RuntimeError(
            "SERPAPI_API_KEY is not set. Add it as an environment variable "
            "(locally via .env, or in the deployment environment)."
        )

    params = {
        **params,
        "engine": "google_flights",
        "api_key": SERPAPI_API_KEY,
    }

    # Hide API key in logs
    log_params = params.copy()
    log_params["api_key"] = "***HIDDEN***"

    print("\n" + "=" * 80)
    print("SERPAPI REQUEST")
    print(json.dumps(log_params, indent=2))
    print("=" * 80)

    resp = requests.get(BASE_URL, params=params, timeout=30)

    print(f"HTTP STATUS: {resp.status_code}")

    try:
        data = resp.json()
    except Exception:
        print("Response is not valid JSON:")
        print(resp.text)
        raise

    print("=" * 80)
    print("SERPAPI RESPONSE")
    print(json.dumps(data, indent=2))
    print("=" * 80 + "\n")

    if resp.status_code != 200:
        resp.raise_for_status()

    if "error" in data:
        raise RuntimeError(f"SerpApi error: {data['error']}")

    return data


def _simplify_flights(data: dict, limit: int) -> list[dict]:
    """
    Convert SerpApi's nested itinerary structure into a simple list.
    """

    itineraries = data.get("best_flights", []) + data.get("other_flights", [])

    simplified = []

    for itinerary in itineraries:
        legs = itinerary.get("flights", [])

        if not legs:
            continue

        first_leg = legs[0]
        last_leg = legs[-1]

        simplified.append(
            {
                "price": itinerary.get("price"),
                "airline": first_leg.get("airline"),
                "flight_number": first_leg.get("flight_number"),
                "stops": len(legs) - 1,
                "total_duration_minutes": itinerary.get("total_duration"),
                "departure_airport": first_leg.get("departure_airport", {}).get("id"),
                "departure_time": first_leg.get("departure_airport", {}).get("time"),
                "arrival_airport": last_leg.get("arrival_airport", {}).get("id"),
                "arrival_time": last_leg.get("arrival_airport", {}).get("time"),
            }
        )

    simplified.sort(key=lambda x: (x["price"] is None, x["price"]))

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
    """Search flight tickets using SerpApi Google Flights."""

    print("\n" + "=" * 80)
    print("MCP TOOL INPUT")
    print(f"origin       : {origin}")
    print(f"destination  : {destination}")
    print(f"departure_at : {departure_at}")
    print(f"return_at    : {return_at}")
    print(f"one_way      : {one_way}")
    print(f"currency     : {currency}")
    print(f"limit        : {limit}")
    print("=" * 80)

    params = {
    "departure_id": origin,
    "arrival_id": destination,
    "outbound_date": departure_at,
    "currency": currency,
    "type": 2 if one_way else 1,
    "gl": "in",          # Search from India
    "hl": "en",          # English interface
    }

    if not one_way and return_at:
        params["return_date"] = return_at

    data = _run_search(params)

    flights = _simplify_flights(data, limit)

    price_insights = data.get("price_insights", {})

    print(f"Flights Found: {len(flights)}")
    print("=" * 80 + "\n")

    return {
        "flights": flights,
        "lowest_price": price_insights.get("lowest_price"),
        "price_level": price_insights.get("price_level"),
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=port,
    )
