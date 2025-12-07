import streamlit as st
import pandas as pd

# ==========================
# ページ設定
# ==========================
st.set_page_config(
    page_title="KEIBA APP",
    layout="wide"
)

# ==========================
# カスタムCSS（黒 / 白 / エルメスオレンジ）
# ==========================
st.markdown("""
    <style>
        body {
            background-color: #000000;
            color: #ffffff;
        }
        .main {
            background-color: #000000;
        }
        .section-box {
            background-color: #111111;
            padding: 20px;
            margin-top: 20px;
            border-radius: 10px;
            border-left: 6px solid #FF7F00;
        }
        .stButton>button {
            background-color: #FF7F00 !important;
            color: white !important;
            font-size: 18px;
            border-radius: 8px;
            padding: 10px 20px;
        }
        .stTabs [role="tab"] {
            background: #222222;
            color: white;
            padding: 10px 15px;
            border-radius: 6px;
            font-size: 16px;
        }
        .stTabs [aria-selected="true"] {
            background: #FF7F00 !important;
            color: black !important;
        }
        .dataframe td {
            text-align: center !important;
            padding: 6px !important;
        }
        .dataframe th {
            text-align: center !important;
            background: #FF7F00 !important;
            color: white !important;
            padding: 6px !important;
        }
    </style>
""", unsafe_allow_html=True)

# ==========================
# タイトル
# ==========================
st.markdown("<h1 style='text-align:center; margin-top:10px;'>KEIBA APP</h1>", unsafe_allow_html=True)

# ==========================
# タブ UI
# ==========================
tab1, tab2, tab3 = st.tabs(["出馬表", "指数・分析", "設定"])

# ==========================
# TAB1：出馬表
# ==========================
with tab1:

    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.markdown("### 🏇 出馬表（テストデータ）")

    # サンプル出馬表（後で差し替える）
    df = pd.DataFrame({
        "馬番": [1, 2, 3],
        "馬名": ["サンプルホースA", "サンプルホースB", "サンプルホースC"],
        "脚質": ["先行", "差し", "逃げ"],
        "適性": ["ダート1800", "芝2400", "芝2000"],
        "人気": [2, 4, 1],
        "スコア": [78, 65, 82]
    })

    st.dataframe(df, use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ==========================
# TAB2：指数・分析
# ==========================
with tab2:
    st.markdown('<div class="section-box"><h3>指数・分析（準備中）</h3></div>', unsafe_allow_html=True)

# ==========================
# TAB3：設定
# ==========================
with tab3:
    st.markdown('<div class="section-box"><h3>設定（準備中）</h3></div>', unsafe_allow_html=True)
