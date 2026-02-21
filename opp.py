import streamlit as st
import google.generativeai as genai
import requests
import pandas as pd
import pydeck as pdk
import polyline
import time

# ==========================================
# 1. 页面配置与状态初始化
# ==========================================
st.set_page_config(page_title="AI 智能精准里程规划器", page_icon="🌍", layout="wide")

# 初始化会话状态，防止页面刷新导致数据丢失
if "itinerary_data" not in st.session_state:
    st.session_state.itinerary_data = None
if "map_data" not in st.session_state:
    st.session_state.map_data = None

# ==========================================
# 2. 核心功能函数
# ==========================================
def analyze_intent_with_gemini(prompt, api_key):
    """调用 Gemini 提取用户意图并强制返回结构化数据"""
    genai.configure(api_key=api_key)
    
    # 强制大模型以严格的格式返回数据
    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "description": "打卡点/景点的准确名称，最好包含城市名以防重名"},
                "description": {"type": "STRING", "description": "该地点的游玩特色"},
                "dwell_time_minutes": {"type": "INTEGER", "description": "合理的游玩停留时间（分钟）"}
            },
            "required": ["name", "description", "dwell_time_minutes"]
        }
    }
    
    model = genai.GenerativeModel(
        "gemini-1.5-pro-latest",
        generation_config={"response_mime_type": "application/json", "response_schema": schema}
    )
    
    system_prompt = f"你是一个专业的全球旅行规划师。请分析以下用户的旅行意图，并提取出沿途按逻辑顺序排列的所有打卡点。用户意图：{prompt}"
    response = model.generate_content(system_prompt)
    import json
    return json.loads(response.text)

def get_coordinates(place_name, gmaps_key):
    """调用 Google Geocoding API 获取精准经纬度"""
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={place_name}&key={gmaps_key}"
    res = requests.get(url).json()
    if res['status'] == 'OK':
        loc = res['results']['geometry']['location']
        return loc['lat'], loc['lng']
    return None, None

def get_route_details(lat1, lng1, lat2, lng2, mode, avoid_tolls, avoid_highways, gmaps_key):
    """调用 Google Routes API 获取真实的里程和驾驶时间"""
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": gmaps_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline"
    }
    
    payload = {
        "origin": {"location": {"latLng": {"latitude": lat1, "longitude": lng1}}},
        "destination": {"location": {"latLng": {"latitude": lat2, "longitude": lng2}}},
        "travelMode": mode,
    }
    
    # 避开收费站/高速（仅对驾驶或两轮车有效）
    if mode in:
        payload["routingPreference"] = "TRAFFIC_AWARE_OPTIMAL"
        payload["routeModifiers"] = {"avoidTolls": avoid_tolls, "avoidHighways": avoid_highways}
        
    res = requests.post(url, headers=headers, json=payload).json()
    
    if 'routes' in res and len(res['routes']) > 0:
        route = res['routes']
        dist_m = route.get('distanceMeters', 0)
        dur_s = int(route.get('duration', '0s').replace('s', ''))
        poly = route.get('polyline', {}).get('encodedPolyline', '')
        return dist_m, dur_s, poly
    return 0, 0, ""

# ==========================================
# 3. 前端控制面板 (侧边栏)
# ==========================================
with st.sidebar:
    st.header("⚙️ 统筹约束设置")
    max_drive_hours = st.slider("每天最大在途时间 (小时)", min_value=2, max_value=12, value=6, step=1)
    travel_mode_ui = st.selectbox("交通方式",)
    
    # 映射到 API 识别的参数
    mode_map = {"驾车 (Drive)": "DRIVE", "步行 (Walk)": "WALK", "自行车 (Bicycle)": "BICYCLE", "公共交通 (Transit)": "TRANSIT", "两轮摩托 (Two-Wheeler)": "TWO_WHEELER"}
    travel_mode = mode_map[travel_mode_ui]
    
    avoid_tolls = st.checkbox("避开收费站")
    avoid_highways = st.checkbox("避开高速公路")

# ==========================================
# 4. 主界面与逻辑执行
# ==========================================
st.title("🌍 智能精准里程规划器")
st.markdown("告诉我想去哪里、玩几天、有什么偏好，AI将结合**谷歌地图真实路况**为您切分每日行程！")

with st.form("prompt_form"):
    user_prompt = st.text_area("✍️ 描述您的旅行意图：", placeholder="例如：我想从旧金山出发，沿着一号公路开到洛杉矶，途经优胜美地、大苏尔、丹麦小镇等，总共规划10个打卡点，每天不想太累...")
    submitted = st.form_submit_button("🚀 开始极速规划")

