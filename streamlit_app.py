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

PRIMARY = "#ff7f00"  # エルメスオレンジ

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
# URL → race_id 変換
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
# 出馬表スクレイピング（完全安定版）
# ======================
def fetch_shutuba(race_id: str):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, None

    r.encoding = r.apparent_encoding  # ← 文字化け対策

    soup = BeautifulSoup(r.text, "html.parser")

    # レース名
    race_name = soup.select_one(".RaceName")
    race_name = race_name.get_text(strip=True) if race_name else ""

    # レース情報
    race_info = soup.select_one(".RaceData01")
    race_info = race_info.get_text(" ", strip=True) if race_info else ""

    # 芝・ダート + 距離
    surface = "不明"
    if "芝" in race_info:
        surface = "芝"
    elif "ダ" in race_info:
        surface = "ダート"

    m_dist = re.search(r"(\d+)m", race_info)
    distance = int(m_dist.group(1)) if m_dist else None

    # 出馬表テーブル
    table = soup.select_one("table.RaceTable01")
    if table is None:
        return None, {
            "race_name": race_name,
            "race_info": race_info,
            "surface": surface,
            "distance": distance,
            "url": url,
        }

    header_row = table.find("tr")
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    def idx(key):
        for i, h in enumerate(headers):
            if key in h:
                return i
        return None

    rows = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if not tds:
            continue

        def safe(i):
            return tds[i].get_text(strip=True) if i is not None and i < len(tds) else ""

        rows.append(
            {
                "枠": safe(idx("枠")),
                "馬番": safe(idx("馬番")),
                "馬名": safe(idx("馬名")),
                "性齢": safe(idx("性齢")),
                "斤量": safe(idx("斤量")),
                "前走体重": safe(idx("馬体重")),
                "騎手": safe(idx("騎手")),
                "オッズ": safe(idx("オッズ")),
                "人気": safe(idx("人気")),
            }
        )

    df = pd.DataFrame(rows)
    df["オッズ"] = pd.to_numeric(df["オッズ"], errors="coerce")
    df["人気"] = pd.to_numeric(df["人気"], errors="coerce")

    return df, {
        "race_name": race_name,
        "race_info": race_info,
        "surface": surface,
        "distance": distance,
        "url": url,
    }


# ======================
# 年齢スコア
# ======================
def score_age(sexage: str, surface: str) -> float:
    m = re.search(r"(\d+)", sexage)
    if not m:
        return 2.0
    age = int(m.group(1))

    if surface == "ダート":
        if 3 <= age <= 4:
            return 3.0
        elif age == 5:
            return 2.0
        elif age == 6:
            return 1.5
        else:
            return 1.0
    else:
        if 3 <= age <= 5:
            return 3.0
        elif age == 6:
            return 2.0
        else:
            return 1.0


# ======================
# SC テーブル構築（安定版）
# ======================
def build_score_df(df, meta):
    surface = meta.get("surface", "不明")

    sc = df.copy()
    sc["年齢"] = sc["性齢"].fillna("").apply(lambda x: score_age(x, surface))

    # 他スコア（後で実装）
    zero_cols = ["血統", "騎手スコア", "馬主", "生産者", "調教師",
                 "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]
    for c in zero_cols:
        sc[c] = 0.0

    # 手動スコア（馬名ベースの key → 衝突しない）
    manual_vals = []
    for _, row in sc.iterrows():
        key = f"manual_{row['馬名']}"
        val = st.session_state.get(key, 0)
        manual_vals.append(val)
    sc["手動"] = manual_vals

    base = ["年齢"] + zero_cols
    sc["合計"] = sc[base].sum(axis=1) + sc["手動"]

    return sc


# ======================
# 馬券 自動配分
# ======================
def allocate_bets(bets_df, total_budget, target_multiplier, loss_tolerance=0.1):
    P = total_budget * target_multiplier
    threshold = P * (1 - loss_tolerance)

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
            "想定払い戻し": payout,
        })

    return pd.DataFrame(results), {
        "目標払い戻し額": P,
        "許容下限": threshold,
        "必要合計金額": needed,
        "残り予算": total_budget - needed,
    }


# ======================
# UI：レースURL入力
# ======================
st.markdown("### 1. レース指定")

race_input = st.text_input(
    "netkeiba URL または 12桁 race_id",
    placeholder="例：https://race.netkeiba.com/race/shutuba.html?race_id=202507050211"
)
go = st.button("このレースを読み込む")

race_df, race_meta = None, None

