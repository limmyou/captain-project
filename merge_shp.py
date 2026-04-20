import geopandas as gpd
import pandas as pd
import os

def merge_shp_files(shp_dir: str, output_path: str):
    shp_files = [f for f in os.listdir(shp_dir) if f.endswith(".shp")]

    gdfs = []

    for shp_file in shp_files:
        # ❗ 별파랑공원 같은 개인 shp 제외 (중요)
        if "LSMD" not in shp_file:
            print(f"스킵: {shp_file}")
            continue

        path = os.path.join(shp_dir, shp_file)
        print(f"읽는 중: {path}")

        gdf = gpd.read_file(path)

        # 🔥 핵심: CRS 통일
        gdf = gdf.to_crs("EPSG:4326")

        gdfs.append(gdf)

    merged = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True))

    merged.to_file(output_path)
    print(f"완료: {output_path}")


if __name__ == "__main__":
    merge_shp_files(
        shp_dir="data",
        output_path="data/UMD_ALL.shp"
    )