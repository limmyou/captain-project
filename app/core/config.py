# app/core/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 경로
BASE_DIR = Path(__file__).resolve().parents[2]

# .env 경로
ENV_PATH = BASE_DIR / ".env"

# .env 로드
load_dotenv(dotenv_path=ENV_PATH)

# 환경변수 읽기
VWORLD_API_KEY = os.getenv("VWORLD_API_KEY")
SOIL_API_KEY = os.getenv("SOIL_API_KEY")
EMD_SHAPEFILE_PATH = os.getenv("EMD_SHAPEFILE_PATH")
NAVER_MAPS_CLIENT_ID = os.getenv("NAVER_MAPS_CLIENT_ID")
NAVER_MAPS_CLIENT_SECRET = os.getenv("NAVER_MAPS_CLIENT_SECRET")
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")

# 디버깅 출력
print("CONFIG DEBUG - ENV_PATH:", ENV_PATH)
print("CONFIG DEBUG - KAKAO_API_KEY exists:", bool(KAKAO_API_KEY))