if go and race_input:
    rid = parse_race_id(race_input)
    if not rid:
        st.error("race_id を認識できません。")
    else:
        with st.spinner("取得中…"):
            df, meta = fetch_shutuba(rid)
        if df is None:
            st.error("出馬表取得に失敗しました。")
        else:
            race_df, race_meta = df, meta
            st.success("取得成功！")
            st.write(f"**レース名**：{meta['race_name']}")
            st.write(f"**情報**：{meta['race_info']}")
            st.write(f"[netkeiba ページ]({meta['url']})")


# ======================
# タブ構成
# ======================
if race_df is not None:

    st.markdown("---")
    st.markdown("### 2. 各タブ")

    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    # スコア計算
    score_df = build_score_df(race_df, race_meta)
    score_df = score_df.sort_values("合計", ascending=False).reset_index(drop=True)
    score_df["スコア順"] = score_df.index + 1

    ma_df = race_df.merge(score_df[["馬名", "合計", "スコア順"]], on="馬名")
    ma_df = ma_df.sort_values("スコア順").reset_index(drop=True)

    # ===== 出馬表 =====
    with tab_ma:
        st.markdown("#### 出馬表（印つき）")

        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]
        mark_list = []

        for _, row in ma_df.iterrows():
            key = f"mark_{row['馬名']}"  # ← ここが重要！
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 印",
                marks,
                key=key
            )
            mark_list.append(val)

        ma_df["印"] = mark_list

        st.dataframe(
            ma_df[["枠", "馬番", "馬名", "性齢", "斤量", "前走体重",
                   "騎手", "オッズ", "人気", "合計", "スコア順", "印"]],
            use_container_width=True
        )

    # ===== スコアタブ =====
    with tab_sc:
        st.markdown("#### スコア（手動補正つき）")

        new_manual = []
        for _, row in score_df.iterrows():
            key = f"manual_{row['馬名']}"
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 手動スコア",
                [-3, -2, -1, 0, 1, 2, 3],
                key=key
            )
            new_manual.append(val)

        score_df["手動"] = new_manual

        base_cols = ["年齢", "血統", "騎手スコア", "馬主", "生産者", "調教師",
                     "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]

        score_df["合計"] = score_df[base_cols].sum(axis=1) + score_df["手動"]
        score_df = score_df.sort_values("合計", ascending=False).reset_index(drop=True)

        st.dataframe(
            score_df[["馬名", "合計", "年齢", "血統", "騎手スコア", "馬主",
                       "生産者", "調教師", "成績", "競馬場", "距離",
                       "脚質", "枠スコア", "馬場", "手動"]],
            use_container_width=True
        )

    # ===== AIスコア（仮） =====
    with tab_ai:
        st.markdown("#### AIスコア（現状＝スコア）")
        ai = score_df[["馬名", "合計"]].rename(columns={"合計": "AIスコア"})
        st.dataframe(ai, use_container_width=True)

    # ===== 馬券 =====
    with tab_be:
        st.markdown("#### 馬券配分")

        col1, col2 = st.columns(2)
        with col1:
            total_budget = st.number_input("総投資額", 100, 1000000, 1000, 100)
        with col2:
            target_mult = st.slider("希望払い戻し倍率", 1.0, 10.0, 1.5, 0.5)

        bet_df = ma_df[["馬名", "オッズ"]].copy()
        bet_df["購入"] = False

        edited = st.data_editor(bet_df, num_rows="fixed", use_container_width=True)

        if st.button("自動配分計算"):
            if edited["購入"].sum() == 0:
                st.warning("1頭以上チェックしてください")
            else:
                alloc, info = allocate_bets(edited, total_budget, target_mult)

                st.subheader("推奨配分結果")
                st.dataframe(alloc, use_container_width=True)

                st.write(f"- 目標払い戻し額: {info['目標払い戻し額']:.0f}円")
                st.write(f"- 下限: {info['許容下限']:.0f}円")
                st.write(f"- 必要合計: {info['必要合計金額']}円")
                st.write(f"- 残り: {info['残り予算']}円")

                if info["必要合計金額"] > total_budget:
                    st.error("総投資額が不足しています。倍率を下げるか点数を絞ってください。")

    # ===== 基本情報 =====
    with tab_pr:
        st.markdown("#### 基本情報")
        st.dataframe(
            race_df[["枠", "馬番", "馬名", "性齢", "斤量", "前走体重",
                     "騎手", "オッズ", "人気"]],
            use_container_width=True
        )

else:
    st.info("URL か race_id を入力して読み込んでください。")
