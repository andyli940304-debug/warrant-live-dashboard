# 🔥 重大修改：加入快取機制 (TTL = 20秒)
# 這行指令的意思是：這份資料讀回來後，會在記憶體存活 20 秒。
# 20 秒內如果有別人也要看資料，直接給他看舊的，不要去煩 Google。
@st.cache_data(ttl=20)
def get_live_warrant_data():
    try:
        # 為了確保快取運作正常，我們在函式內部建立連線，確保獨立性
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        
        # 處理 Secrets 格式
        if "gcp_key" in st.secrets:
            key_data = st.secrets["gcp_key"]
            if isinstance(key_data, str):
                key_dict = json.loads(key_data)
            else:
                key_dict = key_data
                
            creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
            client = gspread.authorize(creds)
            
            # 開啟試算表
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
        # 如果連線失敗 (例如 Google 偶爾秀逗)，回傳空表格，不要讓網站掛掉
        return pd.DataFrame()
