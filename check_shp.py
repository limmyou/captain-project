import geopandas as gpd
from app.core.config import EMD_SHAPEFILE_PATH

gdf = gpd.read_file(EMD_SHAPEFILE_PATH, encoding="euc-kr")

print("컬럼명:")
print(gdf.columns.tolist())

print("\n샘플 데이터:")
print(gdf.head(3))