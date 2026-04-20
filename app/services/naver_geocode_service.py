import requests
from app.core.config import NAVER_MAPS_CLIENT_ID, NAVER_MAPS_CLIENT_SECRET

NAVER_GEOCODE_URL = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"


def naver_geocode(query: str) -> tuple[float, float]:
    if not NAVER_MAPS_CLIENT_ID or not NAVER_MAPS_CLIENT_SECRET:
        raise ValueError("네이버 지도 API 키가 설정되지 않았습니다.")

    headers = {
        "x-ncp-apigw-api-key-id": NAVER_MAPS_CLIENT_ID,
        "x-ncp-apigw-api-key": NAVER_MAPS_CLIENT_SECRET,
    }

    params = {
        "query": query
    }

    res = requests.get(NAVER_GEOCODE_URL, headers=headers, params=params, timeout=15)
    res.raise_for_status()
    data = res.json()

    addresses = data.get("addresses", [])
    if not addresses:
        raise ValueError(f"네이버 geocoding 결과 없음: {query}")

    first = addresses[0]
    lon = float(first["x"])
    lat = float(first["y"])
    return lat, lon