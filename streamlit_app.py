import re
import math
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

# ======================
# ページ設定 / テーマ
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
        font-size: 1.5rem;
        font-weight: 700;
        color: {PRIMARY};
    }}
    .keiba-subtitle {{
        font-size: 1.0rem;
        color: #444444;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="keiba-title">KEIBA APP</div>', unsafe_allow_html=True)
st.markdown('<div class="keiba-subtitle">出馬表 → スコア → 馬券配分までワンタッチ</div>', unsafe_allow_html=True)
st.markdown("---")


# ======================
# race_id 抽出
# ======================
def parse_race_id(text: str):
    text = text.strip()
    if re.fullmatch(r"\d{12}", text):
        return text
    m1 = re.search(r"race_id=(\d{12})", text)
    if m1:
        return m1.group(1)
    m2 = re.search(r"(\d{12})", text)
    if m2:
        return m2.group(1)
    return None


# ======================
# 出馬表スクレイピング
# ======================
def fetch_shutuba(race_id: str):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")

    # レース名 & 情報
    race_name = soup.select_one(".RaceName")
    race_name = race_name.get_text(strip=True) if race_name else ""

    race_info = soup.select_one(".RaceData01")
    race_info = race_info.get_text(" ", strip=True) if race_info else ""

    # コース "芝/ダ" / 距離
    surface = "不明"
    if "芝" in race_info:
        surface = "芝"
    elif "ダ" in race_info:
        surface = "ダート"

    m_dist = re.search(r"(\d+)m", race_info)
    distance = int(m_dist.group(1)) if m_dist else None

    # 出馬表
    table = soup.select_one("table.RaceTable01")
    if table is None:
        return None, {"race_name": race_name, "race_info": race_info, "surface": surface, "distance": distance}

    header_row = table.find("tr")
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    rows = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if not tds:
            continue

        def safe(i):
            return tds[i].get_text(strip=True) if i is not None and i < len(tds) else ""

        def idx(key):
            for i, h in enumerate(headers):
                if key in h:
                    return i
            return None

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

    for col in ["オッズ", "人気"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    meta = {
        "race_name": race_name,
        "race_info": race_info,
        "surface": surface,
        "distance": distance,
        "url": url,
    }

    return df, meta


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
        return 1.0

    else:  # 芝
        if 3 <= age <= 5:
            return 3.0
        elif age == 6:
            return 2.0
        return 1.0


# ======================
# スコアテーブル作成
# ======================
def build_score_df(df: pd.DataFrame, meta: dict):
    surface = meta.get("surface", "不明")

    sc = df.copy()
    sc["年齢"] = sc["性齢"].apply(lambda x: score_age(x, surface))

    # 他は0（後で実装）
    for col in ["血統", "騎手スコア", "馬主", "生産者", "調教師",
                "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]:
        sc[col] = 0.0

    manual_list = []
    for i in range(len(sc)):
        key = f"manual_score_{i}"
        if key not in st.session_state:
            st.session_state[key] = 0
        manual_list.append(st.session_state[key])

    sc["手動"] = manual_list

    base = ["年齢", "血統", "騎手スコア", "馬主", "生産者",
            "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]

    sc["合計"] = sc[base].sum(axis=1) + sc["手動"]

    return sc


# ======================
# 馬券配分
# ======================
def allocate_bets(bets_df, total_budget, target_multiplier, loss_tolerance=0.1):
    P = total_budget * target_multiplier
    threshold = P * (1 - loss_tolerance)

    rows = []
    need = 0

    selected = bets_df[bets_df["購入"]].copy()
    for _, row in selected.iterrows():
        odds = float(row["オッズ"]) if not pd.isna(row["オッズ"]) else 0
        if odds <= 0:
            stake = 0
        else:
            raw = threshold / odds
            stake = int(math.ceil(raw / 100) * 100)

        rows.append({
            "馬名": row["馬名"],
            "オッズ": odds,
            "推奨金額": stake,
            "想定払い戻し": stake * odds
        })
        need += stake

    return pd.DataFrame(rows), {
        "目標払い戻し額": P,
        "許容下限": threshold,
        "必要合計金額": need,
        "残り予算": total_budget - need
    }


# ==================================================
#  レース指定（race_id or URL）
# ==================================================
st.markdown("### 1. レースURL または race_id を入力")

race_input = st.text_input(
    "例：https://race.netkeiba.com/race/shutuba.html?race_id=202507050211",
    placeholder="レースURL または 12桁の race_id"
)

go = st.button("このレースを読み込む")

race_df = None
race_meta = None
race_loaded = False

if go and race_input.strip():
    race_id = parse_race_id(race_input)
    if not race_id:
        st.error("race_id を認識できませんでした。")
    else:
        with st.spinner("出馬表を取得中..."):
            df, meta = fetch_shutuba(race_id)

        if df is None or df.empty:
            st.error("出馬表の取得に失敗しました。")
        else:
            race_df = df
            race_meta = meta
            race_loaded = True

            st.success("出馬表取得成功！")
            st.write(f"**レース名**: {meta['race_name']}")
            st.write(f"**情報**: {meta['race_info']}")
            st.write(f"**URL**: {meta['url']}")

            # ★重要：セッション初期化
            for key in list(st.session_state.keys()):
                if key.startswith("manual_score_") or key.startswith("mark_"):
                    del st.session_state[key]


# ==================================================
#  タブ表示（出馬表 / スコア / AI / 馬券 / 基本情報）
# ==================================================
if race_loaded and race_df is not None:

    st.markdown("---")
    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    # ------------ スコア計算 ---------------
    score_df = build_score_df(race_df, race_meta)
    score_df = score_df.sort_values("合計", ascending=False).reset_index(drop=True)
    score_df["スコア順"] = score_df.index + 1

    ma_df = race_df.merge(score_df[["馬名", "合計", "スコア順"]], on="馬名")
    ma_df = ma_df.sort_values("スコア順").reset_index(drop=True)

    # ---------------- 出馬表タブ ----------------
    with tab_ma:
        st.markdown("#### 出馬表（スコア順 + 印）")

        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]
        mark_list = []

        for i, row in ma_df.iterrows():
            key = f"mark_{i}"
            if key not in st.session_state:
                st.session_state[key] = ""
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 印",
                marks,
                index=marks.index(st.session_state[key]),
                key=key
            )
            st.session_state[key] = val
            mark_list.append(val)

        ma_df["印"] = mark_list

        display_cols = [
            "枠", "馬番", "馬名", "性齢", "斤量", "前走体重",
            "騎手", "オッズ", "人気", "合計", "スコア順", "印"
        ]

        st.dataframe(ma_df[display_cols], use_container_width=True)

    # ---------------- スコアタブ ----------------
    with tab_sc:
        st.markdown("#### スコア（手動補正あり）")

        new_manual = []
        for i, row in score_df.iterrows():
            key = f"manual_score_{i}"
            now = st.session_state.get(key, 0)
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 手動スコア",
                [-3, -2, -1, 0, 1, 2, 3],
                index=[-3, -2, -1, 0, 1, 2, 3].index(now),
                key=key
            )
            st.session_state[key] = val
            new_manual.append(val)

        score_df["手動"] = new_manual

        base = ["年齢", "血統", "騎手スコア", "馬主", "生産者",
                "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]

        score_df["合計"] = score_df[base].sum(axis=1) + score_df["手動"]

        st.dataframe(
            score_df[
                ["馬名", "合計", "年齢", "血統", "騎手スコア",
                 "馬主", "生産者", "調教師", "成績",
                 "競馬場", "距離", "脚質", "枠スコア", "馬場", "手動"]
            ],
            use_container_width=True
        )

    # ---------------- AIスコアタブ ----------------
    with tab_ai:
        st.markdown("#### AIスコア（暫定）")

        ai_df = score_df[["馬名", "合計"]].copy()
        ai_df.rename(columns={"合計": "AIスコア"}, inplace=True)

        st.dataframe(ai_df.sort_values("AIスコア", ascending=False), use_container_width=True)

    # ---------------- 馬券タブ ----------------
    with tab_be:
        st.markdown("#### 馬券自動配分")

        col1, col2 = st.columns(2)
        with col1:
            total_budget = st.number_input("総投資額（円）", 100, 1000000, 1000, 100)
        with col2:
            target_mult = st.slider("希望払い戻し倍率", 1.0, 10.0, 1.5, 0.5)

        bet_df = ma_df[["馬名", "オッズ"]].copy()
        bet_df["購入"] = False

        edited_df = st.data_editor(bet_df, num_rows="fixed", use_container_width=True)

        if st.button("配分を計算"):
            if edited_df["購入"].sum() == 0:
                st.warning("1頭以上チェックしてください。")
            else:
                alloc_df, info = allocate_bets(edited_df, total_budget, target_mult)
                st.subheader("配分結果")
                st.dataframe(alloc_df, use_container_width=True)

                st.write(f"- 目標払い戻し額：**{int(info['目標払い戻し額'])}円**")
                st.write(f"- 必要合計金額：**{int(info['必要合計金額'])}円**")
                st.write(f"- 残り予算：**{int(info['残り予算'])}円**")

    # ---------------- 基本情報タブ ----------------
    with tab_pr:
        st.markdown("#### 基本情報")
        st.dataframe(race_df, use_container_width=True)

else:
    st.info("上にレースURL または race_id を入力して、「読み込む」を押してください。")
