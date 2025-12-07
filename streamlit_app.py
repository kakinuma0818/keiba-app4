import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
import re

st.set_page_config(page_title="KEIBA APP", layout="wide")
st.title("KEIBA APP（STEP3：スコア計算付き）")

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

    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")

    race_name = soup.select_one(".RaceName")
    race_info = soup.select_one(".RaceData01")
    race_name = race_name.get_text(strip=True) if race_name else ""
    race_info = race_info.get_text(" ", strip=True) if race_info else ""

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
    return df, {"race_name": race_name, "race_info": race_info, "url": url}


# ------------------------------------------------
# スコアロジック
# ------------------------------------------------
def calc_scores(df: pd.DataFrame):
    df = df.copy()

    # --- 馬齢スコア ---
    def score_age(seirei):
        m = re.match(r"[牡牝騙](\d+)", seirei)
        if not m:
            return 50
        age = int(m.group(1))
        base = {3: 85, 4: 95, 5: 90, 6: 80, 7: 70}
        return base.get(age, 60)

    df["馬齢スコア"] = df["性齢"].apply(score_age)

    # --- 斤量スコア ---
    def score_weight(x):
        try:
            w = float(x)
        except:
            return 50
        if w <= 52: return 85
        if w <= 54: return 90
        if w <= 56: return 95
        if w <= 57: return 90
        return 80

    df["斤量スコア"] = df["斤量"].apply(score_weight)

    # --- 騎手スコア ---
    JOCKEY_BASE = {
        "川田将雅": 100, "ルメール": 100, "武豊": 95,
        "横山武史": 92, "戸崎圭太": 92, "福永祐一": 95,
    }
    df["騎手スコア"] = df["騎手"].apply(lambda x: JOCKEY_BASE.get(x, 80))

    # --- 人気スコア ---
    def score_ninki(x):
        try:
            n = int(x)
        except:
            return 50
        if n == 1: return 100
        if n <= 3: return 95
        if n <= 5: return 90
        if n <= 10: return 80
        return 70

    df["人気スコア"] = df["人気"].apply(score_ninki)

    # --- オッズスコア ---
    def score_odds(x):
        try:
            o = float(x)
        except:
            return 50
        if o <= 3.0: return 100
        if o <= 5.0: return 95
        if o <= 10.0: return 90
        return 80

    df["オッズスコア"] = df["オッズ"].apply(score_odds)

    # --- 合計スコア ---
    df["総合スコア"] = (
        df["馬齢スコア"]
        + df["斤量スコア"]
        + df["騎手スコア"]
        + df["人気スコア"]
        + df["オッズスコア"]
    ) / 5

    df = df.sort_values("総合スコア", ascending=False).reset_index(drop=True)
    return df


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
            st.write(meta["race_info"])


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

# --- スコア ---
with tab2:
    st.write("### スコア計算")
    if race_df is None:
        st.info("レースを読み込んでください。")
    else:
        score_df = calc_scores(race_df)
        st.dataframe(score_df, width="stretch")

# --- その他のタブ ---
with tab3:
    st.write("AIスコアは STEP4 で追加します。")

with tab4:
    st.write("馬券計算は STEP5 で追加します。")

with tab5:
    st.write("基本情報は STEP6 で追加します。")
