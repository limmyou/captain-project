# 라이브러리 임포트
import glob
import os
import traceback
from pathlib import Path

import geopandas as gpd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

from app.services.admin_service import get_admin_info
from app.services.geocode_service import geocode
from app.services.simulation_service import run_simulation
from app.services.soil_service import get_soil_data_with_fallback
from app.services.tif_service import create_soil_tifs


app = FastAPI(title="COFN Restoration Simulation API")


# ====================== 경로 설정 ======================
BASE_DIR = Path(__file__).resolve().parent
HTML_FILE = BASE_DIR / "templates" / "index.html"
BOUNDARY_SHP_PATH = BASE_DIR / "data" / "UMD_ALL.shp"
SIM_OUTPUT_DIR = BASE_DIR / "simulation_output"
RUN_DATA_DIR = BASE_DIR / "run_data"  # [수정] run_data 경로를 상수로 분리


for directory in ["static", str(SIM_OUTPUT_DIR), str(RUN_DATA_DIR)]:
    os.makedirs(directory, exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/simulation_output", StaticFiles(directory=str(SIM_OUTPUT_DIR)), name="simulation_output")
app.mount("/run_data", StaticFiles(directory=str(RUN_DATA_DIR)), name="run_data")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====================== 요청 모델 ======================
class SimulationRequest(BaseModel):
    address: str
    scenario: str = "mosby"
    n_species: int = 1
    grid_size: int = 20
    period: str = "short"   # short / long
    client_name: str | None = None
    client_email: EmailStr | None = None


# ====================== 공통 함수 ======================
def validate_simulation_request(req: SimulationRequest):
    if not req.address.strip():
        raise HTTPException(status_code=400, detail="주소를 입력해주세요.")

    if req.grid_size not in [20, 30, 50, 100]:
        raise HTTPException(status_code=400, detail="grid_size는 20, 30, 50, 100만 가능합니다.")

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


def make_safe_soil_data(soil_data: dict) -> dict:
    return {
        "Ca": soil_data.get("Ca") if soil_data.get("Ca") is not None else 2.5,
        "OM": soil_data.get("OM") if soil_data.get("OM") is not None else 1.41,
        "CEC": soil_data.get("CEC") if soil_data.get("CEC") is not None else 5.2,
        "pH": soil_data.get("pH") if soil_data.get("pH") is not None else 5.47,
        "EC": soil_data.get("EC") if soil_data.get("EC") is not None else 0.55,
    }


def to_web_path(path_str: str) -> str:
    path_str = path_str.replace("\\", "/")

    if "simulation_output" in path_str:
        path_str = path_str.split("simulation_output")[-1]
        return "/simulation_output" + path_str

    return ""


def pick_image(base_dir: str, relative_path: str) -> str:
    full_path = os.path.join(base_dir, "images", relative_path)
    if os.path.exists(full_path):
        return to_web_path(full_path)
    return ""


# ====================== 라우터 ======================
@app.get("/")
def serve_index():
    if not HTML_FILE.exists():
        raise HTTPException(status_code=404, detail="HTML 파일을 찾을 수 없습니다.")
    return FileResponse(str(HTML_FILE))


@app.get("/db-test")
def db_test():
    import oracledb

    conn = oracledb.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dsn=os.getenv("DB_DSN"),
        config_dir="./wallet",
        wallet_location="./wallet",
        wallet_password=os.getenv("WALLET_PASSWORD")
    )

    cur = conn.cursor()
    cur.execute("SELECT 1 FROM dual")
    result = cur.fetchone()

    cur.close()
    conn.close()

    return {"db": "connected", "result": result[0]}


