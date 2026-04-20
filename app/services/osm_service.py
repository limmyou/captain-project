import requests
import geopandas as gpd
from shapely.geometry import shape, Polygon, MultiPolygon

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    "User-Agent": "captain-project/1.0 (contact: your-real-email@company.com)"
}

def get_osm_polygon(place_name: str) -> gpd.GeoDataFrame:
    params = {
        "q": place_name,
        "format": "jsonv2",
        "limit": 10,
        "polygon_geojson": 1,
        "addressdetails": 1,
        "accept-language": "ko",
        "email": "hrkang@c-of-n.com"
    }

    res = requests.get(
        NOMINATIM_URL,
        params=params,
        headers=HEADERS,
        timeout=30
    )
    res.raise_for_status()
    results = res.json()

    if not results:
        raise ValueError(f"OSM에서 '{place_name}' 검색 결과가 없습니다.")

    polygons = []
    for item in results:
        geojson = item.get("geojson")
        if not geojson:
            continue

        try:
            geom = shape(geojson)
        except Exception:
            continue

        if isinstance(geom, (Polygon, MultiPolygon)) and not geom.is_empty:
            polygons.append({
                "geometry": geom,
                "display_name": item.get("display_name")
            })

    if not polygons:
        raise ValueError(f"OSM에서 '{place_name}' polygon을 찾을 수 없습니다.")

    polygons.sort(key=lambda x: x["geometry"].area, reverse=True)
    return gpd.GeoDataFrame([polygons[0]], geometry="geometry", crs="EPSG:4326")