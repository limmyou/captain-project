# app/services/soil_service.py
import requests
import xml.etree.ElementTree as ET
import numpy as np
from app.core.config import SOIL_API_KEY

SOIL_API_URL = "http://apis.data.go.kr/1390802/SoilEnviron/SoilExam/V2/getSoilExamList"


def _safe_float(value):
    try:
        return float(value) if value not in [None, ""] else None
    except ValueError:
        return None


def get_soil_data(stdg_cd: str) -> dict:
    if not SOIL_API_KEY:
        raise ValueError("SOIL_API_KEY가 설정되지 않았습니다.")

    ph_list = []
    om_list = []
    ca_list = []
    mg_list = []
    k_list = []
    ec_list = []

    page = 1

    while True:
        params = {
            "serviceKey": SOIL_API_KEY,
            "Page_Size": "100",
            "Page_No": str(page),
            "STDG_CD": stdg_cd
        }

        try:
            res = requests.get(SOIL_API_URL, params=params, timeout=15)
            res.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"토양 API 요청 실패: {e}")

        print("==== SOIL API DEBUG ====")
        print("STDG_CD:", stdg_cd)
        print("PAGE:", page)
        print(res.text[:1000])   # 처음 1000자만 확인
        print("========================")

        try:
            root = ET.fromstring(res.text)
        except ET.ParseError as e:
            raise ValueError(f"토양 API XML 파싱 실패: {e}")

        items = root.findall(".//item")

        if not items:
            break

        for item in items:
            ph = _safe_float(item.findtext("ACID"))
            om = _safe_float(item.findtext("OM"))
            ca = _safe_float(item.findtext("POSIFERT_CA"))
            mg = _safe_float(item.findtext("POSIFERT_MG"))
            k = _safe_float(item.findtext("POSIFERT_K"))
            ec = _safe_float(item.findtext("ELCD"))

            if ph is not None:
                ph_list.append(ph)
            if om is not None:
                om_list.append(om)
            if ca is not None:
                ca_list.append(ca)
            if mg is not None:
                mg_list.append(mg)
            if k is not None:
                k_list.append(k)
            if ec is not None:
                ec_list.append(ec)

        page += 1

    if not any([ph_list, om_list, ca_list, mg_list, k_list, ec_list]):
        return {
        "pH": None,
        "OM": None,
        "Ca": None,
        "Mg": None,
        "K": None,
        "EC": None,
        "CEC": None,
        "has_data": False,
        "message": f"토양 데이터 없음: STDG_CD={stdg_cd}"
    }

    ca_mean = float(np.mean(ca_list)) if ca_list else 0.0
    mg_mean = float(np.mean(mg_list)) if mg_list else 0.0
    k_mean = float(np.mean(k_list)) if k_list else 0.0

    return {
        "pH": float(np.mean(ph_list)) if ph_list else None,
        "OM": float(np.mean(om_list)) / 10 if om_list else None,
        "Ca": ca_mean,
        "Mg": mg_mean,
        "K": k_mean,
        "EC": float(np.mean(ec_list)) if ec_list else None,
        "CEC": ca_mean + mg_mean + k_mean,
        "has_data": True,
        "message": "정상 조회"
    }

def get_soil_data_with_fallback(stdg_cd: str) -> dict:
    try:
        soil = get_soil_data(stdg_cd)
        if soil.get("has_data"):
            return soil
    except Exception:
        pass

    return {
        "pH": 5.47,
        "OM": 1.41,
        "Ca": 2.5,
        "Mg": None,
        "K": None,
        "EC": 0.55,
        "CEC": 5.2,
        "has_data": False,
        "message": "기본값 사용"
    }