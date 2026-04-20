import rasterio

paths = [
    "output_tifs/Ca_fin.tif",
    "output_tifs/OM_fin.tif",
    "output_tifs/CEC_fin.tif",
    "output_tifs/pH_fin.tif",
    "output_tifs/EC_fin.tif",
]

for path in paths:
    with rasterio.open(path) as src:
        arr = src.read(1)
        print("=" * 40)
        print("파일:", path)
        print("shape:", arr.shape)
        print("crs:", src.crs)
        print("nodata:", src.nodata)
        print("min:", arr.min())
        print("max:", arr.max())