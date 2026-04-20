import os
import geopandas as gpd
import rasterio
from rasterio import features
from rasterio.transform import from_bounds


def create_soil_tifs(
    shp_path: str,
    output_dir: str,
    data_values: dict,
    pixel_size: float = 0.0001,
    padding: float = 0.1,
    target_crs: str = "EPSG:4326",
    nodata_value: float = -9999.0
):
    os.makedirs(output_dir, exist_ok=True)

    gdf = gpd.read_file(shp_path)

    if gdf.empty:
        raise ValueError("입력 shapefile이 비어 있습니다.")

    if gdf.crs is None:
        raise ValueError("입력 shapefile의 CRS 정보가 없습니다.")

    if gdf.crs.to_string() != target_crs:
        gdf = gdf.to_crs(target_crs)

    geom = gdf.union_all() if hasattr(gdf, "union_all") else gdf.unary_union

    minx, miny, maxx, maxy = gdf.total_bounds
    w_dist = maxx - minx
    h_dist = maxy - miny

    if w_dist == 0 or h_dist == 0:
        raise ValueError("polygon bounds가 비정상입니다.")

    bounds = [
        minx - w_dist * padding,
        miny - h_dist * padding,
        maxx + w_dist * padding,
        maxy + h_dist * padding
    ]

    raw_width = max(1, int((bounds[2] - bounds[0]) / pixel_size))
    raw_height = max(1, int((bounds[3] - bounds[1]) / pixel_size))

    # 모델 입력 크기 맞춤용 16배수
    width = max(16, ((raw_width + 15) // 16) * 16)
    height = max(16, ((raw_height + 15) // 16) * 16)

    transform = from_bounds(*bounds, width, height)

    output_paths = {}

    for var_name, value in data_values.items():
        if value is None:
            continue

        out_path = os.path.join(output_dir, f"{var_name}_fin.tif")

        rasterized = features.rasterize(
            [(geom, float(value))],
            out_shape=(height, width),
            transform=transform,
            fill=nodata_value,
            all_touched=True,
            dtype="float32"
        )

        with rasterio.open(
            out_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="float32",
            crs=target_crs,
            transform=transform,
            nodata=nodata_value
        ) as dst:
            dst.write(rasterized, 1)

        output_paths[var_name] = out_path

    if not output_paths:
        raise ValueError("생성할 tif가 없습니다. data_values를 확인하세요.")

    return output_paths