# place_client.py

from typing import Any

import requests

import config


GOOGLE_PLACE_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


def search_place_google(place: str, size: int = 5) -> dict[str, Any]:
    api_key = config.GOOGLE_PLACES_API_KEY

    if not api_key:
        return {
            "ok": False,
            "status": "config_missing",
            "resolved": False,
            "query": place,
            "candidates": [],
            "top_candidates": [],
            "selected_candidate": None,
            "error_code": "GOOGLE_PLACES_API_KEY_MISSING",
        }

    try:
        response = requests.post(
            GOOGLE_PLACE_SEARCH_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": (
                    "places.id,"
                    "places.displayName,"
                    "places.formattedAddress,"
                    "places.primaryType,"
                    "places.location,"
                    "places.googleMapsUri"
                ),
            },
            json={
                "textQuery": place,
                "languageCode": "en",
                "regionCode": "US",
                "pageSize": size,
                "locationBias": {
                    "circle": {
                        "center": {
                            "latitude": config.GOOGLE_PLACES_LATITUDE,
                            "longitude": config.GOOGLE_PLACES_LONGITUDE,
                        },
                        "radius": config.GOOGLE_PLACES_RADIUS_METERS,
                    }
                },
            },
            timeout=5,
        )

        if response.status_code != 200:
            return {
                "ok": False,
                "status": "http_error",
                "resolved": False,
                "query": place,
                "candidates": [],
                "top_candidates": [],
                "selected_candidate": None,
                "http_status": response.status_code,
                "response_text": response.text[:1000],
            }

        data = response.json()
        places = data.get("places", [])

        candidates = []

        for idx, item in enumerate(places, start=1):
            display_name = item.get("displayName") or {}
            location = item.get("location") or {}

            candidates.append(
                {
                    "rank": idx,
                    "id": item.get("id"),
                    "name": display_name.get("text"),
                    "category": item.get("primaryType"),
                    "address": item.get("formattedAddress"),

                    # 기존 Kakao 결과 schema 최대한 유지
                    "road_address": None,
                    "jibun_address": None,
                    "phone": None,
                    "map_url": item.get("googleMapsUri"),

                    # Kakao x/y와 호환
                    # x = longitude
                    # y = latitude
                    "x": location.get("longitude"),
                    "y": location.get("latitude"),

                    "distance": None,
                }
            )

        if not candidates:
            return {
                "ok": True,
                "status": "not_found",
                "resolved": False,
                "query": place,
                "candidates": [],
                "top_candidates": [],
                "selected_candidate": None,
            }

        if len(candidates) == 1:
            return {
                "ok": True,
                "status": "exact_match",
                "resolved": True,
                "query": place,
                "candidates": candidates,
                "top_candidates": candidates,
                "selected_candidate": candidates[0],
            }

        return {
            "ok": True,
            "status": "multiple_candidates",
            "resolved": False,
            "query": place,
            "candidates": candidates,
            "top_candidates": candidates[:3],
            "selected_candidate": None,
        }

    except Exception as e:
        return {
            "ok": False,
            "status": "error",
            "resolved": False,
            "query": place,
            "candidates": [],
            "top_candidates": [],
            "selected_candidate": None,
            "error_type": type(e).__name__,
            "error": str(e),
        }


if __name__ == "__main__":
    test_queries = [
        "The Grove",
        "Starbucks in Santa Monica",
        "Blue Bottle Coffee",
        "LAX",
    ]

    for query in test_queries:
        print("\n" + "=" * 80)
        print("QUERY:", query)
        print("=" * 80)

        result = search_place_google(query)

        print("ok:", result.get("ok"))
        print("status:", result.get("status"))
        print("resolved:", result.get("resolved"))

        if not result.get("ok"):
            print("error:", result)
            continue

        for candidate in result.get("top_candidates", []):
            print(
                f"[{candidate['rank']}] "
                f"{candidate['name']} | "
                f"{candidate['address']} | "
                f"{candidate['category']}"
            )