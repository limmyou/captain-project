import geopandas as gpd
from shapely.geometry import Point, box


def create_square_polygon_from_point(
    lat: float,
    lon: float,
    output_path: str | None = None,
    half_size_m: int = 1000
) -> gpd.GeoDataFrame:
    
    """
    중심 좌표(lat, lon)를 기준으로
    반경 half_size_m 만큼의 정사각형 polygon 생성.
    기본값 1000m -> 총 2km x 2km
    """

    # WGS84 포인트 생성
    point_gdf = gpd.GeoDataFrame(
        geometry=[Point(lon, lat)],
        crs="EPSG:4326"
    )

    # 미터 단위 좌표계로 변환
    point_proj = point_gdf.to_crs("EPSG:5179")
    point_geom = point_proj.geometry.iloc[0]

    x, y = point_geom.x, point_geom.y

    # 중심 기준 ±1000m 사각형
    square = box(
        x - half_size_m,
        y - half_size_m,
        x + half_size_m,
        y + half_size_m
    )

    square_gdf = gpd.GeoDataFrame(
        geometry=[square],
        crs="EPSG:5179"
    ).to_crs("EPSG:4326")

    # 저장
    if output_path:
        square_gdf.to_file(output_path)

    return square_gdf