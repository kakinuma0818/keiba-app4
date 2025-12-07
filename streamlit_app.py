import streamlit as st

st.set_page_config(page_title="KEIBA TEST", layout="wide")

st.title("タブ動作テスト")

# 必ずタブが表示されるかテスト
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
)

with tab1:
    st.write("出馬表タブ OK")

with tab2:
    st.write("スコアタブ OK")

with tab3:
    st.write("AI スコアタブ OK")

with tab4:
    st.write("馬券タブ OK")

with tab5:
    st.write("基本情報タブ OK")
