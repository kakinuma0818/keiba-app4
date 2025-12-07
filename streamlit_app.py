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
    .accent {{
        color: {PRIMARY};
    }}
    .small-label {{
        font-size: 0.8rem;
        color: #666666;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="keiba-title">KEIBA APP</div>', unsafe_allow_html=True)
st.markdown('<div class="keiba-subtitle">出馬表 → スコア → 馬券配分まで一括サポート</div>', unsafe_allow_html=True)
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
# 出馬表スクレイピング（文字化け対応）
# ======================
def fetch_shutuba(race_id: str):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, None

    r.encoding = r.apparent_encoding  # ← 文字化け防止

    soup = BeautifulSoup(r.text, "html.parser")

    race_name_el = soup.select_one(".RaceName")
    race_name = race_name_el.get_text(strip=True) if race_name_el else ""

    race_info_el = soup.select_one(".RaceData01")
    race_info = race_info_el.get_text(" ", strip=True) if race_info_el else ""

    surface = "不明"
    distance = None
    if "芝" in race_info:
        surface = "芝"
    elif "ダ" in race_info:
        surface = "ダート"
    m_dist = re.search(r"(\d+)m", race_info)
    if m_dist:
        distance = int(m_dist.group(1))

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

    def idx(contain_str):
        for i, h in enumerate(headers):
            if contain_str in h:
                return i
        return None

    idx_waku = idx("枠")
    idx_umaban = idx("馬番")
    idx_name = idx("馬名")
    idx_sexage = idx("性齢")
    idx_weight = idx("斤量")
    idx_jockey = idx("騎手")
    idx_body = idx("馬体重")
    idx_odds = idx("オッズ")
    idx_pop = idx("人気")

    rows = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if not tds:
            continue

        def safe(i):
            return tds[i].get_text(strip=True) if i is not None and i < len(tds) else ""

        rows.append(
            {
                "枠": safe(idx_waku),
                "馬番": safe(idx_umaban),
                "馬名": safe(idx_name),
                "性齢": safe(idx_sexage),
                "斤量": safe(idx_weight),
                "前走体重": safe(idx_body),
                "騎手": safe(idx_jockey),
                "オッズ": safe(idx_odds),
                "人気": safe(idx_pop),
            }
        )

    df = pd.DataFrame(rows)
    df["オッズ"] = pd.to_numeric(df["オッズ"], errors="coerce")
    df["人気"] = pd.to_numeric(df["人気"], errors="coerce")

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
# スコアテーブル生成（現時点は年齢＋手動）
# ======================
def build_score_df(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    surface = meta.get("surface", "不明")

    sc = df.copy()
    sc["年齢"] = sc["性齢"].fillna("").apply(lambda x: score_age(x, surface))

    # 他項目はまだ0（今後追加）
    for col in ["血統", "騎手スコア", "馬主", "生産者", "調教師",
                "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]:
        sc[col] = 0.0

    # 手動（session_stateに読み書きせず、値として保存する）
    manual_list = []
    for i in range(len(sc)):
        key = f"manual_score_{i}"
        val = st.session_state.get(key, 0)
        manual_list.append(val)
    sc["手動"] = manual_list

    base_cols = ["年齢", "血統", "騎手スコア", "馬主", "生産者",
                 "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]
    sc["合計"] = sc[base_cols].sum(axis=1) + sc["手動"]

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

    df = pd.DataFrame(results)
    info = {
        "目標払い戻し額": P,
        "許容下限": threshold,
        "必要合計金額": needed,
        "残り予算": total_budget - needed,
    }
    return df, info


# ======================
# UI：レースURL入力
# ======================
st.markdown("### 1. レース指定")

race_input = st.text_input(
    "netkeiba レースURL または race_id（12桁）",
    placeholder="例）https://race.netkeiba.com/race/shutuba.html?race_id=202507050211",
)
go = st.button("このレースを読み込む")

race_df = None
race_meta = None

if go and race_input:
    race_id = parse_race_id(race_input)
    if not race_id:
        st.error("race_id を認識できませんでした。")
    else:
        with st.spinner("出馬表を取得中..."):
            df, meta = fetch_shutuba(race_id)
        if df is None:
            st.error("出馬表の取得に失敗しました。")
        else:
            race_df = df
            race_meta = meta

            st.success("出馬表取得OK！")
            st.write(f"**レース名**: {meta['race_name']}")
            st.write(f"**概要**: {meta['race_info']}")
            st.write(f"[netkeibaページへ]({meta['url']})")


# ======================
# タブ表示
# ======================
if race_df is not None:

    st.markdown("---")
    st.markdown("### 2. 各種タブ")

    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    # ---- SC計算 ----
    score_df = build_score_df(race_df, race_meta)
    score_df = score_df.sort_values("合計", ascending=False).reset_index(drop=True)
    score_df["スコア順"] = score_df.index + 1

    ma_df = race_df.merge(score_df[["馬名", "合計", "スコア順"]], on="馬名")
    ma_df = ma_df.sort_values("スコア順").reset_index(drop=True)

    # ========== 出馬表タブ ==========
    with tab_ma:
        st.markdown("#### 出馬表（印つき）")

        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]
        mark_list = []
        for i, row in ma_df.iterrows():
            key = f"mark_{i}"
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

    # ========== スコアタブ ==========
    with tab_sc:
        st.markdown("#### スコア（手動補正つき）")

        new_manual = []
        for i, row in score_df.iterrows():
            key = f"manual_score_{i}"
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 手動スコア",
                [-3, -2, -1, 0, 1, 2, 3],
                key=key
            )
            new_manual.append(val)

        score_df["手動"] = new_manual

        base_cols = ["年齢", "血統", "騎手スコア", "馬主", "生産者",
                     "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]
        score_df["合計"] = score_df[base_cols].sum(axis=1) + score_df["手動"]

        score_df = score_df.sort_values("合計", ascending=False).reset_index(drop=True)

        st.dataframe(
            score_df[["馬名", "合計", "年齢", "血統", "騎手スコア", "馬主",
                      "生産者", "調教師", "成績", "競馬場", "距離", "脚質",
                      "枠スコア", "馬場", "手動"]],
            use_container_width=True
        )

    # ========== AIスコア（仮） ==========
    with tab_ai:
        st.markdown("#### AIスコア（仮）")
        ai = score_df[["馬名", "合計"]].rename(columns={"合計": "AIスコア"})
        st.dataframe(ai.sort_values("AIスコア", ascending=False), use_container_width=True)

    # ========== 馬券タブ ==========
    with tab_be:
        st.markdown("#### 馬券配分")

        col1, col2 = st.columns(2)
        with col1:
            total_budget = st.number_input("総投資額", 100, 1000000, 1000, 100)
        with col2:
            target_mult = st.slider("希望払い戻し倍率", 1.0, 10.0, 1.5, 0.5)

        st.write("→ チェックした馬すべてで同じ払い戻しを確保するよう自動調整")

        bet_df = ma_df[["馬名", "オッズ"]].copy()
        bet_df["購入"] = False

        edited = st.data_editor(bet_df, num_rows="fixed", use_container_width=True)

        if st.button("自動配分計算"):
            if edited["購入"].sum() == 0:
                st.warning("1つ以上チェックしてください")
            else:
                alloc, info = allocate_bets(edited, total_budget, target_mult)

                st.subheader("推奨配分")
                st.dataframe(alloc, use_container_width=True)

                st.write(f"- 目標払い戻し額: {info['目標払い戻し額']:.0f} 円")
                st.write(f"- 下限（許容）: {info['許容下限']:.0f} 円")
                st.write(f"- 必要合計: {info['必要合計金額']} 円")
                st.write(f"- 残り: {info['残り予算']} 円")

                if info["必要合計金額"] > total_budget:
                    st.error("💡 この設定では目標払い戻しを満たせません。")

    # ========== 基本情報 ==========
    with tab_pr:
        st.markdown("#### 基本情報")
        st.dataframe(
            race_df[["枠", "馬番", "馬名", "性齢", "斤量", "前走体重", "騎手", "オッズ", "人気"]],
            use_container_width=True
        )

else:
    st.info("URL または race_id を入力して「読み込む」を押してください。")
