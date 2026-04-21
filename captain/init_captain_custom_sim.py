#%%
# init_captain_custom_sim.py

import sys
import os
import pickle
import numpy as np

sys.path.append("C:/Users/yjm58/Documents/GitHub/captain-cofn/captain-project")

from captain.biodivsim.CellClass import get_all_to_all_dist_jit, get_coordinates_jit, init_cell_objects
from captain.biodivsim.SimGrid import SimGrid
from captain.biodivsim.CellClass import CellClass
from captain.biodivsim.StateInitializer import StateInitializer
from captain.biodivsim.DisturbanceGenerator import *
from captain.biodivsim.ClimateGenerator import get_climate


class CustomStateInitializer(StateInitializer):
    """
    대상지 마스크(mask_array)가 주어지면, 그 범위(=1) 내부에서만
    초기 종 분포(패치)가 생성되도록 수정한 버전.
    """
    def __init__(self, scenario, grid_size, mask_array=None):
        """
        Parameters
        ----------
        scenario   : str
        grid_size  : int (시뮬레이션 격자 길이)
        mask_array : 2D ndarray or None
            mask_array.shape = (grid_size, grid_size)
            1이면 대상지, 0이면 비대상지. (없으면 None)
        """
        super().__init__()
        self.scenario = scenario
        self.grid_size = grid_size
        self.mask_array = mask_array  # (grid_size, grid_size), 0 or 1

    def getInitialState(self, K, num_species, length):
        """
        'sequential_restoration' 시나리오:
         - moss(종0) 무작위 패치
         - fast_species(1,2,8) 무작위 패치
         - slow_species(3,4,5,6,7) 무작위 패치
        모두 “mask_array=1”인 곳(대상지) 안에서만 생성.

        Parameters
        ----------
        K : int (K_max로부터 온 값이지만, 여기서는 실제 index 접근하지 않음)
        num_species : int
        length : int (== self.grid_size)
        """
        if self.scenario != 'sequential_restoration':
            raise ValueError(f"Unknown scenario: {self.scenario} (expected: sequential_restoration)")

        # 1. 전체 히스토그램 초기화
        #    h.shape = (num_species, length, length)
        h = np.zeros((num_species, length, length), dtype=np.float64)

        # ---------------------------------------------------
        # [A] 대상지 후보 좌표 추출
        #     mask_array가 있다면, 그 중 "1"인 곳만 후보로
        # ---------------------------------------------------
        if self.mask_array is not None:
            # 마스크가 1인 곳의 (x, y) 목록
            all_coords = np.argwhere(self.mask_array == 1)
        else:
            # 마스크가 없으면 전체 그리드가 대상
            all_coords = np.argwhere(np.ones((length, length), dtype=bool))

        num_all_coords = len(all_coords)
        if num_all_coords == 0:
            print("[WARN] mask_array 내 1인 셀이 없습니다. => 초기 종 분포가 전무할 수 있음.")
            return h  # 전부 0인 상태로 반환

        # ---------------------------------------------------
        # [B] MOSS_A (species_id == 0) 무작위 'moss_patches'개
        #     패치 크기=12×12
        # ---------------------------------------------------
        moss_patches = 2
        patch_size = 3

        for _ in range(moss_patches):
            # 대상지 내 임의의 셀 하나 고름
            idx = np.random.randint(num_all_coords)  # 0 ~ num_all_coords-1
            cx, cy = all_coords[idx]                 # (x,y)

            # 패치의 좌상단 모서리를 (cx, cy)에서 patch_size//2만큼 뺀 위치로 가정
            # 혹은 (cx - patch_size//2, cy - patch_size//2)를 중심 기준으로
            # 아래 예시는 "패치 중앙이 (cx, cy)"가 되도록 시도:
            x1 = cx - patch_size//2
            y1 = cy - patch_size//2
            x2 = x1 + patch_size
            y2 = y1 + patch_size

            # 클리핑: 그리드 범위 벗어나지 않도록
            x1 = max(0, x1); y1 = max(0, y1)
            x2 = min(length, x2); y2 = min(length, y2)

            # 패치에 난수 생성 후 임계치 적용
            sub_w = x2 - x1
            sub_h = y2 - y1
            patch_rand = np.random.rand(sub_w, sub_h)
            patch_bin = (patch_rand > 0.4).astype(np.float64)

            # 각 패치에 K/(2*moss_patches) 만큼의 개체수를 할당
            # 여기서 K는 int(예:25) 이므로, K//(2*moss_patches) = int
            # 수치가 너무 작으면(=0) 문제될 수 있으니 적당히 조정
            moss_val = max(1, K // (2 * moss_patches))
            h[0, x1:x2, y1:y2] = patch_bin * moss_val

        # ---------------------------------------------------
        # [C] 방금 만든 Moss_A 분포 마스크(h[0]>0) 중 실제 대상지 부분만
        #     "candidate_coords"로 삼음
        # ---------------------------------------------------
        moss_mask = (h[0] > 0)
        # 대상지 & Moss_A가 둘다 True인 곳만
        if self.mask_array is not None:
            combined_moss = np.argwhere((moss_mask) & (self.mask_array == 1))
        else:
            combined_moss = np.argwhere(moss_mask)
        num_candidates = len(combined_moss)

        # ---------------------------------------------------
        # [D] 빠른 확산(fast) 종들
        # ---------------------------------------------------
        fast_species = [sp for sp in [1, 2, 8] if sp < num_species]
        if num_candidates > 0:
            fast_patch_size = 10
            num_patches_fast = 20
            fast_multiplier = 2.0

            for sp in fast_species:
                for _ in range(num_patches_fast):
                    idx = np.random.randint(num_candidates)
                    cx, cy = combined_moss[idx]

                    x2 = cx + fast_patch_size
                    y2 = cy + fast_patch_size
                    # 클리핑
                    if x2 > length: x2 = length
                    if y2 > length: y2 = length
                    sub_w = x2 - cx
                    sub_h = y2 - cy
                    patch_rand = np.random.rand(sub_w, sub_h)
                    patch_bin = (patch_rand > 0.45).astype(np.float64)
                    h[sp, cx:x2, cy:y2] = patch_bin * fast_multiplier

        # ---------------------------------------------------
        # [E] 느린 확산(slow) 종들 (3,4,5,6,7)
        # ---------------------------------------------------
        slow_species = [sp for sp in range(num_species) if sp not in fast_species and sp != 0]
        # fast 종들+Moss_A(0) 영역 합집합

        union_indices = [0] + fast_species
        union_mask = np.any(h[union_indices], axis=0)
        # 대상지 & union_mask
        if self.mask_array is not None:
            combined_union = np.argwhere(union_mask & (self.mask_array == 1))
        else:
            combined_union = np.argwhere(union_mask)
        num_candidates_slow = len(combined_union)

        if num_candidates_slow > 0:
            slow_patch_size = 6
            num_patches_slow = 7
            slow_multiplier = 1.2
            for sp in slow_species:
                for _ in range(num_patches_slow):
                    idx = np.random.randint(num_candidates_slow)
                    cx, cy = combined_union[idx]
                    x2 = cx + slow_patch_size
                    y2 = cy + slow_patch_size
                    if x2 > length: x2 = length
                    if y2 > length: y2 = length
                    sub_w = x2 - cx
                    sub_h = y2 - cy
                    patch_rand = np.random.rand(sub_w, sub_h)
                    patch_bin = (patch_rand > 0.5).astype(np.float64)
                    h[sp, cx:x2, cy:y2] = patch_bin * slow_multiplier

        return h


def init_custom_simulation(grid_size, cell_capacity, species_traits, out_path, scenario, mask_array=None):
    """
    기존 initGrid 로직 + CustomStateInitializer(마스크 연동).
    """
    n_species = species_traits.shape[0]

    alpha = 0.02
    lambda_0 = 5.0
    disturbance_initializer = InitialConstUniformDisturbanceGenerator(counter=0, magnitude=0.2)
    disturbance_sensitivity = np.ones(n_species)

    # SimGrid 생성
    env = SimGrid(length=grid_size,
                  num_species=n_species,
                  alpha=alpha,
                  K_max=cell_capacity,
                  lambda_0=lambda_0,
                  disturbanceInitializer=disturbance_initializer,
                  disturbance_sensitivity=disturbance_sensitivity,
                  disturbance_dep_dispersal=0)

    # 종 특성
    env._traits = species_traits

    # 기후
    climate_generator, _ = get_climate(mode=3)
    init_climate = np.ones((grid_size, grid_size))
    init_climate = climate_generator.updateClimate(init_climate)
    env._climate_layer = init_climate
    env._climate_generator = climate_generator

    # 보호 매트릭스/교란 매트릭스
    env._protection_matrix = np.zeros((grid_size, grid_size))
    init_matrix = np.zeros((grid_size, grid_size))
    env._disturbance_matrix = disturbance_initializer.updateDisturbance(init_matrix)

    # 커스텀 초기화
    custom_init = CustomStateInitializer(scenario, grid_size, mask_array=mask_array)

    # 그리드 초기화 -> h[species,x,y]
    env.initGrid(custom_init)

    # 디버깅
    print("[DEBUG] after initGrid -> env._h shape:", env._h.shape)
    print("[DEBUG] species count per species:", np.sum(env._h, axis=(1,2)))

    if not os.path.exists(out_path):
        os.makedirs(out_path)

    save_path = os.path.join(out_path, f"{scenario}_init_env.pkl")
    with open(save_path, 'wb') as f:
        pickle.dump(env, f)

    print(f"[✔] {scenario} 초기 환경 저장 완료: {save_path}")
    return save_path
# %%
