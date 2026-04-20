# app/core/config.py
import os
from dotenv import load_dotenv

load_dotenv()

VWORLD_API_KEY = os.getenv("VWORLD_API_KEY")
SOIL_API_KEY = os.getenv("SOIL_API_KEY")
EMD_SHAPEFILE_PATH = os.getenv("EMD_SHAPEFILE_PATH")
NAVER_MAPS_CLIENT_ID = os.getenv("NAVER_MAPS_CLIENT_ID")
NAVER_MAPS_CLIENT_SECRET = os.getenv("NAVER_MAPS_CLIENT_SECRET")