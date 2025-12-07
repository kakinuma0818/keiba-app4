import re
import math
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

# ---------------------------------------------------------
# ページ設定
# ---------------------------------------------------------
st.set_page_config(page_title="KEIBA APP", layout="wide")

st.title("KEIBA APP")
st.write("出馬表 → スコア → 馬券配分まで一括サポート")
st.markdown("---")


# ---------------------------------------------------------
# race_id 抽出
# ---------------------------------------------------------
def parse_race_id(text: str) -> str | None:
    """URL / 12桁 race_id から 12桁 race_id を取り出す"""
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


# ---------------------------------------------------------
# 出馬表をスクレイピング（本番仕様）
# ---------------------------------------------------------
def fetch_shutuba(race_id: str):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, None

    # 文字化け対策
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")

    # レース名
    race_name_el = soup.select_one(".RaceName")
    race_name = race_name_el.get_text(strip=True) if race_name_el else ""

    # レース概要（距離／天候／頭数 など）
    info_el = soup.select_one(".RaceData01")
    race_info = info_el.get_text(" ", strip=True) if info_el else ""

    # 頭数
    num_horse = None
    m = re.search(r"(\d+)頭", race_info)
    if m:
        num_horse = int(m.group(1))

    # コース種別（芝／ダート）・距離はスコア用に保持（今は年齢スコアのみで使用）
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
            "num_horse": num_horse,
            "surface": surface,
            "distance": distance,
            "url": url,
        }

    header_row = table.find("tr")
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    def find_col(word: str):
        for i, h in enumerate(headers):
            if word in h:
                return i
        return None

    idx_waku = find_col("枠")
    idx_umaban = find_col("馬番")
    idx_name = find_col("馬名")
    idx_sexage = find_col("性齢")
    idx_weight = find_col("斤量")
    idx_body = find_col("馬体重")
    idx_jockey = find_col("騎手")
    idx_odds = find_col("オッズ")
    idx_pop = find_col("人気")

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
                "体重": safe(idx_body),  # 表記は「体重」に統一（前走馬体重）
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
        "num_horse": num_horse,
        "surface": surface,
        "distance": distance,
        "url": url,
    }

    return df, meta


# ---------------------------------------------------------
# 年齢スコア
# ---------------------------------------------------------
def score_age(sexage: str, surface: str) -> float:
    """
    性齢(例: 牡4, 牝3) と 芝/ダートから年齢スコア
    芝: 3〜5歳=3, 6歳=2, 7歳以上=1
    ダ: 3〜4歳=3, 5歳=2, 6歳=1.5, 7歳以上=1
    """
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
    else:  # 芝 or 不明
        if 3 <= age <= 5:
            return 3.0
        elif age == 6:
            return 2.0
        else:
            return 1.0


# ---------------------------------------------------------
# スコア表（SCタブのベース）を作成
#   現時点では「年齢＋手動」だけ有効。その他は0点。
# ---------------------------------------------------------
SCORE_COLS = [
    "年齢",
    "血統",
    "騎手",
    "馬主",
    "生産者",
    "調教師",
    "成績",
    "競馬場",
    "距離",
    "脚質",
    "枠",
    "馬場",
]


