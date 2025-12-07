import streamlit as st

st.set_page_config(layout="wide")

st.title("KEIBA APP テスト版（タブ動作確認用）")

# ---------------------------
# 入力
# ---------------------------
race_input = st.text_input("race_id または URL を入力（今回は何を入れてもOK）")
go = st.button("読み込む")

# ---------------------------
# 状態を保存
# ---------------------------
if "loaded" not in st.session_state:
    st.session_state.loaded = False

if go:
    # 本来はここで fetch_shutuba するが、
    # まずはタブが正しく出るかの確認だけ行うため、
    # 擬似的に loaded True にする
    st.session_state.loaded = True

# ---------------------------
# タブ表示（loaded==Trueのときだけ）
# ---------------------------
if st.session_state.loaded:
    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    with tab_ma:
        st.subheader("出馬表タブ")
        st.write("ここに出馬表が入る予定")

    with tab_sc:
        st.subheader("スコアタブ")
        st.write("ここにスコア計算が入る予定")

    with tab_ai:
        st.subheader("AIスコアタブ")
        st.write("将来のAI予測結果を表示")

    with tab_be:
        st.subheader("馬券タブ")
        st.write("購入配分をここに表示")

    with tab_pr:
        st.subheader("基本情報")
        st.write("レース情報が入る予定")

else:
    st.write("入力して読み込んでください")
