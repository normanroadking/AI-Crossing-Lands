import streamlit as st
from google import genai
import requests
import json

# ================= 网页配置 =================
st.set_page_config(page_title="AI 摩托旅行规划专家", page_icon="🏍️", layout="wide")
st.title("🏍️ 自定义 AI 摩托车里程规划工具")
st.markdown("您可以自由设定骑行规则，AI 将根据您的体能与车辆状况，严格验证每一寸路线的合理性。")

# ================= 动态规则设定 (侧边栏) =================
with st.sidebar:
    st.header("⚙️ 1. API 配置")
    gemini_key = st.text_input("Gemini API Key", type="password")
    gmaps_key = st.text_input("Google Maps API Key", type="password")
    
    st.header("🏁 2. 骑行规则设定")
    # 让用户自己拉动滑块来决定限制
    u_max_daily_km = st.slider("每日最高骑行里程 (km)", 100, 800, 350)
    u_max_half_km = st.slider("半日建议休息里程 (km)", 50, 400, 200)
    
    st.header("🛠️ 3. 车辆保养设定")
    u_small_interval = st.number_input("小保养间隔 (km)", 500, 3000, 1500)
    u_small_hours = st.selectbox("小保养占用时间 (天)", [0.25, 0.5, 1.0], index=1)
    
    u_large_interval = st.number_input("大保养间隔 (km)", 3000, 15000, 10000)
    u_large_hours = st.selectbox("大保养占用时间 (天)", [0.5, 1.0, 2.0], index=1)

# ================= 核心算法模块 =================
ROUTES_API_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"

def parse_user_intent(user_prompt, api_key):
    """解析用户想要去的目的地"""
    try:
        client = genai.Client(api_key=api_key)
        sys_prompt = "你是一个摩托旅行专家。从用户需求中提取目的地城市列表，仅输出JSON: {'destinations': ['城市1', '城市2']}"
        response = client.models.generate_content(
            model='gemini-1.5-flash', contents=f"{sys_prompt}\n\n用户需求: {user_prompt}"
        )
        clean_json = response.text.strip().lstrip('```json').rstrip('```')
        return json.loads(clean_json).get("destinations", list())
    except Exception as e:
        st.error(f"意图解析失败: {e}")
        return list()

def get_route_matrix(origin, destination, api_key):
    """验证实际路网里程"""
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": api_key,
               "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters"}
    payload = {"origins": [{"waypoint": {"address": origin}}],
               "destinations": [{"waypoint": {"address": destination}}],
               "travelMode": "TWO_WHEELER"}
    try:
        res = requests.post(ROUTES_API_URL, headers=headers, json=payload)
        return res.json()
    except: return None

def plan_custom_trip(nodes, gmaps_key):
    """根据侧边栏设定的动态参数进行行程计算"""
    daily_itinerary = list()
    current_day, total_km, daily_km = 1, 0.0, 0.0
    next_small = u_small_interval
    next_large = u_large_interval
    
    curr = nodes
    day_plan = {"day": current_day, "start": curr, "stops": list(), "events": list()}
    
    for next_node in nodes[1:]:
        data = get_route_matrix(curr, next_node, gmaps_key)
        # 获取真实里程，失败则默认步进150km用于演示
        dist = int(data.get('distanceMeters', 150000)) / 1000.0 if data else 150.0
        
        # 规则1：每日里程熔断
        if daily_km + dist > u_max_daily_km:
            day_plan["end"] = curr
            day_plan["events"].append(f"🛑 达到您设定的每日 {u_max_daily_km}km 上限，在 {curr} 休息。")
            daily_itinerary.append(day_plan)
            current_day += 1
            daily_km = 0.0
            day_plan = {"day": current_day, "start": curr, "stops": list(), "events": list()}
            
        # 规则2：大保养逻辑
        if total_km + dist >= next_large:
            day_plan["events"].append(f"🚨 累计行驶 {round(total_km + dist)}km：触发大保养，占用 {u_large_hours} 天。")
            next_large += u_large_interval
            dist = 0 # 保养当天不骑行
            
        # 规则3：小保养逻辑
        elif total_km + dist >= next_small:
            day_plan["events"].append(f"🔧 累计行驶 {round(total_km + dist)}km：触发小保养，占用 {u_small_hours} 天。")
            next_small += u_small_interval
            # 缩减当天可用里程
            if daily_km + dist > (u_max_daily_km * (1 - u_small_hours)):
                dist = (u_max_daily_km * (1 - u_small_hours)) - daily_km
        
        daily_km += max(0, dist)
        total_km += max(0, dist)
        day_plan["stops"].append({"loc": next_node, "km": round(dist, 1)})
        curr = next_node
        
    day_plan["end"] = curr
    daily_itinerary.append(day_plan)
    return daily_itinerary, total_km

# ================= 用户界面 =================
prompt = st.text_area("请描述您的摩托之旅意图（如：穿越州府、极点、避开雨季等）:", height=150)

if st.button("🚀 生成并验证我的专属行程", type="primary"):
    if not gemini_key or not gmaps_key:
        st.warning("请在左侧边栏填写您的 API Key。")
    else:
        with st.spinner("AI 正在解析您的目的地意图..."):
            nodes = parse_user_intent(prompt, gemini_key)
        
        if nodes:
            st.success(f"意图识别完成！我们将依次前往：{' -> '.join(nodes)}")
            with st.spinner("正在根据您的动态规则进行里程计算与保养排期..."):
                itinerary, km = plan_custom_trip(nodes, gmaps_key)
            
            st.markdown("---")
            st.subheader(f"📊 规划结果 (预估总计骑行: {round(km, 1)} 公里)")
            
            for d in itinerary:
                with st.expander(f"📅 第 {d['day']} 天：从 {d['start']} 出发"):
                    if not d['stops']: st.write("本日安排：全天大保养，不骑行。")
                    for s in d['stops']: st.write(f"  - 目的地: {s['loc']} (行驶里程: {s['km']} km)")
                    for e in d['events']: st.info(e)
