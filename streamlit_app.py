import streamlit as st

# ---------------------------------------------------------
# 基本設定
# ---------------------------------------------------------
st.set_page_config(
    page_title="JRA AI KEIBA",
    page_icon="🐎",
    layout="wide",
)

# ---------------------------------------------------------
# カスタムCSS（デザイン設定）
# ---------------------------------------------------------
st.markdown("""
<style>

body {
    font-family: 'Helvetica', sans-serif;
}

/* ヘッダータイトル */
.main-title {
    font-size: 34px;
    font-weight: bold;
    color: #000000;
    padding: 10px 0px 20px 0px;
}

/* セクション枠 */
.section-box {
    border: 2px solid #FF7F00;   /* エルメスオレンジ */
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 20px;
}

/* タブの色 */
[data-baseweb="tab"] button {
    font-weight: bold !important;
    color: #000000 !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# タイトル
# ---------------------------------------------------------
st.markdown('<div class="main-title">JRA KEIBA AI</div>', unsafe_allow_html=True)

# ---------------------------------------------------------
# タブ構成（最上部）
# ---------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏇 出馬表",
    "📊 スコア",
    "📘 基本情報",
    "📈 成績",
    "💰 馬券&配分"
])

# ---------------------------------------------------------
# 各タブの中身（仮の空枠）
# ---------------------------------------------------------

with tab1:
    st.markdown('<div class="section-box"><h3>出馬表（準備中）</h3></div>', unsafe_allow_html=True)

with tab2:
    st.markdown('<div class="section-box"><h3>スコア（準備中）</h3></div>', unsafe_allow_html=True)

with tab3:
    st.markdown('<div class="section-box"><h3>基本情報（準備中）</h3></div>', unsafe_allow_html=True)

with tab4:
    st.markdown('<div class="section-box"><h3>成績（準備中）</h3></div>', unsafe_allow_html=True)

with tab5:
    st.markdown('<div class="section-box"><h3>馬券 ＆ 自動配分（準備中）</h3></div>', unsafe_allow_html=True)
