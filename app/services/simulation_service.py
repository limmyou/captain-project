import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import gym
sys.modules["gym"] = gym
sys.modules["gymnasium"] = gym

import os
import gc
import copy
import hashlib
import numpy as np
import rasterio
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from skimage import measure
from rasterio import features
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from rasterio.enums import Resampling

from captain.init_captain_custom_sim import CustomStateInitializer
from captain.biodivsim.SimGrid import SimGrid
from captain.biodivsim.BioDivEnv import BioDivEnv
from captain.biodivsim.DisturbanceGenerator import InitialConstUniformDisturbanceGenerator
from captain.biodivsim.ClimateGenerator import get_climate
from captain.plot.plot_env import plot_env_state
from captain.plot.plot_env import _plot_env_state_init


_ORIG_DEEPCOPY = copy.deepcopy

def _safe_deepcopy(obj, memo=None):
    if isinstance(obj, SimGrid):
        return obj
    return _ORIG_DEEPCOPY(obj, memo)

copy.deepcopy = _safe_deepcopy


class CustomStateInitializer2(CustomStateInitializer):
    def __init__(self, scenario, grid_size, mask_array=None):
        super().__init__(scenario, grid_size)
        self.mask_array = mask_array
        if mask_array is not None:
            self.mask_coords = np.argwhere(mask_array == 1)

    def getInitialState(self, K, num_species, length):
        h = super().getInitialState(K, num_species, length)

        if self.mask_array is None:
            return h

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

        mask_bool = self.mask_array.astype(bool)
        for sp in range(h.shape[0]):
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
    return np.nan_to_num(out, nan=0.0).astype(np.float32)


def score_ph(ph_arr, mask=None, optimal=6.5, width=1.0):
    ph = ph_arr.copy()
    if mask is not None:
        ph = np.where(mask, ph, np.nan)
    s = np.exp(-((ph - optimal) / width) ** 2).astype(np.float32)
    return np.nan_to_num(s, nan=0.0)


