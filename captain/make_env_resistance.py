#%%
import rasterio
import numpy as np
# %%
def load_and_combine_rasters(
    raster_dict,             # { "변수명": "raster파일경로" } 형태의 딕셔너리
    weight_dict=None,        # { "변수명": 가중치 } 형태의 딕셔너리. 없으면 모두 1.0
    minmax_norm=True,        # True 시 min-max 정규화 수행
    fill_value=0.0           # NoData나 NaN을 대체할 값 (기본 0)
):
    """
    여러 개의 단일밴드 래스터를 읽어와서 2D 배열로 변환, 
    (옵션) min-max 정규화 후, 가중치를 곱해 합산하여 최종 환경저항값을 만든다.

    Parameters
    ----------
    raster_dict : dict
        예: {
          'Ca':  "C:/rasters/Ca.tif",
          'CEC': "C:/rasters/CEC.tif",
          'OM' : "C:/rasters/OrganicMatter.tif",
          ...
        }
    weight_dict : dict, optional
        예: {
          'Ca':  0.2,
          'CEC': 0.3,
          'OM' : 0.5,
          ...
        }
        각 변수별 가중치. 지정 안 하면 1.0으로 간주.
    minmax_norm : bool, default=True
        True면 래스터 내 실제 유효값(Non-NaN)에 대해 (X - min)/(max - min) 스케일링.
    fill_value : float, default=0.0
        NoData나 NaN일 때 대체할 값.

    Returns
    -------
    combined_array : 2D numpy array
        모든 변수(래스터)를 가중합한 최종 환경저항 배열.
    arrays_dict    : dict
        { "변수명": 2D array } 형태로, 각 래스터별 원본(혹은 정규화 후) 배열이 들어 있음.
    """

    arrays_dict = {}
    for var_name, r_path in raster_dict.items():
        # 1) 래스터 열기
        with rasterio.open(r_path) as src:
            arr = src.read(1).astype(float)  # 단일밴드 가정
            nodata_val = src.nodata

        # 2) NoData 처리
        # nodata가 있으면 np.nan으로 바꾼 뒤, 나중에 fill_value로 대체
        if nodata_val is not None:
            arr[arr == nodata_val] = np.nan

        # 3) (옵션) min-max 정규화
        if minmax_norm:
            valid_mask = ~np.isnan(arr)
            valid_vals = arr[valid_mask]
            if len(valid_vals) > 0:
                val_min, val_max = valid_vals.min(), valid_vals.max()
                range_ = val_max - val_min
                if range_ > 0:
                    arr[valid_mask] = (valid_vals - val_min) / range_
                else:
                    # 최소값=최대값인 래스터라면 모두 같은 값
                    # 일단 0으로 두거나 1로 둘 수 있음
                    arr[valid_mask] = 1.0
            else:
                # 전부 NaN이면 그냥 넘어감
                pass

        arrays_dict[var_name] = arr

    # 4) 가중합
    #    weight_dict가 없다면 모든 변수에 weight=1.0
    var_list = list(arrays_dict.keys())
    first_var = var_list[0]
    combined_array = np.zeros_like(arrays_dict[first_var], dtype=float)

    for var_name in var_list:
        w = weight_dict[var_name] if (weight_dict and var_name in weight_dict) else 1.0
        arr_ = arrays_dict[var_name]
        # NaN -> fill_value 치환
        arr_ = np.nan_to_num(arr_, nan=fill_value)
        combined_array += (w * arr_)

    # 5) 최종 결과에서 남아있는 NaN(혹시 있다면)도 fill_value로
    combined_array = np.nan_to_num(combined_array, nan=fill_value)

    return combined_array, arrays_dict

# %%
# 예시 실행
if __name__ == "__main__":
    raster_dict = {
       "Ca": r"C:\Users\yjm58\Documents\GitHub\res_sim_cofn\gis_data\Ca_fin.tif",
       "CEC": r"C:\Users\yjm58\Documents\GitHub\res_sim_cofn\gis_data\CEC_fin.tif",
       "OM": r"C:\Users\yjm58\Documents\GitHub\res_sim_cofn\gis_data\Org_fin.tif",
       "Light": r"C:\Users\yjm58\Documents\GitHub\res_sim_cofn\gis_data\Lum_fin.tif",
       "Soil_mo": r"C:\Users\yjm58\Documents\GitHub\res_sim_cofn\gis_data\Soil_mo_fin.tif",
       "Soil_tem": r"C:\Users\yjm58\Documents\GitHub\res_sim_cofn\gis_data\Soil_tem_fin.tif"
    }
    weight_dict = {
       "Ca": 0.2,
       "CEC": 0.2,
       "OM": 0.15,
       "Light": 0.15,
       "Soil_mo": 0.15,
       "Soil_tem": 0.15
    }
    env_resistance, arrays = load_and_combine_rasters(
        raster_dict, weight_dict, minmax_norm=True, fill_value=0.0
    )
    print("env_resistance.shape:", env_resistance.shape)
# %%
raster_path = r"C:\Users\yjm58\Documents\GitHub\res_sim_cofn\gis_data\Soil_tem_fin.tif"
with rasterio.open(raster_path) as src:
    height = src.height
    width = src.width
# %%
print("height:", height)
print("width:", width)
# %%
