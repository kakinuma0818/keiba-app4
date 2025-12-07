import re
import math
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

# ======================
# ページ設定 & テーマ
# ======================
st.set_page_config(page_title="KEIBA APP", layout="wide")

PRIMARY = "#ff7f00"

st.markdown(
    f"""
<style>
.stApp {{
    background-color: #ffffff;
    color: #111111;
    font-family: "Helvetica", sans-serif;
}}
.keiba-title {{
    font-size: 1.4rem;
    font-weight: 700;
    color: {PRIMARY};
}}
.keiba-subtitle {{
    font-size: 0.9rem;
    color: #555555;
}}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="keiba-title">KEIBA APP</div>', unsafe_allow_html=True)
st.markdown('<div class="keiba-subtitle">出馬表 → スコア → 馬券配分を一括サポート</div>', unsafe_allow_html=True)
st.markdown("---")


# ======================
# race_id 抽出
# ======================
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


# ======================
# 出馬表取得
# ======================
def fetch_shutuba(race_id: str):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, None

    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")

    race_name = soup.select_one(".RaceName").get_text(strip=True) if soup.select_one(".RaceName") else ""
    race_info = soup.select_one(".RaceData01").get_text(" ", strip=True) if soup.select_one(".RaceData01") else ""

    # 頭数の抽出
    m_n = re.search(r"(\d+)頭", race_info)
    num_horses = int(m_n.group(1)) if m_n else None

    # 出馬表テーブル
    table = soup.select_one("table.RaceTable01") or soup.find("table")
    if table is None:
        return None, {"race_name": race_name, "race_info": race_info, "url": url}

    header_row = table.find("tr")
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    def idx(key):
        for i, h in enumerate(headers):
            if key in h:
                return i
        return None

    index_map = {
        "枠": idx("枠"),
        "馬番": idx("馬番"),
        "馬名": idx("馬名"),
        "性齢": idx("性齢"),
        "斤量": idx("斤量"),
        "前走体重": idx("馬体重"),
        "騎手": idx("騎手"),
        "オッズ": idx("オッズ"),
        "人気": idx("人気"),
    }

    rows = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if not tds:
            continue

        def safe(key):
            i = index_map[key]
            return tds[i].get_text(strip=True) if (i is not None and i < len(tds)) else ""

        rows.append({col: safe(col) for col in index_map})

    df = pd.DataFrame(rows)
    df["オッズ"] = pd.to_numeric(df["オッズ"], errors="coerce")
    df["人気"] = pd.to_numeric(df["人気"], errors="coerce")

    meta = {
        "race_name": race_name,
        "race_info": race_info,
        "num_horses": num_horses if num_horses else len(df),
        "url": url,
    }
    return df, meta


# ======================
# 年齢スコア
# ======================
def score_age(sexage: str):
    m = re.search(r"(\d+)", sexage)
    if not m:
        return 2.0
    age = int(m.group(1))

    if 3 <= age <= 5:
        return 3.0
    elif age == 6:
        return 2.0
    else:
        return 1.0


# ======================
# スコアベース作成
# ======================
def build_score_base(df: pd.DataFrame):
    sc = df.copy()
    sc["年齢"] = sc["性齢"].fillna("").apply(score_age)

    # 必須でない列は全て安全に初期化
    optional_cols = [
        "血統", "騎手スコア", "馬主", "生産者", "調教師",
        "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"
    ]
    for c in optional_cols:
        sc[c] = 0.0

    return sc


# ======================
# 馬券配分
# ======================
def allocate_bets(bets_df, total_budget, target_mult):
    P = total_budget * target_mult
    threshold = P * 0.9  # -10% 許容

    results = []
    needed = 0

    selected = bets_df[bets_df["購入"] & bets_df["オッズ"].notna()]
    for _, row in selected.iterrows():
        odds = float(row["オッズ"])
        raw = threshold / odds
        stake = int(math.ceil(raw / 100) * 100)
        payout = stake * odds
        needed += stake

        results.append({
            "馬名": row["馬名"],
            "オッズ": odds,
            "推奨金額": stake,
            "想定払い戻し": payout
        })

    info = {
        "目標": P,
        "下限": threshold,
        "必要": needed,
        "残り": total_budget - needed
    }
    return pd.DataFrame(results), info


# ======================
# UI：レース入力
# ======================
st.markdown("### 1. レース指定")

race_input = st.text_input("netkeiba レースURL / race_id（12桁）を入力")
go = st.button("読み込む")

race_df = None
race_meta = None

if go and race_input:
    race_id = parse_race_id(race_input)
    if not race_id:
        st.error("race_id を認識できません。")
    else:
        df, meta = fetch_shutuba(race_id)
        if df is None:
            st.error("出馬表が取得できませんでした。")
        else:
            race_df, race_meta = df, meta

            st.success("取得成功！")
            st.markdown(f"**{meta['race_name']}**")
            st.markdown(f"**{meta['race_info']} | {meta['num_horses']}頭**")
            st.markdown(f"[netkeibaで見る]({meta['url']})")


# ======================
# タブ
# ======================
if race_df is not None:

    score_base = build_score_base(race_df)

    # -------------------------
    # タブ生成（ここがエラーで止まると出馬表だけになる）
    # -------------------------
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    # ============================================
    # 出馬表タブ
    # ============================================
    with tab1:
        st.markdown("#### 出馬表（印入力）")

        # 手動スコア反映前の暫定合計
        tmp = score_base.copy()
        tmp["手動"] = 0
        tmp["合計"] = tmp[["年齢"]].sum(axis=1)
        tmp = tmp.sort_values("合計", ascending=False).reset_index(drop=True)
        tmp["順位"] = tmp.index + 1

        list_df = race_df.merge(tmp[["馬名", "順位", "合計"]], on="馬名", how="left")

        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]
        mark_list = []
        for _, row in list_df.iterrows():
            key = f"mark_{row['馬名']}"
            val = st.selectbox(f"{row['馬番']} {row['馬名']} 印", marks, key=key)
            mark_list.append(val)

        list_df["印"] = mark_list

        st.dataframe(
            list_df[["枠", "馬番", "馬名", "性齢", "斤量",
                     "騎手", "オッズ", "人気", "順位", "印"]],
            use_container_width=True
        )

    # ============================================
    # スコアタブ
    # ============================================
    with tab2:
        st.markdown("#### スコア（手動補正つき）")

        sc = score_base.copy()

        manual = []
        for _, row in sc.iterrows():
            key = f"manual_{row['馬名']}"
            val = st.selectbox(f"{row['馬番']} {row['馬名']} 手動", [-3, -2, -1, 0, 1, 2, 3], key=key)
            manual.append(val)

        sc["手動"] = manual
        sc["合計"] = sc["年齢"] + sc["手動"]
        sc = sc.sort_values("合計", ascending=False).reset_index(drop=True)

        st.dataframe(
            sc[["馬名", "合計", "年齢", "手動"]],
            use_container_width=True
        )

    # ============================================
    # AIスコア
    # ============================================
    with tab3:
        st.markdown("#### AIスコア（暫定）")

        ai = sc[["馬名", "合計"]].rename(columns={"合計": "AIスコア"})
        st.dataframe(ai, use_container_width=True)

    # ============================================
    # 馬券タブ
    # ============================================
    with tab4:
        st.markdown("#### 馬券自動配分")

        col1, col2 = st.columns(2)
        with col1:
            total_budget = st.number_input("総投資額", 100, 1000000, 1000, 100)
        with col2:
            target_mult = st.slider("希望倍率", 1.0, 10.0, 1.5, 0.5)

        bet_df = race_df[["馬名", "オッズ"]].copy()
        bet_df["購入"] = False

        edited = st.data_editor(bet_df, use_container_width=True, num_rows="fixed")

        if st.button("計算"):
            if edited["購入"].sum() == 0:
                st.warning("1つはチェックしてください")
            else:
                alloc, info = allocate_bets(edited, total_budget, target_mult)
                st.dataframe(alloc, use_container_width=True)
                st.write(f"目標: {info['目標']:.0f}")
                st.write(f"下限: {info['下限']:.0f}")
                st.write(f"必要: {info['必要']}")
                st.write(f"残り: {info['残り']}")

    # ============================================
    # 基本情報
    # ============================================
    with tab5:
        st.dataframe(
            race_df[["枠", "馬番", "馬名", "性齢", "斤量", "前走体重", "騎手", "オッズ", "人気"]],
            use_container_width=True
        )
