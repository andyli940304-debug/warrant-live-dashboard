# Mark 66 - Railway 專用修正版 (🛡️ 修復 Secrets 報錯)
# ✅ 功能：優先讀取 Railway 環境變數，避免 st.secrets 崩潰
# ✅ 包含：自動復活、手機版格式、認售修復

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import requests
import streamlit.components.v1 as components 
import time 
import os 
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager 
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException

# ==========================================
# 0. 安全讀取設定 (🔥 核心修復：先讀環境變數)
# ==========================================
def get_config(key):
    """
    聰明讀取設定：
    1. 先看 Railway 環境變數 (os.environ)
    2. 如果沒有，再小心地試探 Streamlit Secrets
    """
    # 1. 優先檢查環境變數 (Railway 模式)
    # 這樣程式就不會因為找不到 secrets.toml 而崩潰
    if key in os.environ:
        return os.environ[key]
    
    # 2. 嘗試讀取 st.secrets (本機/Streamlit Cloud 模式)
    try:
        if key in st.secrets:
            return st.secrets[key]
    except:
        # 如果 st.secrets 檔案不存在，安靜地忽略，不要報錯
        pass
        
    return None

# ==========================================
# 1. 雲端資料庫設定 & 連線功能
# ==========================================

SHEET_NAME_DB = '會員系統資料庫'   
SHEET_NAME_LIVE = 'live_data'     
OPAY_URL = "https://p.opay.tw/qzA4j"

# @st.cache_resource
def get_gcp_client():
    """取得 GCP 連線客戶端"""
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    
    # 🔥 改用 get_config 安全讀取
    key_data = get_config("gcp_key")
        
    if not key_data:
        st.error("❌ 找不到 GCP Key！請檢查 Railway 變數設定。")
        return None

    # 處理 JSON 格式
    if isinstance(key_data, str):
        try:
            key_dict = json.loads(key_data)
        except json.JSONDecodeError:
            st.error("❌ GCP Key 格式錯誤，無法解析 JSON")
            return None
    else:
        key_dict = key_data
        
    creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    client = gspread.authorize(creds)
    return client

def get_db_connection():
    client = get_gcp_client()
    return client.open(SHEET_NAME_DB) if client else None

def upload_image_to_imgbb(image_file):
    if not image_file: return ""
    try:
        # 🔥 改用 get_config 安全讀取
        api_key = get_config("imgbb_key")
        if not api_key: return ""
            
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": api_key}
        files = {"image": image_file.getvalue()}
        response = requests.post(url, data=payload, files=files)
        if response.status_code == 200:
            return response.json()['data']['url']
        else:
            return ""
    except:
        return ""

# ==========================================
# 2. 核心功能函數 (已加入快取防護)
# ==========================================

