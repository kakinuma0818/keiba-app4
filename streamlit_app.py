import streamlit as st

st.set_page_config(layout="wide")

st.title("KEIBA APP FIXED VERSION")

# --- 1. 入力 ---
race_input = st.text_input("race_id or URL")
go = st.button("読み込む")

# --- 2. フラグ管理（ここ重要） ---
if "loaded" not in st.session_state:
    st.session_state.loaded = False
if "race_df" not in st.session_state:
    st.session_state.race_df = None
if "meta" not in st.session_state:
    st.session_state.meta = None

# --- 3. 読み込み時 ---
if go:
    race_id = ...  # ここは今まで通り parse
    df, meta = fetch_shutuba(race_id)

    if df is not None:
        st.session_state.loaded = True
        st.session_state.race_df = df
        st.session_state.meta = meta
    else:
        st.session_state.loaded = False
        st.error("取得失敗")

# --- 4. 読み込み成功したらタブをつくる（軽い処理だけ書く） ---
if st.session_state.loaded:

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    with tab1:
        st.subheader("出馬表")
        st.dataframe(st.session_state.race_df)

    with tab2:
        st.subheader("スコア")
        st.write("ここに後で処理を追加")

    with tab3:
        st.subheader("AIスコア")

    with tab4:
        st.subheader("馬券")

    with tab5:
        st.subheader("基本情報")
        st.write(st.session_state.meta)
