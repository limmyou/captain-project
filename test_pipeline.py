from app.services.geocode_service import geocode
from app.services.admin_service import get_admin_info
from app.services.soil_service import get_soil_data

address = "전라남도 여수시 돌산읍"

lat, lon = geocode(address)
print("좌표:", lat, lon)

admin_info = get_admin_info(lat, lon)
print("행정정보:", admin_info["emd_cd"], admin_info["stdg_cd"], admin_info["emd_nm"])

soil_data = get_soil_data(admin_info["stdg_cd"])
print("토양데이터:", soil_data)