def get_data_as_df(worksheet_name):
    try:
        sh = get_db_connection()
        ws = sh.worksheet(worksheet_name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

# 🔥 快取機制 (TTL = 20秒)：防止 API 額度爆炸
@st.cache_data(ttl=20)
def get_live_warrant_data():
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        
        # 🔥 改用 get_config 安全讀取
        key_data = get_config("gcp_key")
        if not key_data: return pd.DataFrame()

        if isinstance(key_data, str):
            key_dict = json.loads(key_data)
        else:
            key_dict = key_data 
            
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
        client = gspread.authorize(creds)
        
        sh = client.open('live_data') 
        ws = sh.sheet1 
        data = ws.get_all_values() 
        
        if len(data) > 1:
            headers = data[0]
            rows = data[1:]
            df = pd.DataFrame(rows, columns=headers)
            return df
            
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def check_login(username, password):
    # 🔥 改用 get_config 安全讀取 (修復這裡的報錯)
    admin_user = get_config("admin_username")
    admin_pwd = get_config("admin_password")

    if admin_user and admin_pwd:
        if str(username) == str(admin_user) and str(password) == str(admin_pwd):
            return True
            
    df = get_data_as_df('users')
    if df.empty: return False
    user_row = df[df['username'].astype(str) == str(username)]
    if not user_row.empty:
        if str(user_row.iloc[0]['password']) == str(password):
            return True
    return False

def register_user(username, password):
    df = get_data_as_df('users')
    if not df.empty and str(username) in df['username'].astype(str).values:
        return False, "帳號已存在"
    try:
        sh = get_db_connection()
        ws = sh.worksheet('users')
        tw_now = datetime.now() + timedelta(hours=8)
        yesterday = (tw_now - timedelta(days=1)).strftime("%Y-%m-%d")
        ws.append_row([str(username), str(password), yesterday])
        return True, "註冊成功！請切換到「登入」分頁進入。"
    except Exception as e:
        return False, f"連線錯誤: {e}"

def check_subscription(username):
    # 🔥 改用 get_config 安全讀取
    admin_user = get_config("admin_username")

    if admin_user:
        if str(username) == str(admin_user): 
            return True, "永久會員 (管理員)"
    
    df = get_data_as_df('users')
    if df.empty: return False, "資料庫讀取失敗"
    user_row = df[df['username'].astype(str) == str(username)]
    if not user_row.empty:
        expiry_str = str(user_row.iloc[0]['expiry'])
        try:
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            tw_today = (datetime.now() + timedelta(hours=8)).date()
            if expiry_date >= tw_today: return True, expiry_str
            else: return False, expiry_str
        except: return False, "日期格式異常"
    return False, "無此帳號"

def add_days_to_user(username, days=30):
    try:
        sh = get_db_connection()
        ws = sh.worksheet('users')
        cell = ws.find(str(username))
        if not cell: return False
        row_num = cell.row
        current_expiry_str = ws.cell(row_num, 3).value
        tw_today = (datetime.now() + timedelta(hours=8)).date()
        try: current_expiry = datetime.strptime(current_expiry_str, "%Y-%m-%d").date()
        except: current_expiry = tw_today
        start_date = max(current_expiry, tw_today)
        new_expiry = start_date + timedelta(days=days)
        ws.update_cell(row_num, 3, new_expiry.strftime("%Y-%m-%d"))
        return True
    except: return False

def add_new_post(title, content, img_url=""):
    try:
        sh = get_db_connection()
        ws = sh.worksheet('posts')
        tw_time = datetime.now() + timedelta(hours=8)
        ws.append_row([tw_time.strftime("%Y-%m-%d %H:%M"), title, content, img_url])
        return True
    except: return False

# 🔥 自動刷新區塊 (每30秒)
@st.fragment(run_every=30)
def show_live_table():
    st.subheader("🔥 盤中權證熱門榜")
    
    col_r1, col_r2 = st.columns([6, 1])
    with col_r2:
        if st.button("🔄 立即刷新"):
            st.rerun()

    df_live = get_live_warrant_data()
    
    if not df_live.empty:
        # 1. 顯示當下時間
        current_tw_time = (datetime.utcnow() + timedelta(hours=8)).strftime("%H:%M:%S")
        st.caption(f"🕒 最後更新時間：{current_tw_time}")

        # 2. 手機版優化
        df_live['標的'] = df_live['名稱'] + " (" + df_live['代號'] + ")"
        
        display_cols = ['標的', '漲跌', '成交值', '倍數', '量/流', '槓桿']
        df_display = df_live[display_cols]

        st.markdown("""
            <style>
            [data-testid="stDataFrame"] th { font-size: 14px !important; pointer-events: none; } 
            [data-testid="stDataFrame"] td { font-size: 14px !important; cursor: default; }
            </style>
        """, unsafe_allow_html=True)

        st.dataframe(
            df_display, 
            use_container_width=True,
            hide_index=True,
            height=800,  
            column_config={
                "標的": st.column_config.TextColumn("標的", width="medium"),
                "漲跌": st.column_config.TextColumn("漲跌", width="small"),
                "成交值": st.column_config.TextColumn("金額", width="small"),
                "倍數": st.column_config.ProgressColumn("倍數", format="%s", min_value=0, max_value=100),
                "量/流": st.column_config.TextColumn("量/流", width="medium"),
            }
        )
    else:
        st.warning("⚠️ 目前無即時資料，或機器人尚未啟動。")


# ==========================================
# 3. 網站介面
# ==========================================
st.set_page_config(page_title="權證主力戰情室", layout="wide", page_icon="📈")

st.markdown("""
    <style>
        [data-testid="stToolbar"] {visibility: hidden; display: none;}
        [data-testid="stDecoration"] {visibility: hidden; display: none;}
        footer {visibility: hidden; display: none;}
        th {
            background-color: #f0f2f6;
            text-align: center !important;
            font-size: 14px !important;
            padding: 8px !important;
        }
        td {
            text-align: center !important;
            vertical-align: middle !important;
            font-size: 14px !important;
            padding: 8px !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- 尚未登入區 ---
if 'logged_in_user' not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>🚀 權證主力戰情室</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>每日盤後籌碼分析 | 盤中即時熱門權證</p>", unsafe_allow_html=True)
    
    st.error("⚠️ **法律免責聲明**：本網站數據僅供學術研究參考，**絕不構成任何投資建議**。使用者應自行承擔所有投資風險，盈虧自負。")
    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info("🔒 請先登入或註冊以繼續")
        tab_login, tab_register = st.tabs(["🔑 會員登入", "📝 免費註冊"])
        with tab_login:
            st.write("")
            user_input = st.text_input("帳號", key="login_user")
            pwd_input = st.text_input("密碼", type="password", key="login_pwd")
            if st.button("登入系統", key="btn_login", use_container_width=True):
                if check_login(user_input, pwd_input):
                    st.session_state['logged_in_user'] = user_input
                    st.rerun()
                else:
                    st.error("帳號或密碼錯誤！")
        with tab_register:
            st.write("")
            new_user = st.text_input("設定帳號", key="reg_user")
            new_pwd = st.text_input("設定密碼", type="password", key="reg_pwd")
            new_pwd_confirm = st.text_input("確認密碼", type="password", key="reg_pwd2")
            if st.button("提交註冊", key="btn_reg", use_container_width=True):
                if new_pwd != new_pwd_confirm:
                    st.error("兩次密碼輸入不一致")
                elif not new_user or not new_pwd:
                    st.error("帳號密碼不能為空")
                else:
                    success, msg = register_user(new_user, new_pwd)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
    st.write("")
    c1, c2 = st.columns(2)
    with c1: st.success("📊 **即時權證監控**\n\n盤中即時監控，捕捉主力動向。")
    with c2: st.warning("🤖 **深度籌碼日報**\n\n盤後完整分析，拆解大戶手法。")

# --- 已登入區 ---
else:
    user = st.session_state['logged_in_user']
    is_vip, expiry = check_subscription(user)
    
    # 頂部導覽列
    top_col1, top_col2 = st.columns([4, 1])
    with top_col1:
        st.title("🚀 權證主力戰情室")
        st.write(f"👋 歡迎回來，**{user}**")
        if is_vip: st.caption(f"✅ 會員效期至：{expiry}")
        else: st.caption(f"⛔ 會員已過期 ({expiry})")
    with top_col2:
        st.write("")
        if st.button("登出系統", use_container_width=True):
            del st.session_state['logged_in_user']
            st.rerun()
            
    st.warning("⚠️ **免責聲明**：本網站內容僅為資訊整理，**不構成投資建議**。盈虧自負。")
    st.divider()

    # --- 管理員後台 ---
    is_admin = False
    # 🔥 改用 get_config 安全讀取
    admin_user = get_config("admin_username")
    if admin_user:
        if str(user) == str(admin_user): is_admin = True
        
    if is_admin:
        with st.expander("🔧 管理員後台 (點擊展開)", expanded=False):
            tab1, tab2 = st.tabs(["發布文章", "會員管理"])
            with tab1:
                with st.form("post_form"):
                    st.write("### 發布新戰情")
                    new_title = st.text_input("文章標題")
                    new_content = st.text_area("內容 (支援 HTML)", height=300)
                    uploaded_files = st.file_uploader("上傳圖片 (選填)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
                    submitted = st.form_submit_button("發布文章")
                    if submitted:
                        final_img_str = ""
                        if uploaded_files:
                            img_urls = []
                            for f in uploaded_files:
                                url = upload_image_to_imgbb(f)
                                if url: img_urls.append(url)
                            final_img_str = ",".join(img_urls)
                        if add_new_post(new_title, new_content, final_img_str):
                            st.success(f"發布成功！")
            
            with tab2:
                target_user = st.text_input("輸入會員帳號")
                st.write("👇 快速加值：")
                b1, b2, b3, b4 = st.columns(4)
                
                with b1:
                    if st.button("+10 天", use_container_width=True):
                        if add_days_to_user(target_user, 10): st.success("成功 +10 天")
                        else: st.error("失敗")
                with b2:
                    if st.button("+30 天", use_container_width=True):
                        if add_days_to_user(target_user, 30): st.success("成功 +30 天")
                        else: st.error("失敗")
                with b3:
                    if st.button("+60 天", use_container_width=True):
                        if add_days_to_user(target_user, 60): st.success("成功 +60 天")
                        else: st.error("失敗")
                with b4:
                    if st.button("+90 天", use_container_width=True):
                        if add_days_to_user(target_user, 90): st.success("成功 +90 天")
                        else: st.error("失敗")

                # 🔥 新增功能：計算並顯示有效訂閱人數
                df_users = get_data_as_df('users')
                active_count = 0
                if not df_users.empty:
                    tw_today = (datetime.utcnow() + timedelta(hours=8)).date()
                    for _, row in df_users.iterrows():
                        try:
                            # 讀取到期日並比對是否大於等於今天
                            expiry_str = str(row['expiry'])
                            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                            if expiry_date >= tw_today:
                                active_count += 1
                        except:
                            pass # 忽略日期格式錯誤的
                            
                st.write("")
                st.write("---")
                st.metric(label="🏆 目前有效訂閱人數", value=f"{active_count} 人")
                st.write("📋 **目前會員名單：**")
                st.dataframe(df_users, use_container_width=True)

    # --- VIP 內容區 ---
    if is_vip:
        tab_live, tab_posts = st.tabs(["⚡ 盤中即時熱門榜", "📰 盤後主力日報"])
        
        with tab_live:
            show_live_table()

        with tab_posts:
            st.subheader("📊 主力戰情日報")
            df_posts = get_data_as_df('posts')
            if not df_posts.empty:
                for index, row in df_posts.iloc[::-1].iterrows():
                    with st.container():
                        st.markdown(f"### {row['title']}")
                        st.caption(f"{row['date']}")
                        
                        if row['img']:
                            if "," in str(row['img']): st.image(row['img'].split(","))
                            else: st.image(row['img'])
                        
                        content = row['content']
                        if "<div" in content or "<html" in content or "<style>" in content:
                            components.html(content, height=600, scrolling=True)
                        else:
                            st.write(content)
                        st.divider()
            else: st.info("尚無文章")

    else:
        st.error("⛔ 您的會員權限尚未開通或已到期。")
        # 🔥 修改價格：$299/月
        st.link_button("👉 前往歐付寶付款 ($299/月)", OPAY_URL, use_container_width=True)
        st.write("#### 🔒 最新戰情預覽")
        df_posts = get_data_as_df('posts')
        if not df_posts.empty:
            for index, row in df_posts.iloc[::-1].iterrows():
                st.info(f"🔒 {row['date']} | {row['title']}")
