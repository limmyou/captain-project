from app.services.tif_service import create_soil_tifs

data_values = {
    "Ca": 2.5,
    "OM": 1.41,
    "CEC": 5.2,
    "pH": 5.47,
    "EC": 0.55
}

shp_path = "data/별파랑공원.shp"
output_dir = "output_tifs"

result = create_soil_tifs(
    shp_path=shp_path,
    output_dir=output_dir,
    data_values=data_values
)

print(result)