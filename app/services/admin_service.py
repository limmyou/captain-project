# app/services/admin_service.py
import geopandas as gpd
from shapely.geometry import Point
from functools import lru_cache
from app.core.config import EMD_SHAPEFILE_PATH


@lru_cache(maxsize=1)
def load_emd_boundary() -> gpd.GeoDataFrame:
    if not EMD_SHAPEFILE_PATH:
        raise ValueError("EMD_SHAPEFILE_PATH가 설정되지 않았습니다.")

    gdf = gpd.read_file(EMD_SHAPEFILE_PATH, encoding="euc-kr")

    if gdf.empty:
        raise ValueError("행정구역 shapefile이 비어 있습니다.")

    return gdf


def get_admin_info(lat: float, lon: float) -> dict:
    emd = load_emd_boundary()

    point = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    point = point.to_crs(emd.crs)
    point_geom = point.iloc[0]

    target = emd[emd.intersects(point_geom)]

    if target.empty:
        raise ValueError("해당 좌표를 포함하는 행정구역을 찾을 수 없습니다.")

    row = target.iloc[0]

    emd_cd = str(row["EMD_CD"])
    stdg_cd = emd_cd + "00"

    return {
        "emd_cd": emd_cd,
        "stdg_cd": stdg_cd,
        "emd_nm": row.get("EMD_NM"),
        "geometry": row.geometry
    }