# streamlit_app.py
import streamlit as st
import pandas as pd

# ---------- ページ設定 ----------
st.set_page_config(
    page_title="KEIBA APP",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
    body {font-family: 'Helvetica'; background-color: white; color: black;}
    .highlight {color: #FF6700; font-weight:bold;}  /* エルメスオレンジ */
    table {border-collapse: collapse; width: 100%;}
    th, td {padding: 8px; text-align: left; border-bottom: 1px solid #ddd;}
    th {background-color: #f2f2f2;}
    </style>
    """, unsafe_allow_html=True
)

# ---------- 固定レースID ----------
# デモ用：2025/12/7 中京 11R
race_id = "202507050211"

# ---------- サイドバー ----------
st.sidebar.header("レース選択")
st.sidebar.write("固定レースID：", race_id)

# ---------- タブ ----------
tab_names = ["出馬表", "スコア", "馬券", "基本情報", "成績"]
tabs = st.tabs(tab_names)

# ---------- デモデータ ----------
horses = [
    {"馬名":"ウマ1","性齢":"牡4","斤量":57,"体重":500,"印":"◎","スコア":85,"手動":0},
    {"馬名":"ウマ2","性齢":"牝3","斤量":55,"体重":480,"印":"○","スコア":78,"手動":0},
    {"馬名":"ウマ3","性齢":"牡5","斤量":58,"体重":520,"印":"▲","スコア":70,"手動":0},
]
df = pd.DataFrame(horses)

# ---------- 出馬表 ----------
with tabs[0]:
    st.subheader("出馬表")
    st.dataframe(df[["馬名","性齢","斤量","体重","印","スコア"]])

# ---------- スコア ----------
with tabs[1]:
    st.subheader("スコア")
    # 手動スコア追加
    manual_scores = []
    for i, row in df.iterrows():
        manual = st.selectbox(f"{row['馬名']} 手動スコア", options=[-3,-2,-1,0,1,2,3], index=0, key=f"manual_{i}")
        manual_scores.append(manual)
    df["手動"] = manual_scores
    df["合計"] = df["スコア"] + df["手動"]
    st.dataframe(df[["馬名","合計","性齢","斤量","体重","印","スコア","手動"]])

# ---------- 馬券 ----------
with tabs[2]:
    st.subheader("馬券")
    st.write("※ここに馬券購入UIを追加予定（チェックボックス、単勝・複勝・3連複など）")
    st.write("総投資金額、希望払い戻し倍率の設定後に自動配分")

# ---------- 基本情報 ----------
with tabs[3]:
    st.subheader("基本情報")
    st.write("性齢、血統、騎手、馬主、生産者、調教師、成績、競馬場、距離、脚質、枠、馬場などを表示予定")

# ---------- 成績 ----------
with tabs[4]:
    st.subheader("成績")
    st.write("過去成績、勝率、複勝率、距離適性などを表示予定")
