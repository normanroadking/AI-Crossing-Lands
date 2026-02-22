import streamlit as st
import json
import requests
import pandas as pd
import pydeck as pdk
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import time

# ==========================================
# 1. 定义大模型的强制输出结构 (Pydantic Schema)
# ==========================================
class POI(BaseModel):
    name: str = Field(description="景点的准确名称，需包含城市名以防重名")
    description: str = Field(description="该地点的游玩特色")
    dwell_time_minutes: int = Field(description="合理的游玩停留时间（分钟）")
    is_night_poi: bool = Field(description="如果该地点强烈建议在晚上游玩（如夜市、酒吧、夜景），设为 true")
    assigned_day: int = Field(description="该景点被初步分配在第几天（从1开始）")

class TripExtraction(BaseModel):
    pois: list[POI]

# ==========================================
# 2. 页面配置与状态初始化 (防御性状态机)
# ==========================================
st.set_page_config(page_title="SaaS 级智能路线运筹大脑", page_icon="🌍", layout="wide")

if "final_itinerary" not in st.session_state:
    st.session_state.final_itinerary = None
if "raw_pois" not in st.session_state:
    st.session_state.raw_pois = None

# ==========================================
# 3. 核心功能函数
# ==========================================
def extract_pois(prompt, api_key):
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model='gemini-2.5-pro',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TripExtraction,
            temperature=0.2 
        ),
    )
    return json.loads(response.text)['pois']

def geocode_place(place_name, gmaps_key):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={place_name}&key={gmaps_key}"
    res = requests.get(url).json()
    if res['status'] == 'OK':
        loc = res['results']['geometry']['location']
        return loc['lat'], loc['lng']
    return None, None

def get_daily_route_matrix(locations, gmaps_key):
    url = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    waypoints = [{"waypoint": {"location": {"latLng": {"latitude": loc['lat'], "longitude": loc['lng']}}}} for loc in locations]
    
    payload = {
        "origins": waypoints,
        "destinations": waypoints,
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL"
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": gmaps_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters"
    }
    
    response = requests.post(url, headers=headers, json=payload).json()
    size = len(locations)
    time_matrix = [ * size for _ in range(size)]
    
    for element in response:
        o_idx = element.get('originIndex', 0)
        d_idx = element.get('destinationIndex', 0)
        duration_sec = int(element.get('duration', '0s').replace('s', ''))
        time_matrix[o_idx][d_idx] = duration_sec
        
    return time_matrix

def optimize_schedule(time_matrix, pois, max_drive_seconds=28800):
    manager = pywrapcp.RoutingIndexManager(len(time_matrix), 1, 0) 
    routing = pywrapcp.RoutingModel(manager)

    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        drive_time = time_matrix[from_node][to_node]
        dwell_time = pois[from_node].get('dwell_time_minutes', 0) * 60 if from_node!= 0 else 0
        return drive_time + dwell_time

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    routing.AddDimension(transit_callback_index, 3600, max_drive_seconds, False, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")

    for node_idx, poi in enumerate(pois):
        if node_idx == 0: continue
        index = manager.NodeToIndex(node_idx)
        if poi.get('is_night_poi', False):
            # 强制夜游点在 10 小时后访问
            time_dimension.CumulVar(index).SetMin(10 * 3600)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    
    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        ordered_route =
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            time_var = time_dimension.CumulVar(index)
            arrival_time_sec = solution.Min(time_var)
            
            poi_data = pois[node_index].copy()
            poi_data['arrival_offset_hrs'] = round(arrival_time_sec / 3600, 2)
            ordered_route.append(poi_data)
            
            index = solution.Value(routing.NextVar(index))
        return ordered_route
    return None

# ==========================================
# 4. 前端 UI 与侧边栏交互
# ==========================================
with st.sidebar:
    st.header("🔑 平台接入设置 (BYOK)")
    st.info("作为 SaaS 平台，用户需提供自己的 API 密钥以核算成本。您的密钥仅在本次会话中可用，不会被保存。")
    gemini_key = st.text_input("Gemini API Key", type="password")
    gmaps_key = st.text_input("Google Maps API Key", type="password")
    
    st.header("⚙️ 运筹约束设置")
    max_drive_hours = st.slider("每日最大驾驶+游玩总时长 (小时)", 4, 16, 10)
    
st.title("🌍 智能精准里程规划器 (专业运筹版)")

with st.form("planner_form"):
    user_prompt = st.text_area("✍️ 请输入大致的旅行意图：", placeholder="例如：我想去日本东京和京都玩5天，喜欢历史和夜市，别太累...")
    submitted = st.form_submit_button("🚀 启动运筹引擎计算")

if submitted:
    if not gemini_key or not gmaps_key:
        st.error("请先在左侧边栏输入您的 API 密钥！")
    elif not user_prompt:
        st.warning("请输入旅行意图。")
    else:
        st.session_state.final_itinerary = {} # 重置数据
        
        with st.status("🧠 正在启动 AI 运筹大脑...", expanded=True) as status:
            try:
                st.write("1️⃣ [常识模型] 正在分配结构化节点池...")
                raw_pois = extract_pois(user_prompt, gemini_key)
                
                # 按天分组
                days_dict = {}
                for p in raw_pois:
                    d = p['assigned_day']
                    if d not in days_dict: days_dict[d] =
                    days_dict[d].append(p)
                
                st.write("2️⃣ [物理与运筹引擎] 正在按天进行硬约束排班...")
                for day, day_pois in days_dict.items():
                    # 确保起点存在（这里简化处理，将第一个点作为当日酒店/起点）
                    valid_day_pois =
                    for p in day_pois:
                        lat, lng = geocode_place(p['name'], gmaps_key)
                        if lat and lng:
                            p['lat'], p['lng'] = lat, lng
                            valid_day_pois.append(p)
                    
                    if len(valid_day_pois) > 1:
                        time_mat = get_daily_route_matrix(valid_day_pois, gmaps_key)
                        optimized_route = optimize_schedule(time_mat, valid_day_pois, max_drive_hours * 3600)
                        st.session_state.final_itinerary[day] = optimized_route or valid_day_pois # 如果求解失败则使用原序列
                    else:
                        st.session_state.final_itinerary[day] = valid_day_pois
                
                status.update(label="✅ 所有节点计算与排班完成！", state="complete", expanded=False)
                
            except Exception as e:
                status.update(label="❌ 计算中发生错误", state="error")
                st.error(f"错误详情: {str(e)}")

# ==========================================
# 5. 结果渲染 (持久化展示)
# ==========================================
if st.session_state.final_itinerary:
    st.success("🎉 行程排班表生成成功！(任意切换页面或调整参数，下方数据都不会丢失)")
    
    for day, route in sorted(st.session_state.final_itinerary.items()):
        with st.expander(f"📍 第 {day} 天行程 (系统建议游玩顺序)", expanded=True):
            for idx, stop in enumerate(route):
                # 提取运筹学计算出的时间偏移量
                arrival_hr = stop.get('arrival_offset_hrs', 0)
                is_night = "🌙 强制夜间" if stop.get('is_night_poi') else "☀️ 日间推荐"
                
                st.markdown(f"**第 {idx+1} 站: {stop['name']}**  `{is_night}`")
                st.caption(f"📝 {stop['description']} | ⏳ 预计游玩: {stop['dwell_time_minutes']} 分钟 | 🚗 出发后第 {arrival_hr} 小时抵达")
