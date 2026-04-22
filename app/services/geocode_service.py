# app/services/geocode_service.py
import os
import requests

KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")
KAKAO_URL = "https://dapi.kakao.com/v2/local/search/address.json"


def geocode(address: str) -> tuple[float, float]:
    if not KAKAO_API_KEY:
        raise ValueError("KAKAO_API_KEY가 설정되지 않았습니다.")

    headers = {
        "Authorization": f"KakaoAK {KAKAO_API_KEY}"
    }

    params = {
        "query": address
    }

    try:
        print("👉 카카오 API 요청", flush=True)
        print("address:", address, flush=True)

        res = requests.get(KAKAO_URL, headers=headers, params=params, timeout=10)

        print("status:", res.status_code, flush=True)
        print("response:", res.text[:200], flush=True)

        res.raise_for_status()
        data = res.json()

    except requests.RequestException as e:
        print("❌ 카카오 API 실패:", repr(e), flush=True)
        raise RuntimeError("주소 변환 API 요청 실패")

    documents = data.get("documents", [])

    if not documents:
        raise RuntimeError("주소 검색 결과가 없습니다.")

    first = documents[0]

    x = first["x"]  # 경도
    y = first["y"]  # 위도

    return float(y), float(x)