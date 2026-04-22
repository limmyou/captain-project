# app/services/geocode_service.py
import requests
from app.core.config import VWORLD_API_KEY

VWORLD_URL = "https://api.vworld.kr/req/address"


def geocode(address: str) -> tuple[float, float]:
    if not VWORLD_API_KEY:
        raise ValueError("VWORLD_API_KEY가 설정되지 않았습니다.")

    last_error = None

    for addr_type in ["road", "parcel"]:
        params = {
            "service": "address",
            "request": "getcoord",
            "version": "2.0",
            "crs": "epsg:4326",
            "address": address,
            "type": addr_type,
            "key": VWORLD_API_KEY,
        }

        print("VWORLD_KEY exists:", bool(VWORLD_API_KEY))
        print("address:", address)
        print("addr_type:", addr_type)

        try:
            print("👉 sending request to VWorld...")
            res = requests.get(VWORLD_URL, params=params, timeout=10)

            print("👉 status code:", res.status_code)
            print("👉 response text:", res.text[:300])

            res.raise_for_status()
            data = res.json()

        except requests.RequestException as e:
            print("❌ VWorld request failed:", addr_type, repr(e))
            last_error = e
            continue

        response = data.get("response", {})

        if response.get("status") == "OK":
            result = response.get("result", {})
            point = result.get("point", {})
            x = point.get("x")
            y = point.get("y")

            if x and y:
                return float(y), float(x)

        else:
            print("❌ VWorld API returned non-OK:", response)

    if last_error is not None:
        raise RuntimeError("VWorld API 요청에 실패했습니다. 잠시 후 다시 시도해주세요.")

    raise RuntimeError("주소 좌표 변환에 실패했습니다.")