if submitted and user_prompt:
    try:
        # 获取存储在云端的密钥
        gemini_key = st.secrets
        gmaps_key = st.secrets
        
        with st.status("🧠 正在启动 AI 规划引擎...", expanded=True) as status:
            # 步骤 1：大模型推理
            st.write("1️⃣ 正在解析意图并提取结构化打卡点...")
            places = analyze_intent_with_gemini(user_prompt, gemini_key)
            
            # 步骤 2：地理编码
            st.write("2️⃣ 正在通过谷歌地图校验确切地理坐标...")
            valid_places =
            for p in places:
                lat, lng = get_coordinates(p['name'], gmaps_key)
                if lat and lng:
                    p['lat'] = lat
                    p['lng'] = lng
                    valid_places.append(p)
                time.sleep(0.1) # 避免触发频控
                
            # 步骤 3：矩阵与折线计算
            st.write("3️⃣ 正在计算真实物理里程与驾驶时间...")
            for i in range(len(valid_places) - 1):
                p1, p2 = valid_places[i], valid_places[i+1]
                dist, dur, poly = get_route_details(p1['lat'], p1['lng'], p2['lat'], p2['lng'], travel_mode, avoid_tolls, avoid_highways, gmaps_key)
                valid_places[i]['next_dist_km'] = round(dist / 1000, 1)
                valid_places[i]['next_dur_mins'] = round(dur / 60)
                valid_places[i]['polyline'] = poly
            
            # 步骤 4：运筹学每日切分
            st.write("4️⃣ 正在结合您的作息约束，进行每日行程排班...")
            daily_plans =
            current_day =
            current_time = 0
            max_mins_per_day = max_drive_hours * 60
            
            for i, place in enumerate(valid_places):
                transit_time = place.get('next_dur_mins', 0) if i < len(valid_places)-1 else 0
                dwell_time = place.get('dwell_time_minutes', 60)
                
                # 如果当天的时间耗尽，就切割到下一天
                if current_time + transit_time + dwell_time > max_mins_per_day and len(current_day) > 0:
                    daily_plans.append(current_day)
                    current_day = [place]
                    current_time = dwell_time + transit_time
                else:
                    current_day.append(place)
                    current_time += (dwell_time + transit_time)
                    
            if current_day:
                daily_plans.append(current_day)

            # 将结果写入持久化状态机
            st.session_state.itinerary_data = daily_plans
            status.update(label="✅ 规划完成！", state="complete", expanded=False)
            
    except Exception as e:
        st.error(f"规划过程中遇到错误: {e}")
        st.info("提示：请检查左侧边栏是否已正确配置，以及 API 密钥是否在部署时正确粘贴。")

# ==========================================
# 5. 结果渲染 (读取 Session State)
# ==========================================
if st.session_state.itinerary_data:
    st.divider()
    st.subheader("📅 您的专属行程排班")
    
    all_points_for_map =
    all_polylines_for_map =
    
    for day_idx, day_plan in enumerate(st.session_state.itinerary_data):
        with st.expander(f"📍 第 {day_idx + 1} 天 (共 {len(day_plan)} 个打卡点)", expanded=(day_idx==0)):
            for i, stop in enumerate(day_plan):
                all_points_for_map.append({"name": stop['name'], "lat": stop['lat'], "lng": stop['lng']})
                
                st.markdown(f"**{i+1}. {stop['name']}**")
                st.caption(f"📝 {stop['description']} | ⏳ 建议游玩: {stop['dwell_time_minutes']} 分钟")
                
                if 'next_dist_km' in stop and i < len(day_plan) - 1:
                    st.info(f"🚗 前往下一站：真实里程 {stop['next_dist_km']} km，预估用时 {stop['next_dur_mins']} 分钟")
                    if stop.get('polyline'):
                        coords = polyline.decode(stop['polyline'])
                        for c in coords:
                            all_polylines_for_map.append({"lat": c, "lng": c[1]})

    # 渲染动态地图
    if all_points_for_map:
        st.subheader("🗺️ 行程全景地图")
        
        # 绘制路线层
        path_layer = pdk.Layer(
            "PathLayer",
            data=[{"path": [[pt['lng'], pt['lat']] for pt in all_polylines_for_map]}],
            get_path="path",
            get_color=,
            width_scale=20,
            width_min_pixels=3,
        )
        
        # 绘制散点层
        scatter_layer = pdk.Layer(
            "ScatterplotLayer",
            data=all_points_for_map,
            get_position='[lng, lat]',
            get_color='',
            get_radius=8000,
            pickable=True,
        )
        
        view_state = pdk.ViewState(
            latitude=all_points_for_map['lat'], 
            longitude=all_points_for_map['lng'], 
            zoom=5, pitch=0
        )
        
        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/light-v9',
            initial_view_state=view_state,
            layers=[path_layer, scatter_layer],
            tooltip={"text": "{name}"}
        ))