@app.post("/api/simulate")
def simulate(req: SimulationRequest):
    print("=== /api/simulate called ===", flush=True)
    print("address:", req.address, flush=True)
    print("scenario:", req.scenario, flush=True)

    try:
        validate_simulation_request(req)

        # 주소 -> 좌표
        lat, lon = geocode(req.address)
        print("geocode result:", lat, lon, flush=True)

        # 좌표 -> 행정구역
        admin_info = get_admin_info(lat, lon)
        print("admin_info ok:", admin_info.get("emd_cd"), flush=True)

        # 해당 행정구역 geometry 하나만 shp로 저장
        site_name = req.address.replace(" ", "_")
        run_base_dir = RUN_DATA_DIR / site_name  # [수정] BASE_DIR / "run_data" 대신 RUN_DATA_DIR 사용
        run_shp_dir = run_base_dir / "shp"
        run_tif_dir = run_base_dir / "tifs"

        os.makedirs(str(run_shp_dir), exist_ok=True)
        os.makedirs(str(run_tif_dir), exist_ok=True)

        site_shp_path = run_shp_dir / f"{site_name}.shp"
        site_gdf = gpd.GeoDataFrame(
            [{"name": site_name, "emd_cd": admin_info["emd_cd"]}],
            geometry=[admin_info["geometry"]],
            crs="EPSG:4326"
        )
        site_gdf.to_file(str(site_shp_path), encoding="utf-8")

        # 행정구역 -> 토양 데이터
        soil_data = get_soil_data_with_fallback(admin_info["stdg_cd"])
        safe_soil_data = make_safe_soil_data(soil_data)  # [수정] fallback 로직 분리

        # 토양 tif 생성
        print("BEFORE create_soil_tifs", flush=True)
        tif_result = create_soil_tifs(
            shp_path=str(site_shp_path),
            output_dir=str(run_tif_dir),
            data_values=safe_soil_data
        )
        print("AFTER create_soil_tifs", flush=True)

        # 시뮬레이션 실행 설정
        runtime_grid_size = min(req.grid_size, 20)
        runtime_n_species = 1
        runtime_n_years = 3 if req.period == "short" else 10

        print("req.n_species =", req.n_species, flush=True)
        print("req.grid_size =", req.grid_size, flush=True)
        print("runtime_grid_size =", runtime_grid_size, flush=True)
        print("runtime_n_species =", runtime_n_species, flush=True)
        print("runtime_n_years =", runtime_n_years, flush=True)

        print("BEFORE run_simulation", flush=True)
        sim_result = run_simulation(
            site=site_name,
            shp_path=str(site_shp_path),
            tif_dir=str(run_tif_dir),
            output_root=str(SIM_OUTPUT_DIR),
            grid_size=runtime_grid_size,
            n_years=runtime_n_years,
            n_species=runtime_n_species
        )
        print("AFTER run_simulation", flush=True)

        # 생성된 이미지 경로 수집
        before_dir = sim_result["before_dir"]
        after_dir = sim_result["after_dir"]

        before_images = sorted(
            glob.glob(os.path.join(before_dir, "images", "**", "*.png"), recursive=True)
        )
        after_images = sorted(
            glob.glob(os.path.join(after_dir, "images", "**", "*.png"), recursive=True)
        )

        before_image_urls = [to_web_path(p) for p in before_images]
        after_image_urls = [to_web_path(p) for p in after_images]

        print("BEFORE PATH:", before_images[:3], flush=True)
        print("WEB PATH:", before_image_urls[:3], flush=True)
        print("AFTER PATH:", after_images[:3], flush=True)
        print("AFTER WEB PATH:", after_image_urls[:3], flush=True)

        selected_years = [1, 2, 3] if req.period == "short" else [1, 3, 5, 10]
        mosby_year = 3 if req.period == "short" else 5

        mosby_compare = {
            "before": pick_image(
                before_dir,
                f"mean_population_density/mean_population_density_year_{mosby_year}.png"
            ),
            "after": pick_image(
                after_dir,
                f"mean_population_density/mean_population_density_year_{mosby_year}.png"
            ),
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

        # KPI 값 수집
        final_year = selected_years[-1]
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
                "richness_means": richness_means,
                "density_means": density_means,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))