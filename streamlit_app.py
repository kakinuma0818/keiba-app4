import re
import math
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

# =========================================
# ページ設定
# =========================================
st.set_page_config(page_title="KEIBA APP", layout="wide")

PRIMARY = "#ff7f00"

st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: #ffffff;
        color: #111;
        font-family: "Helvetica", sans-serif;
    }}
    .keiba-title {{
        font-size: 1.6rem;
        font-weight: bold;
        color: {PRIMARY};
    }}
    .keiba-subtitle {{
        font-size: 0.9rem;
        color: #666;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="keiba-title">KEIBA APP</div>', unsafe_allow_html=True)
st.markdown('<div class="keiba-subtitle">出馬表 → スコア → 馬券 の一括サポート</div>', unsafe_allow_html=True)
st.markdown("---")


# =========================================
# race_id 抽出
# =========================================
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


# =========================================
# 出馬表スクレイピング
# =========================================
def fetch_shutuba(race_id: str):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, None

    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")

    # レース名
    name_el = soup.select_one(".RaceName")
    race_name = name_el.get_text(strip=True) if name_el else ""

    # 概要（頭数・距離・馬場など）
    info_el = soup.select_one(".RaceData01")
    race_info = info_el.get_text(" ", strip=True) if info_el else ""

    # 出馬数を race_info に統合
    horse_rows = soup.select("table.RaceTable01 tr")[1:]
   頭数 = len(horse_rows)
    race_info += f"　頭数:{頭数}"

    # 芝/ダートと距離
    surface = "不明"
    if "芝" in race_info:
        surface = "芝"
    elif "ダ" in race_info:
        surface = "ダート"
    m = re.search(r"(\d+)m", race_info)
    distance = int(m.group(1)) if m else None

    # 出馬表
    table = soup.select_one("table.RaceTable01")
    if not table:
        return None, {"race_name": race_name, "race_info": race_info, "surface": surface, "distance": distance}

    header_row = table.find("tr")
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    def idx(label):
        for i, h in enumerate(headers):
            if label in h:
                return i
        return None

    rows = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if not tds:
            continue

        def safe(i):
            return tds[i].get_text(strip=True) if i is not None and i < len(tds) else ""

        rows.append({
            "枠": safe(idx("枠")),
            "馬番": safe(idx("馬番")),
            "馬名": safe(idx("馬名")),
            "性齢": safe(idx("性齢")),
            "斤量": safe(idx("斤量")),
            "前走体重": safe(idx("馬体重")),
            "騎手": safe(idx("騎手")),
            "オッズ": safe(idx("オッズ")),
            "人気": safe(idx("人気")),
        })

    df = pd.DataFrame(rows)
    df["オッズ"] = pd.to_numeric(df["オッズ"], errors="coerce")
    df["人気"] = pd.to_numeric(df["人気"], errors="coerce")

    meta = {
        "race_name": race_name,
        "race_info": race_info,
        "surface": surface,
        "distance": distance,
        "headcount": 頭数,
        "url": url,
    }
    return df, meta


# =========================================
# 年齢スコア（仮）
# =========================================
def score_age(sexage: str, surface: str):
    m = re.search(r"(\d+)", sexage)
    if not m:
        return 2
    age = int(m.group(1))
    if surface == "ダート":
        if 3 <= age <= 4:
            return 3
        elif age == 5:
            return 2
        elif age == 6:
            return 1.5
        else:
            return 1
    else:
        if 3 <= age <= 5:
            return 3
        elif age == 6:
            return 2
        else:
            return 1


# =========================================
# スコア表作成
# =========================================
def build_score(df, meta):
    surface = meta["surface"]
    sc = df.copy()
    sc["年齢"] = sc["性齢"].apply(lambda x: score_age(x, surface))
    sc["合計"] = sc["年齢"]  # 現状は年齢のみ
    return sc


# =========================================
# 馬券自動配分
# =========================================
def allocate_bets(bets_df, total_budget, mult):
    P = total_budget * mult
    threshold = P * 0.9

    results = []
    need = 0

    selected = bets_df[bets_df["購入"] & bets_df["オッズ"].notna()]
    for _, row in selected.iterrows():
        odds = row["オッズ"]
        stake = math.ceil((threshold / odds) / 100) * 100
        payout = stake * odds
        need += stake

        results.append({
            "馬名": row["馬名"],
            "オッズ": odds,
            "推奨金額": stake,
            "想定払い戻し": payout
        })

    return pd.DataFrame(results), {
        "目標": P,
        "下限": threshold,
        "必要金額": need,
        "残り": total_budget - need
    }


# =========================================
# 1. レース指定
# =========================================
st.markdown("### 1. レース指定")

race_input = st.text_input("レースURL または race_id（12桁）")
go = st.button("読み込む")

race_df = None
race_meta = None

if go and race_input:
    race_id = parse_race_id(race_input)
    if not race_id:
        st.error("race_id を認識できませんでした。")
    else:
        df, meta = fetch_shutuba(race_id)
        if df is None:
            st.error("出馬表取得に失敗しました。")
        else:
            race_df, race_meta = df, meta
            st.success("取得完了！")
            st.write(f"**レース名:** {meta['race_name']}")
            st.write(f"**情報:** {meta['race_info']}")
            st.write(f"[netkeibaリンク]({meta['url']})")


# =========================================
# 2. タブ表示
# =========================================
if race_df is not None:

    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    # ---------------- 出馬表 ----------------
    with tab_ma:
        st.markdown("#### 出馬表")
        st.dataframe(race_df, width="stretch")

    # ---------------- スコア ----------------
    with tab_sc:
        st.markdown("#### スコア（年齢のみ）")
        sc = build_score(race_df, race_meta)
        sc = sc.sort_values("合計", ascending=False).reset_index(drop=True)
        st.dataframe(sc, width="stretch")

    # ---------------- AIスコア（仮） ----------------
    with tab_ai:
        st.markdown("#### AIスコア（仮）")
        ai = sc[["馬名", "合計"]].rename(columns={"合計": "AIスコア"})
        st.dataframe(ai, width="stretch")

    # ---------------- 馬券 ----------------
    with tab_be:
        st.markdown("#### 馬券自動配分")

        col1, col2 = st.columns(2)
        with col1:
            total = st.number_input("総投資額", 100, 200000, 1000, 100)
        with col2:
            mult = st.slider("希望倍率", 1.0, 10.0, 1.5, 0.5)

        bet_df = race_df[["馬名", "オッズ"]].copy()
        bet_df["購入"] = False

        edited = st.data_editor(bet_df, width="stretch")

        if st.button("計算する"):
            alloc, info = allocate_bets(edited, total, mult)
            st.write(info)
            st.dataframe(alloc, width="stretch")

    # ---------------- 基本情報 ----------------
    with tab_pr:
        st.markdown("#### 基本情報")
        st.dataframe(race_df, width="stretch")


else:
    st.info("レースURLかIDを入力して読み込んでください。")