def build_score_base(race_df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    surface = meta.get("surface", "不明")

    sc = race_df.copy()
    sc["年齢"] = sc["性齢"].fillna("").apply(lambda x: score_age(x, surface))

    # まだロジック未実装の項目は0点で初期化
    for col in ["血統", "騎手", "馬主", "生産者", "調教師", "成績",
                "競馬場", "距離", "脚質", "枠", "馬場"]:
        sc[col] = 0.0

    return sc


def get_manual_list(df: pd.DataFrame) -> list[int]:
    """manual_score_i を session_state から読むだけ（書き込みはしない）"""
    options = [-3, -2, -1, 0, 1, 2, 3]
    manual = []
    for i, _ in df.iterrows():
        key = f"manual_score_{i}"
        val = st.session_state.get(key, 0)
        if val not in options:
            val = 0
        manual.append(val)
    return manual


# ---------------------------------------------------------
# 馬券 自動配分（単純版）
# ---------------------------------------------------------
def allocate_bets(bets_df: pd.DataFrame, total_budget: int, target_multiplier: float, loss_tolerance: float = 0.1):
    """
    bets_df: columns = ["馬名", "オッズ", "購入"]
    total_budget: 総投資額
    target_multiplier: 希望払い戻し倍率 (例: 1.5)
    loss_tolerance: 目標払い戻し額からどこまで下振れOKか（0.1 で -10%）
    """
    P = total_budget * target_multiplier
    threshold = P * (1 - loss_tolerance)

    results = []
    needed = 0

    selected = bets_df[bets_df["購入"] & bets_df["オッズ"].notna()]
    for _, row in selected.iterrows():
        odds = float(row["オッズ"])
        if odds <= 0:
            stake = 0
        else:
            raw = threshold / odds
            stake = int(math.ceil(raw / 100.0) * 100)

        payout = stake * odds
        needed += stake

        results.append(
            {
                "馬名": row["馬名"],
                "オッズ": odds,
                "推奨金額": stake,
                "想定払い戻し": payout,
            }
        )

    df = pd.DataFrame(results)
    info = {
        "目標払い戻し額": P,
        "許容下限": threshold,
        "必要合計金額": needed,
        "残り予算": total_budget - needed,
    }
    return df, info


# ---------------------------------------------------------
# 1. レース指定 UI
# ---------------------------------------------------------
st.subheader("1. レース指定")

race_input = st.text_input(
    "netkeiba レースURL または race_id（12桁）",
    placeholder="例）https://race.netkeiba.com/race/shutuba.html?race_id=202507050211",
)
go = st.button("このレースを読み込む")

race_df = None
race_meta = None

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

            st.success("出馬表の取得に成功しました ✅")
            # 概要に頭数も含めて表示
            head_str = f" / 頭数: {meta['num_horse']}頭" if meta.get("num_horse") else ""
            st.write(f"**レース名**: {meta.get('race_name','')}")
            st.write(f"**概要**: {meta.get('race_info','')}{head_str}")
            st.write(f"[netkeibaページ]({meta.get('url','')})")


# ---------------------------------------------------------
# 2. タブ表示（出馬表 / スコア / AIスコア / 馬券 / 基本情報）
# ---------------------------------------------------------
if race_df is not None:
    # ---- スコア基礎計算（年齢＋手動） ----
    score_base = build_score_base(race_df, race_meta)
    manual_values = get_manual_list(score_base)
    score_base["手動"] = manual_values
    score_base["スコア"] = score_base[SCORE_COLS].sum(axis=1) + score_base["手動"]

    # スコア順（大きい順）
    score_sorted = score_base.sort_values("スコア", ascending=False).reset_index(drop=True)
    score_sorted["スコア順"] = score_sorted.index + 1

    # 出馬表用にスコアを結合
    ma_df = race_df.merge(score_sorted[["馬名", "スコア", "スコア順"]], on="馬名", how="left")

    st.markdown("---")
    st.subheader("2. 分析タブ")

    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    # -----------------------------------------------------
    # 出馬表タブ（MA）
    # -----------------------------------------------------
    with tab_ma:
        st.markdown("#### 出馬表（スコア順＋印）")

        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]
        mark_list = []
        for i, row in ma_df.iterrows():
            key = f"mark_{i}"
            current = st.session_state.get(key, "")
            default_index = marks.index(current) if current in marks else 0
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} の印",
                marks,
                index=default_index,
                key=key,
            )
            mark_list.append(val)

        ma_df["印"] = mark_list

        ma_display = ma_df[
            ["枠", "馬番", "馬名", "性齢", "斤量", "体重", "騎手", "オッズ", "人気", "スコア", "スコア順", "印"]
        ].sort_values("スコア順")

        st.dataframe(ma_display, width="stretch", hide_index=True)

    # -----------------------------------------------------
    # スコアタブ（SC）
    # -----------------------------------------------------
    with tab_sc:
        st.markdown("#### スコア（年齢＋手動スコア）")

        sc_df = build_score_base(race_df, race_meta)
        manual_vals = []
        options = [-3, -2, -1, 0, 1, 2, 3]

        for i, row in sc_df.iterrows():
            key = f"manual_score_{i}"
            current = st.session_state.get(key, 0)
            if current not in options:
                current = 0
            default_index = options.index(current)
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 手動スコア",
                options,
                index=default_index,
                key=key,
            )
            manual_vals.append(val)

        sc_df["手動"] = manual_vals
        sc_df["スコア"] = sc_df[SCORE_COLS].sum(axis=1) + sc_df["手動"]

        sc_display = sc_df[
            ["馬名", "スコア", "年齢", "血統", "騎手", "馬主", "生産者",
             "調教師", "成績", "競馬場", "距離", "脚質", "枠", "馬場", "手動"]
        ].sort_values("スコア", ascending=False)

        st.dataframe(sc_display, width="stretch", hide_index=True)
        st.caption("※ 現時点では「年齢スコア＋手動」だけが有効。他の項目は0点（あとから本ロジックを追加）。")

    # -----------------------------------------------------
    # AIスコアタブ
    # -----------------------------------------------------
    with tab_ai:
        st.markdown("#### AIスコア（暫定版）")
        # 今はスコアと同じ値をそのまま表示しておく
        ai_df = sc_df[["馬名", "スコア"]].copy()
        ai_df = ai_df.sort_values("スコア", ascending=False)
        ai_df = ai_df.rename(columns={"スコア": "AIスコア"})

        st.dataframe(ai_df, width="stretch", hide_index=True)
        st.caption("※ 将来的に別ロジックのAIスコアに差し替え予定。")

    # -----------------------------------------------------
    # 馬券タブ
    # -----------------------------------------------------
    with tab_be:
        st.markdown("#### 馬券配分（単純版）")

        col1, col2 = st.columns(2)
        with col1:
            total_budget = st.number_input("総投資額（円）", min_value=100, max_value=1_000_000, value=1000, step=100)
        with col2:
            target_mult = st.slider("希望払い戻し倍率", min_value=1.0, max_value=10.0, value=1.5, step=0.5)

        st.write("チェックした馬すべてで、少なくとも **目標払い戻し額の -10%** を確保するように自動配分します。")

        bet_df = ma_df[["馬名", "オッズ"]].copy()
        bet_df["購入"] = False

        edited = st.data_editor(bet_df, num_rows="fixed", width="stretch", hide_index=True)

        if st.button("自動配分を計算"):
            if edited["購入"].sum() == 0:
                st.warning("少なくとも1頭は購入にチェックしてください。")
            else:
                alloc_df, info = allocate_bets(edited, total_budget, target_mult, loss_tolerance=0.1)

                st.subheader("推奨配分結果")
                st.dataframe(alloc_df, width="stretch", hide_index=True)

                st.write(f"- 目標払い戻し額: **{int(info['目標払い戻し額'])}円**")
                st.write(f"- 下限（-10%許容）: **{int(info['許容下限'])}円**")
                st.write(f"- 必要合計金額: **{int(info['必要合計金額'])}円**")
                st.write(f"- 残り予算: **{int(info['残り予算'])}円**")

                if info["必要合計金額"] > total_budget:
                    st.error("💡 現在の総投資額では、すべての馬券で目標払い戻しを満たせません。")
                    st.write("・総投資額を増やすか、")
                    st.write("・希望払い戻し倍率を下げるか、")
                    st.write("・購入点数（チェックする頭数）を減らしてください。")
                else:
                    st.success("どれか1点的中で、少なくとも下限払い戻しを確保できます。")

    # -----------------------------------------------------
    # 基本情報タブ
    # -----------------------------------------------------
    with tab_pr:
        st.markdown("#### 基本情報")
        st.dataframe(
            race_df[["枠", "馬番", "馬名", "性齢", "斤量", "体重", "騎手", "オッズ", "人気"]],
            width="stretch",
            hide_index=True,
        )

else:
    st.info("上の入力欄に netkeiba のレースURL または race_id を入力して「このレースを読み込む」を押してください。")
