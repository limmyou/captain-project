from app.services.simulation_service import run_simulation

result = run_simulation(
    site="별파랑공원",
    shp_path="data/별파랑공원.shp",
    tif_dir="output_tifs",
    output_root="simulation_output"
)

print(result)