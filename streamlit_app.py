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
st.markdown(
    '<div class="keiba-subtitle">出馬表 → スコア → 馬券配分まで一括サポート</div>',
    unsafe_allow_html=True,
)
st.markdown("---")

# ======================
# session_state 初期化
# ======================
if "race_df" not in st.session_state:
    st.session_state["race_df"] = None
if "race_meta" not in st.session_state:
    st.session_state["race_meta"] = None


# ======================
# race_id 抽出
# ======================
def parse_race_id(text: str):
    """URL または 12桁ID から race_id を取り出す"""
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
# 出馬表スクレイピング
# ======================
def fetch_shutuba(race_id: str):
    """
    netkeiba PC版 出馬表ページから情報を取得
    - レース名・概要（距離/芝ダ/頭数など）
    - 出馬表（枠, 馬番, 馬名, 性齢, 斤量, 前走体重, 騎手, オッズ, 人気）
    """
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        return None, None

    r.encoding = r.apparent_encoding  # 文字化け防止
    soup = BeautifulSoup(r.text, "html.parser")

    # レース名
    race_name_el = soup.select_one(".RaceName")
    race_name = race_name_el.get_text(strip=True) if race_name_el else ""

    # 概要
    race_info_el = soup.select_one(".RaceData01")
    race_info = race_info_el.get_text(" ", strip=True) if race_info_el else ""

    # 芝 / ダート & 距離
    surface = "不明"
    distance = None
    if "芝" in race_info:
        surface = "芝"
    if "ダ" in race_info or "ダート" in race_info:
        surface = "ダート"
    m_dist = re.search(r"(\d+)m", race_info)
    if m_dist:
        distance = int(m_dist.group(1))

    # 出馬表テーブル
    table = soup.select_one("table.RaceTable01")
    if table is None:
        return None, None

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

    horse_rows = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if not tds:
            continue

        def safe(i):
            return tds[i].get_text(strip=True) if i is not None and i < len(tds) else ""

        horse_rows.append(
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

    df = pd.DataFrame(horse_rows)
    for col in ["オッズ", "人気"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    headcount = len(df)
    if headcount > 0 and f"{headcount}頭" not in race_info:
        race_info = race_info + f"　/　{headcount}頭"

    meta = {
        "race_name": race_name,
        "race_info": race_info,
        "surface": surface,
        "distance": distance,
        "url": url,
        "headcount": headcount,
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
# スコアテーブル
# ======================
def build_score_df(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    surface = meta.get("surface", "不明")

    sc = df.copy()
    sc["年齢"] = sc["性齢"].fillna("").apply(lambda x: score_age(x, surface))

    for col in [
        "血統",
        "騎手スコア",
        "馬主",
        "生産者",
        "調教師",
        "成績",
        "競馬場",
        "距離",
        "脚質",
        "枠スコア",
        "馬場",
    ]:
        sc[col] = 0.0

    manual_vals = []
    for i in range(len(sc)):
        key = f"manual_score_{i}"
        manual_vals.append(st.session_state.get(key, 0))
    sc["手動"] = manual_vals

    base_cols = [
        "年齢",
        "血統",
        "騎手スコア",
        "馬主",
        "生産者",
        "調教師",
        "成績",
        "競馬場",
        "距離",
        "脚質",
        "枠スコア",
        "馬場",
    ]
    sc["合計"] = sc[base_cols].sum(axis=1) + sc["手動"]

    return sc


# ======================
# 馬券 自動配分
# ======================
def allocate_bets(bets_df, total_budget, target_multiplier, loss_tolerance=0.1):
    P = total_budget * target_multiplier
    threshold = P * (1 - loss_tolerance)

    results = []
    needed_total = 0

    selected = bets_df[bets_df["購入"] & bets_df["オッズ"].notna()]

    for _, row in selected.iterrows():
        odds = float(row["オッズ"])
        if odds <= 0:
            stake = 0
        else:
            raw = threshold / odds
            stake = int(math.ceil(raw / 100) * 100)

        payout = stake * odds
        needed_total += stake

        results.append(
            {
                "馬名": row["馬名"],
                "オッズ": odds,
                "推奨金額": stake,
                "想定払い戻し": payout,
            }
        )

    alloc_df = pd.DataFrame(results)
    info = {
        "目標払い戻し額": P,
        "許容下限": threshold,
        "必要合計金額": needed_total,
        "残り予算": total_budget - needed_total,
    }
    return alloc_df, info


# ======================
# 1. レース指定 UI
# ======================
st.markdown("### 1. レース指定")

race_input = st.text_input(
    "netkeiba レースURL または race_id（12桁）",
    placeholder="例）https://race.netkeiba.com/race/shutuba.html?race_id=202507050211",
)
go = st.button("このレースを読み込む")

if go and race_input.strip():
    race_id = parse_race_id(race_input)
    if not race_id:
        st.error("race_id を認識できませんでした。URL または 12桁のIDを入力してください。")
    else:
        with st.spinner("出馬表を取得中..."):
            df, meta = fetch_shutuba(race_id)
        if df is None or df.empty:
            st.error("出馬表の取得に失敗しました。")
        else:
            st.session_state["race_df"] = df
            st.session_state["race_meta"] = meta
            st.success("出馬表を取得しました ✅")

race_df = st.session_state["race_df"]
race_meta = st.session_state["race_meta"]

if race_meta:
    st.write(f"**レース名**：{race_meta.get('race_name','')}")
    st.write(f"**概要**：{race_meta.get('race_info','')}")
    if race_meta.get("url"):
        st.write(f"[netkeibaページを開く]({race_meta['url']})")

# ======================
# 2. タブ（常に表示）
# ======================
st.markdown("---")
st.markdown("### 2. 出馬表・スコア・馬券")

tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
    ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
)

# ---------- 共通：race_df が無いとき ----------
if race_df is None or race_meta is None:
    with tab_ma:
        st.info("まず上でレースURL / race_id を入力して『このレースを読み込む』を押してください。")
    with tab_sc:
        st.info("レースを読み込むとスコアが表示されます。")
    with tab_ai:
        st.info("レースを読み込むとAIスコアが表示されます。")
    with tab_be:
        st.info("レースを読み込むと馬券配分ツールが使えます。")
    with tab_pr:
        st.info("レースを読み込むと基本情報が表示されます。")
else:
    # ========= スコア計算 =========
    score_df = build_score_df(race_df, race_meta)
    score_df = score_df.sort_values("合計", ascending=False).reset_index(drop=True)
    score_df["スコア順"] = score_df.index + 1
    ma_df = race_df.merge(
        score_df[["馬名", "合計", "スコア順"]], on="馬名", how="left"
    ).sort_values("スコア順").reset_index(drop=True)

    # ========= 出馬表タブ =========
    with tab_ma:
        st.markdown("#### 出馬表（印つき・スコア順）")

        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]
        mark_values = []

        for i, row in ma_df.iterrows():
            key = f"mark_{i}"
            default_mark = st.session_state.get(key, "")
            if default_mark not in marks:
                default_mark = ""
            idx = marks.index(default_mark)

            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} の印",
                marks,
                index=idx,
                key=key,
            )
            mark_values.append(val)

        ma_df["印"] = mark_values

        ma_display = ma_df[
            [
                "枠",
                "馬番",
                "馬名",
                "性齢",
                "斤量",
                "前走体重",
                "騎手",
                "オッズ",
                "人気",
                "合計",
                "スコア順",
                "印",
            ]
        ]
        st.dataframe(ma_display, width="stretch")

    # ========= スコアタブ =========
    with tab_sc:
        st.markdown("#### スコア詳細（手動補正つき）")

        new_manual = []
        for i, row in score_df.iterrows():
            key = f"manual_score_{i}"
            default_manual = st.session_state.get(key, 0)
            if default_manual not in [-3, -2, -1, 0, 1, 2, 3]:
                default_manual = 0
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 手動スコア",
                [-3, -2, -1, 0, 1, 2, 3],
                index=[-3, -2, -1, 0, 1, 2, 3].index(default_manual),
                key=key,
            )
            new_manual.append(val)

        score_df["手動"] = new_manual
        base_cols = [
            "年齢",
            "血統",
            "騎手スコア",
            "馬主",
            "生産者",
            "調教師",
            "成績",
            "競馬場",
            "距離",
            "脚質",
            "枠スコア",
            "馬場",
        ]
        score_df["合計"] = score_df[base_cols].sum(axis=1) + score_df["手動"]
        score_df = score_df.sort_values("合計", ascending=False).reset_index(drop=True)

        sc_display = score_df[
            [
                "馬名",
                "合計",
                "年齢",
                "血統",
                "騎手スコア",
                "馬主",
                "生産者",
                "調教師",
                "成績",
                "競馬場",
                "距離",
                "脚質",
                "枠スコア",
                "馬場",
                "手動",
            ]
        ]
        st.dataframe(sc_display, width="stretch")

    # ========= AIスコアタブ =========
    with tab_ai:
        st.markdown("#### AIスコア（暫定）")
        ai_df = score_df[["馬名", "合計"]].rename(columns={"合計": "AIスコア"})
        st.dataframe(ai_df.sort_values("AIスコア", ascending=False), width="stretch")

    # ========= 馬券タブ =========
    with tab_be:
        st.markdown("#### 馬券配分（単勝イメージ）")

        col1, col2 = st.columns(2)
        with col1:
            total_budget = st.number_input("総投資額（円）", 100, 1000000, 1000, 100)
        with col2:
            target_mult = st.slider("希望払い戻し倍率", 1.0, 10.0, 1.5, 0.5)

        st.write("チェックした馬の単勝を、どれが当たっても同じくらいの払い戻しになるように自動配分します。")

        bet_df = ma_df[["馬名", "オッズ"]].copy()
        bet_df["購入"] = False
        edited = st.data_editor(bet_df, num_rows="fixed", width="stretch")

        if st.button("自動配分を計算"):
            if edited["購入"].sum() == 0:
                st.warning("少なくとも1頭は『購入』にチェックしてください。")
            else:
                alloc_df, info = allocate_bets(
                    edited, total_budget, target_mult, loss_tolerance=0.1
                )
                st.subheader("推奨配分結果")
                if alloc_df.empty:
                    st.warning("有効なオッズが取得できていません。")
                else:
                    st.dataframe(alloc_df, width="stretch")
                    st.write(f"- 目標払い戻し額: **{int(info['目標払い戻し額'])}円**")
                    st.write(f"- 下限（-10%許容）: **{int(info['許容下限'])}円**")
                    st.write(f"- 必要合計金額: **{int(info['必要合計金額'])}円**")
                    st.write(f"- 残り予算: **{int(info['残り予算'])}円**")

    # ========= 基本情報タブ =========
    with tab_pr:
        st.markdown("#### 基本情報")
        pr_cols = [
            "枠",
            "馬番",
            "馬名",
            "性齢",
            "斤量",
            "前走体重",
            "騎手",
            "オッズ",
            "人気",
        ]
        st.dataframe(race_df[pr_cols], width="stretch")
