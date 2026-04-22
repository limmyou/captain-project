# app/services/geocode_service.py
import requests
from app.core.config import VWORLD_API_KEY

VWORLD_URL = "https://api.vworld.kr/req/address"


def geocode(address: str) -> tuple[float, float]:
    if not VWORLD_API_KEY:
        raise ValueError("VWORLD_API_KEY가 설정되지 않았습니다.")

    for addr_type in ["road", "parcel"]:
        params = {
            "service": "address",
            "request": "getcoord",
            "version": "2.0",
            "crs": "epsg:4326",
            "address": address,
            "type": addr_type,
            "key": VWORLD_API_KEY
        }
        print("VWORLD_KEY exists:", bool(VWORLD_API_KEY))
        print("address:", address)


        try:
            print("👉 sending request to VWorld...")
            res = requests.get(VWORLD_URL, params=params, timeout=10)

            print("👉 status code:", res.status_code)
            print("👉 response text:", res.text[:300])

            res.raise_for_status()
            data = res.json()
        except requests.RequestException as e:
            print("❌ VWorld request failed:", repr(e))
            raise RuntimeError(f"VWorld API 요청 실패: {e}")

        response = data.get("response", {})
        if response.get("status") == "OK":
            point = response.get("result", {}).get("point")
            if point:
                lon = float(point["x"])
                lat = float(point["y"])
                return lat, lon

    raise ValueError(f"주소를 좌표로 변환할 수 없습니다: {address}")