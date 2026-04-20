import requests

API_KEY = "fhlBlfRcnxZ091IZrC46PbGzjXt3G3G3clp0B/Pbyv9PnN6PdZY9H16eQZrbllWDamuRegRzetqGdwR9jE3MpQ=="
URL = "http://apis.data.go.kr/1390802/SoilEnviron/SoilExam/V2/getSoilExamList"

codes = [
    "4677025300",  # 현재 방식: EMD_CD + 00
    "46770253",    # EMD_CD 그대로
    "46770",       # COL_ADM_SE / 시군구 추정
]

for code in codes:
    params = {
        "serviceKey": API_KEY,
        "Page_Size": "10",
        "Page_No": "1",
        "STDG_CD": code
    }

    res = requests.get(URL, params=params, timeout=15)

    print("\n==============================")
    print("TEST CODE:", code)
    print(res.text[:1000])
    print("==============================")