# 라이브러리 임포트
import gc
import os
import re
import sys
import copy
import hashlib
from pathlib import Path

import rasterio
import numpy as np
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from skimage import measure
from rasterio import features
from rasterio.warp import reproject
from rasterio.enums import Resampling
from rasterio.transform import from_bounds

CAPTAIN_PROJECT_DIR=Path(r"C:\Users\heeli\Downloads\captain-project")
sys.path.append(str(CAPTAIN_PROJECT_DIR))

from captain.init_captain_custom_sim import CustomStateInitializer
from captain.biodivsim.SimGrid import SimGrid
from captain.biodivsim.BioDivEnv import BioDivEnv
from captain.biodivsim.DisturbanceGenerator import InitialConstUniformDisturbanceGenerator
from captain.biodivsim.ClimateGenerator import get_climate
from captain.plot.plot_env import plot_env_state, _plot_env_state_init


_ORIG_DEEPCOPY = copy.deepcopy

def _safe_deepcopy(obj, memo=None):
    if isinstance(obj, SimGrid):
        return obj 
    return _ORIG_DEEPCOPY(obj, memo)

copy.deepcopy = _safe_deepcopy

class MaskedStateInitializer(CustomStateInitializer):
    def __init__(self, scenario, grid_size, mask_array=None):
        super().__init__(scenario, grid_size)
        self.mask_array = mask_array
        if mask_array is not None:
            self.mask_coords = np.argwhere(mask_array == 1)

    def getInitialState(self, K, num_species, length):
        h = super().getInitialState(K, num_species, length)

        if self.mask_array is None:
            return h

        # Moss_A 패치를 지역 마스크 안에서만 뿌리기
        moss_patches = 3
        patch_size = 12
        for _ in range(moss_patches):
            if len(self.mask_coords) > 0:
                idx = np.random.choice(len(self.mask_coords))
                cx, cy = self.mask_coords[idx]
                half = patch_size // 2
                x0 = max(cx - half, 0)
                x1 = min(cx + half, length)
                y0 = max(cy - half, 0)
                y1 = min(cy + half, length)
                patch = (np.random.rand(x1-x0, y1-y0) > 0.4).astype(np.float64)
                h[0, x0:x1, y0:y1] = patch * (K // (2 * moss_patches))

        # 마스크 밖이라면 모든 종의 개체수를 0으로
        mask_bool = self.mask_array.astype(bool)
        for sp in range(num_species):
            h[sp, ~mask_bool] = 0.0

        return h


def read_to_target_grid(tif_path, dst_shape, dst_transform, dst_crs):
    with rasterio.open(tif_path) as src:
        src_arr = src.read(1).astype(np.float32)
        nodata = src.nodata
        if nodata is not None:
            src_arr = np.where(src_arr == nodata, np.nan, src_arr)

        dst_arr = np.full(dst_shape, np.nan, dtype=np.float32)

        reproject(
            source=src_arr,
            destination=dst_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear
        )
    return dst_arr

# 레이어별 점수화
def minmax01(arr, mask=None):
    arr2 = arr.copy()
    if mask is not None:
        arr2 = np.where(mask, arr2, np.nan)

    valid = np.isfinite(arr2)
    if not np.any(valid):
        return np.zeros_like(arr, dtype=np.float32)

    vmin = np.nanmin(arr2[valid])
    vmax = np.nanmax(arr2[valid])
    if vmax - vmin < 1e-12:
        out = np.zeros_like(arr, dtype=np.float32)
        out[valid] = 1.0
        return out

    out = (arr2 - vmin) / (vmax - vmin)
    out = np.nan_to_num(out, nan=0.0).astype(np.float32)
    return out

def score_ph(ph_arr, mask=None, optimal=6.5, width=1.0):
    ph = ph_arr.copy()
    if mask is not None:
        ph = np.where(mask, ph, np.nan)
    s = np.exp(-((ph - optimal) / width) ** 2).astype(np.float32)
    s = np.nan_to_num(s, nan=0.0)
    return s

def overlay_boundary(ax, contours, color='red'):
    for contour in contours:
        ax.plot(contour[:,1], contour[:,0], color=color, linewidth=2)

# ====================== MAIN 실행부 =======================

def run_simulation(
    site,
    shp_path,
    tif_dir,
    output_root="simulation_output",
    grid_size=100,
    n_years=10,
    n_species=9,
    cell_capacity=25,
    alpha=0.09,
    mosby_fraction=0.2,
    mosby_factor=1.3,
    seed=42,
):
    np.random.seed(seed)

    gdf = gpd.read_file(shp_path)

    if gdf.crs is None:
        raise ValueError("SHP에 CRS가 없습니다.")
    dst_crs = gdf.crs

    bounds = gdf.total_bounds
    transform = from_bounds(*bounds, grid_size, grid_size)

    # SHP 영역 마스크 생성
    mask_arr_polygon = features.rasterize(
        [(geom, 1) for geom in gdf.geometry],
        out_shape=(grid_size, grid_size),
        transform=transform,
        fill=0,
        dtype="uint8"
    ).astype(int)

    final_mask = mask_arr_polygon
    print(f"지형 마스크 생성 완료.")

    # TIF 레이어 로드
    tif_files = ["Ca_fin.tif", "OM_fin.tif", "pH_fin.tif", "CEC_fin.tif", "EC_fin.tif"]
    layers = {}

    for tif_name in tif_files:
        full_path = os.path.join(tif_dir, tif_name)
        if not os.path.exists(full_path):
            print(f"[경고] 파일을 찾을 수 없습니다: {full_path}")
            continue
        arr = read_to_target_grid(
            tif_path=full_path,
            dst_shape=(grid_size, grid_size),
            dst_transform=transform,
            dst_crs=dst_crs
        )
        layers[tif_name] = arr

    if len(layers) == 0:
        raise RuntimeError("TIF 레이어가 없습니다")

    # 레이어별 점수화
    mask_bool = final_mask.astype(bool)

    scored_layers = []
    used_layer_names = []

    for name, arr in layers.items():
        low = name.lower()
        arr_in = np.where(mask_bool, arr, np.nan)

        if "ph" in low:
            s = score_ph(arr_in, mask=mask_bool, optimal=6.5, width=1.0)
            scored_layers.append(s)
            used_layer_names.append(name + "(pH_scored)")
        else:
            s = minmax01(arr_in, mask=mask_bool)
            scored_layers.append(s)
            used_layer_names.append(name + "(minmax)")

    env_score = np.mean(np.stack(scored_layers, axis=0), axis=0)
    env_score = np.where(mask_bool, env_score, 0.0).astype(np.float32)

    final_env = env_score
    print(f"[INFO] 사용된 레이어 수: {len(used_layer_names)}")
    print(f"[INFO] 사용된 레이어: {used_layer_names}")
    print(f"[INFO] final_env range: {final_env.min():.4f} ~ {final_env.max():.4f}")


    disturbance_initializer = InitialConstUniformDisturbanceGenerator(counter=0, magnitude=0.0)
    disturbance_sensitivity = np.ones(n_species)
    climate_generator, _ = get_climate(mode=3)
    growth_rate = np.array([1.5] + [1]*(n_species-1))


    mosby_mask = (final_mask == 1) & (np.random.rand(*final_mask.shape) < mosby_fraction)

    valid_area = int((final_mask == 1).sum())
    applied_area = int(mosby_mask.sum())
    applied_pct = (applied_area / valid_area * 100) if valid_area > 0 else 0
    print(f"[MOSBY MASK] target~{mosby_fraction*100:.1f}% | applied={applied_area}/{valid_area} ({applied_pct:.2f}%)")

    # env 생성 함수
    def build_env():
        custom_init_obj = MaskedStateInitializer(
            scenario="sequential_restoration",
            grid_size=grid_size,
            mask_array=final_mask
        )
        env = BioDivEnv(
            budget=0.5, gridInitializer=custom_init_obj, length=grid_size, n_species=n_species,
            alpha=alpha, K_max=cell_capacity, dispersal_rate=0.0,
            disturbanceGenerator=disturbance_initializer, disturbance_sensitivity=disturbance_sensitivity,
            max_fraction_protected=1, immediate_capacity=False, truncateToInt=False,
            species_threshold=1, K_disturbance_coeff=1, climateModel=climate_generator,
            climate_sensitivity=np.zeros(n_species), climate_as_disturbance=0, iterations=n_years,
            resolution=np.array([5, 5]), growth_rate=growth_rate, selectivedisturbanceInitializer=0,
            selective_sensitivity=np.zeros(n_species), list_species_values=np.ones(n_species)
        )
        return env
    
    # 공통 초기 상태 1회 생성
    base_env = build_env()
    np.random.seed(seed)
    base_env.reset()

    # BEFORE / AFTER 모두 같은 시작 상태 사용
    initial_h = np.array(base_env.bioDivGrid.h, copy=True)

    del base_env
    gc.collect()

    # 실행 + 저장 함수
    def run_and_save(label, apply_mosby):
        print(f"[{label}] mosby_mask sum:", int(mosby_mask.sum()))
        print(f"[{label}] mosby_mask md5:", hashlib.md5(mosby_mask.tobytes()).hexdigest())

        env = build_env()

        # 초기 상태 재현성
        np.random.seed(seed)
        env.reset()
        env.bioDivGrid.h = np.array(initial_h, copy=True)

        # K 설정
        K_2d = cell_capacity * final_env
        if apply_mosby:
            K_2d[mosby_mask] *= mosby_factor
            print(f"[{label}] mosby applied: K x{mosby_factor}")
        else:
            print(f"[{label}] mosby NOT applied")

        env.bioDivGrid._K = K_2d

        # K 적용 확인
        k_mosby = float(np.mean(K_2d[mosby_mask])) if mosby_mask.any() else 0.0
        k_non   = float(np.mean(K_2d[(final_mask == 1) & (~mosby_mask)])) if ((final_mask == 1) & (~mosby_mask)).any() else 0.0
        print(f"[{label}] K mean mosby={k_mosby:.4f} | non-mosby={k_non:.4f}")

        # 저장 폴더
        base_dir = os.path.join(output_root, f"{site}_{label}")
        os.makedirs(base_dir, exist_ok=True)
        image_dir = os.path.join(base_dir, 'images')
        os.makedirs(image_dir, exist_ok=True)

        polygon_contours = measure.find_contours(final_mask, 0.5)

        allowed_categories = ['species richness', 'mean population density'] + [f"sp.{i}" for i in range(n_species)]
        for cat in allowed_categories:
            os.makedirs(os.path.join(image_dir, cat.replace(' ', '_')), exist_ok=True)


        plot_years = [1, 3, 5, 10]
        exclude_keywords = ["total population size", "phylogenetic diversity", "variables through time"]

        np.random.seed(seed)
        for i in range(n_years):
            env.step()

            if (i + 1) in plot_years:
                year = i + 1
                env.currentIteration = year

                plot_env_state(env, wd=base_dir, outfile=f"{site}_{label}", file_format="one_pdf")

                figs, titles = _plot_env_state_init(env=env, species_list=list(range(n_species)), plot_titles=True)
                for j, title in enumerate(titles):
                    ax = figs[j].axes[0]
                    low_title = title.strip().lower()

                    if not any(ex in low_title for ex in exclude_keywords):
                        overlay_boundary(ax, polygon_contours, color='red')

                    target_cat = None
                    if "species richness" in low_title:
                        target_cat = "species_richness"
                    elif "mean population density" in low_title:
                        target_cat = "mean_population_density"
                    else:
                        match = re.search(r'\d+', low_title)
                        if match:
                            sp_num = match.group()
                            target_cat = f"sp.{sp_num}"

                    if target_cat:
                        folder_path = os.path.join(image_dir, target_cat)
                        filename = os.path.join(folder_path, f"{target_cat}_year_{year}.png")
                        figs[j].savefig(filename)

                    plt.close(figs[j])

        print(f"[{label}] done -> {base_dir}")

        # env 메모리 정리
        del env
        gc.collect()
        return base_dir 

    # BEFORE / AFTER 둘 다 실행
    before_dir = run_and_save(label="BEFORE", apply_mosby=False)
    after_dir = run_and_save(label="AFTER", apply_mosby=True)

    print("\n시뮬레이션 완료!")

    return {
        "before_dir": before_dir,
        "after_dir": after_dir,
        "mosby_mask_md5": hashlib.md5(mosby_mask.tobytes()).hexdigest(),
    }