def run_simulation(
    site: str,
    shp_path: str,
    tif_dir: str,
    output_root: str = "simulation_output",
    grid_size: int = 100,
    n_years: int = 10,
    n_species: int = 9,
    cell_capacity: int = 25,
    alpha: float = 0.09,
    mosby_fraction: float = 0.10,
    mosby_factor: float = 1.20,
    seed: int = 42
):
    print("=== run_simulation entered ===", flush=True)

    import numpy as np
    print("NUMPY VERSION:", np.__version__, flush=True)

    try:
        print("GYM VERSION:", gym.__version__, flush=True)
    except Exception as e:
        print("GYM IMPORT ERROR:", repr(e), flush=True)


    np.random.seed(seed)

    print("before gpd.read_file", flush=True)
    gdf = gpd.read_file(shp_path)
    print("after gpd.read_file", flush=True)
    
    if gdf.empty:
        raise ValueError("입력 shapefile이 비어 있습니다.")
    if gdf.crs is None:
        raise ValueError("SHP에 CRS가 없습니다.")

    dst_crs = gdf.crs
    bounds = gdf.total_bounds
    transform = from_bounds(*bounds, grid_size, grid_size)

    print("before rasterize", flush=True)
    final_mask = features.rasterize(
        [(geom, 1) for geom in gdf.geometry],
        out_shape=(grid_size, grid_size),
        transform=transform,
        fill=0,
        dtype="uint8"
    ).astype(int)
    print("after rasterize", flush=True)


    tif_files = ["Ca_fin.tif", "OM_fin.tif", "pH_fin.tif", "CEC_fin.tif", "EC_fin.tif"]
    layers = {}

    print("before reading tif layers", flush=True)
    for tif_name in tif_files:
        full_path = os.path.join(tif_dir, tif_name)
        if not os.path.exists(full_path):
            continue
        arr = read_to_target_grid(
            tif_path=full_path,
            dst_shape=(grid_size, grid_size),
            dst_transform=transform,
            dst_crs=dst_crs
        )
        layers[tif_name] = arr
    print("after reading tif layers", flush=True)
    
    if not layers:
        raise RuntimeError("사용 가능한 TIF 레이어가 없습니다.")

    mask_bool = final_mask.astype(bool)
    scored_layers = []
    
    for name, arr in layers.items():
        arr_in = np.where(mask_bool, arr, np.nan)
        if "ph" in name.lower():
            scored_layers.append(score_ph(arr_in, mask=mask_bool, optimal=6.5, width=1.0))
        else:
            scored_layers.append(minmax01(arr_in, mask=mask_bool))

    final_env = np.mean(np.stack(scored_layers, axis=0), axis=0)
    final_env = np.where(mask_bool, final_env, 0.0).astype(np.float32)

    disturbance_initializer = InitialConstUniformDisturbanceGenerator(counter=0, magnitude=0.2)
    disturbance_sensitivity = np.ones(n_species)
    climate_generator, _ = get_climate(mode=3)
    growth_rate = np.array([1.5] + [1] * (n_species - 1))

    mosby_mask = (final_mask == 1) & (np.random.rand(*final_mask.shape) < mosby_fraction)
    polygon_contours = measure.find_contours(final_mask, 0.5)

    def build_env():
        try:
            print("🔥 build_env START", flush=True)

            custom_init_obj = CustomStateInitializer2(
                scenario="sequential_restoration",
                grid_size=grid_size,
                mask_array=final_mask
            )
            print("🔥 initializer OK", flush=True)

            print("🔥 BEFORE build_env", flush=True)

            env = BioDivEnv(
                budget=0.5,
                gridInitializer=custom_init_obj,
                length=grid_size,
                n_species=n_species,
                alpha=alpha,
                K_max=cell_capacity,
                dispersal_rate=0.3,
                disturbanceGenerator=disturbance_initializer,
                disturbance_sensitivity=disturbance_sensitivity,
                max_fraction_protected=1,
                immediate_capacity=False,
                truncateToInt=False,
                species_threshold=1,
                K_disturbance_coeff=1,
                climateModel=climate_generator,
                climate_sensitivity=np.zeros(n_species),
                climate_as_disturbance=0,
                iterations=n_years,
                resolution=np.array([5, 5]),
                growth_rate=growth_rate,
                selectivedisturbanceInitializer=0,
                selective_sensitivity=np.zeros(n_species),
                list_species_values=np.ones(n_species)
            )
            print("🔥 BioDivEnv CREATED", flush=True)
            print("🔥 AFTER build_env", flush=True)

            return env

        except Exception as e:
            print("❌ BioDivEnv ERROR:", repr(e), flush=True)
            raise

    def overlay_boundary(ax, contours, color="red"):
        for contour in contours:
            ax.plot(contour[:, 1], contour[:, 0], color=color, linewidth=2)

    def run_and_save(label, apply_mosby):
        print("before build_env", flush=True)
        env = build_env()
        print("after build_env", flush=True)

        np.random.seed(seed)
        print("before env.reset()", flush=True)
        env.reset()
        print("after env.reset()", flush=True)  
        
        K_2d = cell_capacity * final_env
        if apply_mosby:
            K_2d[mosby_mask] *= mosby_factor

        env.bioDivGrid._K = K_2d

        base_dir = os.path.join(output_root, f"{site}_{label}")
        image_dir = os.path.join(base_dir, "images")
        os.makedirs(image_dir, exist_ok=True)

        allowed_categories = ["species richness", "mean population density"] + [f"sp.{i}" for i in range(n_species)]
        for cat in allowed_categories:
            os.makedirs(os.path.join(image_dir, cat.replace(" ", "_")), exist_ok=True)

        if n_years <= 3:
            plot_years = [1, 2, 3]
        else:
            plot_years = [1, 3, 5, 10]

        richness_means = {}
        density_means = {}

        for i in range(n_years):
            year = i + 1
            print(f"🔥 {label} YEAR START: {year}", flush=True)

            env.step()

            print(f"🔥 {label} YEAR AFTER STEP: {year}", flush=True)

            if year in plot_years:
                print(f"🔥 {label} PLOT START: {year}", flush=True)

            if (i + 1) in plot_years:
                year = i + 1
                env.currentIteration = year

                try:
                    plot_env_state(env, wd=base_dir, outfile=f"{site}_{label}", file_format="one_pdf")
                except Exception as e:
                    print("[WARN] plot_env_state skipped:", e)

                figs, titles = _plot_env_state_init(env=env, species_list=list(range(n_species)), plot_titles=True)
                for j, title in enumerate(titles):
                    if j >= len(figs):
                        print(f"[WARN] figs[{j}] missing, skip: {title}")
                        continue

                    fig = figs[j]

                    if not fig.axes:
                        print(f"[WARN] figs[{j}] has no axes, skip: {title}")
                        continue

                    ax = fig.axes[0]

                    # 아래 기존 코드 그대로 유지
                    low_title = title.strip().lower()

                    exclude_keywords = ["total population size", "phylogenetic diversity", "variables through time"]
                    if not any(ex in low_title for ex in exclude_keywords):
                        overlay_boundary(ax, polygon_contours, color="red")

                    target_cat = None
                    if "species richness" in low_title:
                        target_cat = "species_richness"
                    elif "mean population density" in low_title:
                        target_cat = "mean_population_density"
                    else:
                        import re
                        match = re.search(r"\d+", low_title)
                        if match:
                            target_cat = f"sp.{match.group()}"

                    if target_cat:
                        filename = os.path.join(image_dir, target_cat, f"{target_cat}_year_{year}.png")
                        figs[j].savefig(filename)

                    plt.close(figs[j])

                # 연도별 richness/density 평균 수집
                h_snap = env.bioDivGrid.h
                mask_bool_snap = final_mask.astype(bool)
                richness_snap = (h_snap > 1).sum(axis=0)
                richness_means[year] = float(richness_snap[mask_bool_snap].mean())
                density_means[year] = float(h_snap.mean(axis=0)[mask_bool_snap].mean())
    
        h = env.bioDivGrid.h  # (n_species, grid_size, grid_size)
        mask_bool = final_mask.astype(bool)
        mask_cells = int(mask_bool.sum())

        richness_map = (h > 1).sum(axis=0)
        final_richness = float(richness_map[mask_bool].mean())

        density_map = h.mean(axis=0)
        final_density = float(density_map[mask_bool].mean())

        active_cells = int((richness_map[mask_bool] >= 1).sum())
        active_area_pct = float(active_cells / mask_cells * 100) if mask_cells > 0 else 0.0

        del env
        gc.collect()
        return {
            "base_dir": base_dir,
            "final_richness": final_richness,
            "final_density": final_density,
            "restoration_active_area": active_area_pct,
            "richness_means": richness_means,
            "density_means": density_means,
        }

    before_result = run_and_save(label="BEFORE", apply_mosby=False)
    print("🔥 BEFORE RESULT DONE", flush=True)

    after_result = run_and_save(label="AFTER", apply_mosby=True)
    print("🔥 AFTER RESULT DONE", flush=True)
    print("🔥 RUN_SIMULATION RETURN", flush=True)

    return {
        "before_dir": before_result["base_dir"],
        "after_dir": after_result["base_dir"],
        "mosby_mask_md5": hashlib.md5(mosby_mask.tobytes()).hexdigest(),
        "final_richness": after_result["final_richness"],
        "final_density": after_result["final_density"],
        "restoration_active_area": after_result["restoration_active_area"],
        "richness_means": after_result["richness_means"],   # 추가
        "density_means": after_result["density_means"],  
    }