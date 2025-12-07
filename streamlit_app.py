import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
import re

st.set_page_config(page_title="KEIBA APP", layout="wide")

st.title("KEIBA APP（STEP2：出馬表テスト）")

# ------------------------------------------------
# race_id 抽出
# ------------------------------------------------
def parse_race_id(text: str):
    text = text.strip()
    if re.fullmatch(r"\d{12}", text):
        return text
    m = re.search(r"race_id=(\d{12})", text)
    if m:
        return m.group(1)
    m2 = re.search(r"(\d{12})", text)
    if m2:
        return m2.group(1)
    return None


# ------------------------------------------------
# 出馬表スクレイピング
# ------------------------------------------------
def fetch_shutuba(race_id: str):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, {}

    # 文字化け対策
    r.encoding = r.apparent_encoding

    soup = BeautifulSoup(r.text, "html.parser")

    race_name = soup.select_one(".RaceName")
    race_info = soup.select_one(".RaceData01")

    race_name = race_name.get_text(strip=True) if race_name else ""
    race_info = race_info.get_text(" ", strip=True) if race_info else ""

    # 出馬表テーブル
    table = soup.select_one("table.RaceTable01")
    if not table:
        return None, {"race_name": race_name, "race_info": race_info}

    rows = []
    trs = table.find_all("tr")[1:]
    for tr in trs:
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue

        rows.append({
            "枠": tds[0].get_text(strip=True),
            "馬番": tds[1].get_text(strip=True),
            "馬名": tds[3].get_text(strip=True),
            "性齢": tds[4].get_text(strip=True),
            "斤量": tds[5].get_text(strip=True),
            "騎手": tds[6].get_text(strip=True),
            "オッズ": tds[7].get_text(strip=True),
            "人気": tds[8].get_text(strip=True) if len(tds) > 8 else "",
        })

    df = pd.DataFrame(rows)

    return df, {
        "race_name": race_name,
        "race_info": race_info,
        "url": url,
    }


# ------------------------------------------------
# UI
# ------------------------------------------------
st.markdown("### 1. レース URL または race_id を入力")

url_input = st.text_input("URL または race_id（12桁）を入力")
load_btn = st.button("出馬表を取得")

race_df = None
race_meta = None

if load_btn and url_input:
    race_id = parse_race_id(url_input)
    if not race_id:
        st.error("race_id を認識できませんでした。")
    else:
        with st.spinner("取得中..."):
            df, meta = fetch_shutuba(race_id)
        if df is None:
            st.error("出馬表の取得に失敗しました。")
        else:
            race_df = df
            race_meta = meta
            st.success("出馬表取得成功！")
            st.write(f"### {meta['race_name']}")
            st.write(meta['race_info'])

# ------------------------------------------------
# タブ
# ------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
)

# --- 出馬表 ---
with tab1:
    st.write("### 出馬表")

    if race_df is None:
        st.info("レースを読み込んでください。")
    else:
        st.dataframe(race_df, width="stretch")

# --- その他のタブ ---
with tab2:
    st.write("スコア機能は STEP3 で追加します。")

with tab3:
    st.write("AIスコアは STEP4 で追加します。")

with tab4:
    st.write("馬券計算は STEP5 で追加します。")

with tab5:
    st.write("基本情報は STEP6 で追加します。")
