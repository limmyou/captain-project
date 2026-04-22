from pathlib import Path
import os
import glob
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from app.services.geocode_service import geocode
from app.services.admin_service import get_admin_info
from app.services.soil_service import get_soil_data_with_fallback
from app.services.tif_service import create_soil_tifs
from app.services.simulation_service import run_simulation

app = FastAPI(title="COFN Restoration Simulation API")

os.makedirs("static", exist_ok=True)
os.makedirs("simulation_output", exist_ok=True)
os.makedirs("run_data", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/simulation_output", StaticFiles(directory="simulation_output"), name="simulation_output")
app.mount("/run_data", StaticFiles(directory="run_data"), name="run_data")

# 개발 단계에서는 전체 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
HTML_FILE = BASE_DIR / "templates" / "index.html"
# 처음에는 테스트용 shp를 고정
BOUNDARY_SHP_PATH = BASE_DIR / "data" / "UMD_ALL.shp"
OUTPUT_TIF_DIR = BASE_DIR / "output_tifs"
SIM_OUTPUT_DIR = BASE_DIR / "simulation_output"


class SimulationRequest(BaseModel):
    address: str
    scenario: str = "mosby"
    n_species: int = 9
    grid_size: int = 100
    period: str = "long"   # short / long
    client_name: str | None = None
    client_email: EmailStr | None = None


@app.get("/")
def serve_index():
    if not HTML_FILE.exists():
        raise HTTPException(status_code=404, detail="HTML 파일을 찾을 수 없습니다.")
    return FileResponse(str(HTML_FILE))


@app.post("/api/simulate")
def simulate(req: SimulationRequest):
    print("=== /api/simulate called ===", flush=True)
    print("address:", req.address, flush=True)
    print("scenario:", req.scenario, flush=True)
    try:
        if not req.address.strip():
            raise HTTPException(status_code=400, detail="주소를 입력해주세요.")

        if req.grid_size not in [50, 100]:
            raise HTTPException(status_code=400, detail="grid_size는 50 또는 100만 가능합니다.")

        if not (1 <= req.n_species <= 9):
            raise HTTPException(status_code=400, detail="n_species는 1~9 사이여야 합니다.")

        if req.period not in ["short", "long"]:
            raise HTTPException(status_code=400, detail="period는 short 또는 long 이어야 합니다.")

        if req.scenario not in ["mosby", "sequential", "passive"]:
            raise HTTPException(status_code=400, detail="scenario 값이 올바르지 않습니다.")

        if not BOUNDARY_SHP_PATH.exists():
            raise HTTPException(
                status_code=500,
                detail=f"행정구역 shp 파일이 없습니다: {BOUNDARY_SHP_PATH}"
            )

        # 1. 주소 -> 좌표
        lat, lon = geocode(req.address)
        print("🔥 geocode result:", lat, lon, flush=True)
        # 2. 좌표 -> 행정구역
        admin_info = get_admin_info(lat, lon)
        print("🔥 admin_info ok:", admin_info.get("emd_cd"), flush=True)



        # 3. 해당 행정구역 geometry 하나만 shp로 저장
        site_name = req.address.replace(" ", "_")
        run_base_dir = BASE_DIR / "run_data" / site_name
        run_shp_dir = run_base_dir / "shp"
        run_tif_dir = run_base_dir / "tifs"

        os.makedirs(str(run_shp_dir), exist_ok=True)
        os.makedirs(str(run_tif_dir), exist_ok=True)

        site_shp_path = run_shp_dir / f"{site_name}.shp"
        import geopandas as gpd
        site_gdf = gpd.GeoDataFrame(
            [{"name": site_name, "emd_cd": admin_info["emd_cd"]}],
            geometry=[admin_info["geometry"]],
            crs="EPSG:4326"
        )

        site_gdf.to_file(str(site_shp_path), encoding="utf-8")

        # 4. 행정구역 -> 토양 데이터
        soil_data = get_soil_data_with_fallback(admin_info["stdg_cd"])

        safe_soil_data = {
            "Ca": soil_data.get("Ca") if soil_data.get("Ca") is not None else 2.5,
            "OM": soil_data.get("OM") if soil_data.get("OM") is not None else 1.41,
            "CEC": soil_data.get("CEC") if soil_data.get("CEC") is not None else 5.2,
            "pH": soil_data.get("pH") if soil_data.get("pH") is not None else 5.47,
            "EC": soil_data.get("EC") if soil_data.get("EC") is not None else 0.55,
        }
        print("🚀 BEFORE create_soil_tifs", flush=True)
        # 5. 토양 tif 생성
        tif_result = create_soil_tifs(
            shp_path=str(site_shp_path),
            output_dir=str(run_tif_dir),
            data_values=safe_soil_data
        )
        print("🚀 AFTER create_soil_tifs", flush=True)

        # 6. 기간 설정
        n_years = 3 if req.period == "short" else 20

        print("req.n_species =", req.n_species)
        print("req.grid_size =", req.grid_size)
        print("req.address =", req.address)


        # 7. 시뮬레이션 실행
        print("🚀 BEFORE run_simulation", flush=True)
        sim_result = run_simulation(
            site=site_name,
            shp_path=str(site_shp_path),
            tif_dir=str(run_tif_dir),
            output_root=str(SIM_OUTPUT_DIR),
            grid_size=req.grid_size,
            n_years=n_years,
            n_species=req.n_species
        )
        print("🚀 AFTER run_simulation", flush=True)
        
        # 8. 생성된 이미지 경로 수집
        before_images = sorted(
            glob.glob(os.path.join(sim_result["before_dir"], "images", "**", "*.png"), recursive=True)
        )
        after_images = sorted(
            glob.glob(os.path.join(sim_result["after_dir"], "images", "**", "*.png"), recursive=True)
        )

        def to_web_path(path_str: str) -> str:
            path_str = path_str.replace("\\", "/")
            base_str = str(BASE_DIR).replace("\\", "/")

            if path_str.startswith(base_str):
                path_str = path_str[len(base_str):]

            if not path_str.startswith("/"):
                path_str = "/" + path_str

            return path_str

        def pick_image(base_dir: str, relative_path: str) -> str:
            full_path = os.path.join(base_dir, "images", relative_path)
            if os.path.exists(full_path):
                return to_web_path(full_path)
            return ""

        before_image_urls = [to_web_path(p) for p in before_images]
        after_image_urls = [to_web_path(p) for p in after_images]

        selected_years = [1, 2, 3] if req.period == "short" else [1, 5, 10, 15]
        mosby_year = 3 if req.period == "short" else 5

        before_dir = sim_result["before_dir"]
        after_dir = sim_result["after_dir"]

        mosby_compare = {
            "before": pick_image(before_dir, f"sp.0/sp.0_year_{mosby_year}.png"),
            "after": pick_image(after_dir, f"sp.0/sp.0_year_{mosby_year}.png"),
            "year": mosby_year,
        }

        richness_maps = [
            {
                "year": y,
                "image": pick_image(after_dir, f"species_richness/species_richness_year_{y}.png")
            }
            for y in selected_years
        ]

        density_maps = [
            {
                "year": y,
                "image": pick_image(after_dir, f"mean_population_density/mean_population_density_year_{y}.png")
            }
            for y in selected_years
        ]

        # 9. KPI 계산
        final_year = selected_years[-1]

        final_richness = next(
            (item for item in richness_maps if item["year"] == final_year),
            None
        )
        final_density = next(
            (item for item in density_maps if item["year"] == final_year),
            None
        )

        final_richness_value = sim_result.get("final_richness", 0.0)
        final_density_value = sim_result.get("final_density", 0.0)
        restoration_active_area = sim_result.get("restoration_active_area", 0.0)
        richness_means = sim_result.get("richness_means", {})
        density_means = sim_result.get("density_means", {})


        return {
            "success": True,
            "message": "시뮬레이션이 완료되었습니다.",
            "input": {
                "address": req.address,
                "scenario": req.scenario,
                "period": req.period,
                "n_species": req.n_species,
                "grid_size": req.grid_size,
                "client_name": req.client_name,
                "client_email": str(req.client_email) if req.client_email else None,
            },
            "location": {
                "lat": lat,
                "lon": lon,
                "emd_cd": admin_info.get("emd_cd"),
                "stdg_cd": admin_info.get("stdg_cd"),
                "emd_nm": admin_info.get("emd_nm"),
            },
            "soil_data": soil_data,
            "tif_result": tif_result,
            "simulation": {
                "before_dir": before_dir,
                "after_dir": after_dir,
                "mosby_mask_md5": sim_result["mosby_mask_md5"],
                "before_image_count": len(before_images),
                "after_image_count": len(after_images),
                "before_images": before_image_urls,
                "after_images": after_image_urls,
                "selected_years": selected_years,
                "mosby_compare": mosby_compare,
                "richness_maps": richness_maps,
                "density_maps": density_maps,
                "final_year": final_year,
                "final_richness": final_richness_value,
                "final_density": final_density_value,
                "restoration_active_area": restoration_active_area,
                "richness_means": richness_means,   # 추가
                "density_means": density_means,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))