import streamlit as st
from src.ui_style import inject_style
from src.data_loader import load_dummy_data
from src.keiba_logic import simple_rank

# -----------------------------
# ページ設定
# -----------------------------
st.set_page_config(
    page_title="Keiba App",
    page_icon="🐎",
    layout="wide"
)

inject_style()

# -----------------------------
# UI：トップヘッダー
# -----------------------------
st.markdown("""
<div style='text-align:center; padding:12px; font-size:26px; font-weight:bold; border-bottom:2px solid #ff7f00;'>
KEIBA APP
</div>
""", unsafe_allow_html=True)

# -----------------------------
# メインUI
# -----------------------------
st.markdown("<div class='block-title'>出走馬データ（テスト）</div>", unsafe_allow_html=True)
df = load_dummy_data()
st.dataframe(df)

# -----------------------------
# ボタン
# -----------------------------
if st.button("評価する", type="primary"):
    ranked = simple_rank(df)
    st.markdown("<div class='block-title'>評価結果</div>", unsafe_allow_html=True)
    st.dataframe(ranked)
