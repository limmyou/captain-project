from fastapi import FastAPI, HTTPException
from app.services.geocode_service import geocode
from app.services.admin_service import get_admin_info
from app.services.soil_service import get_soil_data, get_soil_data_with_fallback
from app.services.tif_service import create_soil_tifs
from app.services.osm_service import get_osm_polygon
from app.services.point_polygon_service import create_square_polygon_from_point
from app.services.naver_geocode_service import naver_geocode

app = FastAPI()


@app.get("/")
def root():
    return {"message": "ok"}


@app.get("/predict")
def predict(address: str):
    try:
        lat, lon = geocode(address)
        admin_info = get_admin_info(lat, lon)
        soil_data = get_soil_data(admin_info["stdg_cd"])

        return {
            "address": address,
            "lat": lat,
            "lon": lon,
            "admin_info": {
                "emd_cd": admin_info["emd_cd"],
                "stdg_cd": admin_info["stdg_cd"],
                "emd_nm": admin_info["emd_nm"]
            },
            "soil_data": soil_data
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/simulate")
def simulate(site: str, shp_path: str, tif_dir: str):
    try:
        from app.services.simulation_service import run_simulation

        result = run_simulation(
            site=site,
            shp_path=shp_path,
            tif_dir=tif_dir,
            output_root="simulation_output"
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/run_from_address")
def run_from_address(address: str):
    try:
        from app.services.simulation_service import run_simulation
        import os

        polygon_source = "osm"
        lat, lon = None, None

        # 1) OSM에서 polygon 찾기
        try:
            gdf = get_osm_polygon(address)
            site_name = address.replace(" ", "_")
        except Exception:
            polygon_source = "osm_fallback"

            # 2) OSM 실패 후 네이버 geocoding 사용
            try:
                lat, lon = naver_geocode(address)
            except Exception:
                raise ValueError(f"주소 변환 실패: {address}")

            # 행정구역 정보 로드 후 polygon 생성
            admin_info = get_admin_info(lat, lon)
            gdf = create_square_polygon_from_point(
                lat=lat,
                lon=lon,
                half_size_m=1000
            )
            site_name = address.replace(" ", "_")

        # 이후 동일한 로직
        shp_dir = f"run_data/{site_name}/shp"
        tif_dir = f"run_data/{site_name}/tifs"

        os.makedirs(shp_dir, exist_ok=True)
        os.makedirs(tif_dir, exist_ok=True)

        shp_path = f"{shp_dir}/{site_name}.shp"
        gdf.to_file(shp_path)

        soil = get_soil_data_with_fallback("dummy")

        tif_paths = create_soil_tifs(
            shp_path=shp_path,
            output_dir=tif_dir,
            data_values={
                "Ca": soil["Ca"],
                "OM": soil["OM"],
                "CEC": soil["CEC"],
                "pH": soil["pH"],
                "EC": soil["EC"]
            }
        )

        result = run_simulation(
            site=site_name,
            shp_path=shp_path,
            tif_dir=tif_dir,
            output_root="simulation_output"
        )

        return {
            "address": address,
            "lat": lat,
            "lon": lon,
            "polygon_source": polygon_source,
            "shp_path": shp_path,
            "tif_paths": tif_paths,
            "simulation_result": result
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))