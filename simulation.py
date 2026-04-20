# 라이브러리 임포트
import sys
import os
import glob
import rasterio
import numpy as np
import geopandas as gpd
import imageio.v2 as imageio
import matplotlib.pyplot as plt
from skimage import measure
from shapely.geometry import Polygon, Point
from rasterio import features
from rasterio.transform import from_bounds

from captain.init_captain_custom_sim import CustomStateInitializer 
from captain.biodivsim.SimGrid import SimGrid 
from captain.biodivsim.BioDivEnv import BioDivEnv 
from captain.biodivsim.DisturbanceGenerator import InitialConstUniformDisturbanceGenerator
from captain.biodivsim.ClimateGenerator import get_climate
from captain.plot.plot_env import plot_env_state, plot_biodiv_env
from captain.plot.plot_env import _plot_env_state_init

sys.path.append(r"C:\Users\LG\Downloads\captain-project") 


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

        # 특정 종(Moss_A) 패치를 지역 마스크 안에서만 뿌리기
        moss_patches = 3
        patch_size = 12
        for _ in range(moss_patches):
            if len(self.mask_coords) > 0:
                idx = np.random.choice(len(self.mask_coords))
                cx, cy = self.mask_coords[idx]
                half = patch_size // 2
                x0 = max(cx - half, 0);   x1 = min(cx + half, length)
                y0 = max(cy - half, 0);   y1 = min(cy + half, length)
                patch = (np.random.rand(x1-x0, y1-y0) > 0.4).astype(np.float64)
                h[0, x0:x1, y0:y1] = patch * (K // (2 * moss_patches))

        # 마스크 밖이라면 모든 종의 개체수를 0으로
        mask_bool = self.mask_array.astype(bool)
        for sp in range(num_species):
            h[sp, ~mask_bool] = 0.0

        return h

#------------------------------------------------------------------------------
# main 실행부
#------------------------------------------------------------------------------
if __name__ == "__main__":

    #====================== 환경 및 경계 데이터 =======================
    shp_path = r"C:\Users\LG\Downloads\captain-project\gis_data\한일시멘트\한일시멘트.shp"
    tif_dir = r"C:\Users\LG\Downloads\captain-project\gis_data\한일시멘트"
    
    # 영풍 SHP
    gdf = gpd.read_file(shp_path)
    grid_size = 100 
    bounds = gdf.total_bounds 
    transform = from_bounds(*bounds, grid_size, grid_size)

    # TIF 데이터 통합
    tif_files = ["Ca_fin.tif", "OM_fin.tif", "pH_fin.tif", "CEC_fin.tif", 
                "Org_fin.tif", "Soil_mo_fin.tif", "Soil_tem_fin.tif", "Lum_fin.tif"]
    
    env_accumulation = np.zeros((grid_size, grid_size))
    
    for tif_name in tif_files:
        full_path = os.path.join(tif_dir, tif_name)
        if os.path.exists(full_path):
            with rasterio.open(full_path) as src:
                # 100x100 해상도로 리샘플링하여 읽기
                data = src.read(1, out_shape=(grid_size, grid_size))
                env_accumulation += data
        else:
            print(f"[경고] 파일을 찾을 수 없습니다: {full_path}")

    # 영풍 SHP 영역 마스크 생성
    mask_arr_polygon = features.rasterize(
        [(shape, 1) for shape in gdf.geometry],
        out_shape=(grid_size, grid_size),
        transform=transform
    ).astype(int)

    # 환경 저항 및 정규화
    env_resistance = np.where(mask_arr_polygon == 1, env_accumulation, 0.0)
    
    if env_resistance.max() > 0:
        final_env = env_resistance / env_resistance.max()
    else:
        final_env = env_resistance

    final_mask = mask_arr_polygon
    print(f"지형 마스크 생성 완료. 활성 면적: {final_mask.sum()}")

    #====================== 시뮬레이션 파라미터 ======================
    n_years = 20
    n_species = 9
    cell_capacity = 25
    alpha = 0.09
    
    species_traits = np.array([
        [1.5, 1.0],  # Moss_A
        [1.5, 1.0],  # Microbial_B
        [1.3, 1.0],  # Detritivore_C
        [0.6, 0.5],  # Tree_D
        [1.0, 0.9],  # Shrub_E
        [1.3, 1.0],  # Herb_F
        [0.4, 1.5],  # Bird_G
        [0.9, 0.7],  # Rodent_H
        [0.8, 1.4],  # Insect_I
    ])

    disturbance_initializer = InitialConstUniformDisturbanceGenerator(counter=0, magnitude=0.2)
    disturbance_sensitivity = np.ones(n_species)
    climate_generator, _ = get_climate(mode=3)
    growth_rate = np.array([1.5] + [1]*(n_species-1))

    custom_init_obj = CustomStateInitializer2(
        scenario="sequential_restoration",
        grid_size=grid_size,
        mask_array=final_mask
    )

    env = BioDivEnv(
        budget=0.5, gridInitializer=custom_init_obj, length=grid_size, n_species=n_species,
        alpha=alpha, K_max=cell_capacity, dispersal_rate=0.3,
        disturbanceGenerator=disturbance_initializer, disturbance_sensitivity=disturbance_sensitivity,
        max_fraction_protected=1, immediate_capacity=False, truncateToInt=False,
        species_threshold=1, K_disturbance_coeff=1, climateModel=climate_generator,
        climate_sensitivity=np.zeros(n_species), climate_as_disturbance=0, iterations=n_years,
        resolution=np.array([5, 5]), growth_rate=growth_rate, selectivedisturbanceInitializer=0,
        selective_sensitivity=np.zeros(n_species), list_species_values=np.ones(n_species)
    )

    #====================== 시뮬레이션 초기화 및 K값 반영 ======================
    env.reset()
    K_2d = cell_capacity * final_env
    env.bioDivGrid._K = K_2d
    print("환경 수치 반영 완료.")

    # 윤곽선 추출 및 결과 폴더 생성
    polygon_contours = measure.find_contours(final_mask, 0.5)
    base_dir = './hanil'
    os.makedirs(base_dir, exist_ok=True)
    image_dir = './hanil/images'
    os.makedirs(image_dir, exist_ok=True)

    allowed_categories = ['species richness', 'mean population density'] + [f"sp.{i}" for i in range(n_species)]
    for cat in allowed_categories:
        os.makedirs(os.path.join(image_dir, cat.replace(' ', '_')), exist_ok=True)

    def overlay_boundary(ax, contours, color='red'):
        for contour in contours:
            ax.plot(contour[:,1], contour[:,0], color=color, linewidth=2)

    #====================== 실행 및 시각화 ======================
    plot_years = [1, 5, 10, 15, 20]

    for i in range(n_years):
        env.step()
        print(f"[INFO] Step {i+1} executed.")

        if (i + 1) in plot_years:
            env.currentIteration = i + 1
            # PDF 저장
            plot_env_state(env, wd='./hanil', outfile=f"hanil", file_format="one_pdf")
            
            # figs, titles = plot_biodiv_env(loaded_env=env, plot_titles=True)
            figs, titles = _plot_env_state_init(env=env,species_list=list(range(n_species)), plot_titles=True)
            for j, title in enumerate(titles):
                ax = figs[j].axes[0]
                low_title = title.strip().lower()

                # 제외할 항목
                exclude_keywords = ["total population size", "phylogenetic diversity", "variables through time"]

                # 테두리 그리기
                if not any(ex in low_title for ex in exclude_keywords):
                    overlay_boundary(ax, polygon_contours, color='red')

                target_cat = None

                if "species richness" in low_title:
                    target_cat = "species_richness"

                elif "mean population density" in low_title:
                    target_cat = "mean_population_density"

                else:
                    import re
                    match = re.search(r'\d+', low_title)
                    if match:
                        sp_num = match.group()
                        target_cat = f"sp.{sp_num}"

                # 저장
                if target_cat:
                    folder_path = os.path.join(image_dir, target_cat)
                    os.makedirs(folder_path, exist_ok=True)

                    filename = os.path.join(folder_path, f"{target_cat}_year_{i+1}.png")
                    figs[j].savefig(filename)

                plt.close(figs[j])

    print("\n 시뮬레이션 완료!")

    # # 영상 제작
    # video_categories = ['species richness', 'mean population density']

    # for cat in video_categories:
    #     cat_path = cat.replace(' ', '_')
    #     image_files = sorted(glob.glob(os.path.join(image_dir, cat_path, f"*year_*.png")))
    #     if image_files:
    #         video_output = os.path.join(image_dir, f"{cat_path}.mp4")
    #         writer = imageio.get_writer(video_output, fps=1)
    #         for fname in image_files:
    #             writer.append_data(imageio.imread(fname))
    #         writer.close()