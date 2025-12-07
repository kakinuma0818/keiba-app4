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
st.markdown('<div class="keiba-subtitle">出馬表 → スコア → 馬券配分まで一括サポート</div>', unsafe_allow_html=True)
st.markdown("---")


# ======================
# race_id 抽出
# ======================
def parse_race_id(text: str) -> str | None:
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
# 出馬表取得（netkeiba PC版）
# ======================
def fetch_shutuba(race_id: str):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, None

    # 文字化け対策
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")

    race_name_el = soup.select_one(".RaceName")
    race_name = race_name_el.get_text(strip=True) if race_name_el else ""

    race_info_el = soup.select_one(".RaceData01")
    race_info = race_info_el.get_text(" ", strip=True) if race_info_el else ""

    # 頭数
    m_n = re.search(r"(\d+)頭", race_info)
    num_horses = int(m_n.group(1)) if m_n else None

    # 出馬表テーブル
    table = soup.select_one("table.RaceTable01") or soup.find("table")
    if table is None:
        return None, {
            "race_name": race_name,
            "race_info": race_info,
            "num_horses": num_horses,
            "url": url,
        }

    header_row = table.find("tr")
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    def idx(keyword: str):
        for i, h in enumerate(headers):
            if keyword in h:
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

        def safe(col):
            i = index_map[col]
            return tds[i].get_text(strip=True) if (i is not None and i < len(tds)) else ""

        rows.append({col: safe(col) for col in index_map})

    df = pd.DataFrame(rows)
    df["オッズ"] = pd.to_numeric(df["オッズ"], errors="coerce")
    df["人気"] = pd.to_numeric(df["人気"], errors="coerce")

    meta = {
        "race_name": race_name,
        "race_info": race_info,
        "num_horses": num_horses if num_horses is not None else len(df),
        "url": url,
    }
    return df, meta


# ======================
# 年齢スコア（ひとまず芝・ダ区別なしの簡易版）
# ======================
def score_age(sexage: str) -> float:
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
# スコア用ベースDF
# ======================
def build_score_base(df: pd.DataFrame) -> pd.DataFrame:
    sc = df.copy()
    sc["年齢"] = sc["性齢"].fillna("").apply(score_age)

    # まだロジック未実装の項目は 0 で初期化（枠だけ用意）
    extra_cols = [
        "血統", "騎手スコア", "馬主", "生産者",
        "調教師", "成績", "競馬場", "距離",
        "脚質", "枠スコア", "馬場",
    ]
    for c in extra_cols:
        sc[c] = 0.0

    # 手動はこの関数ではまだ入れない（タブ側で入れる）
    return sc


# ======================
# 馬券自動配分（単純版）
# ======================
def allocate_bets(bets_df: pd.DataFrame, total_budget: int, target_multiplier: float):
    """
    target_multiplier 倍の払い戻しを目標とし、
    どの馬が当たっても「目標の90%」以上になるように 100円単位で配分。
    """
    P = total_budget * target_multiplier
    threshold = P * 0.9

    results = []
    needed_total = 0

    selected = bets_df[bets_df["購入"] & bets_df["オッズ"].notna()]
    for _, row in selected.iterrows():
        odds = float(row["オッズ"])
        if odds <= 0:
            stake = 0
        else:
            raw = threshold / odds
            stake = int(math.ceil(raw / 100.0) * 100)

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
# UI：レース指定
# ======================
st.markdown("### 1. レース指定")

race_input = st.text_input(
    "netkeiba レースURL または race_id（12桁）",
    placeholder="https://race.netkeiba.com/race/shutuba.html?race_id=202507050211",
)
go = st.button("このレースを読み込む")

race_df = None
race_meta = None

if go and race_input.strip():
    race_id = parse_race_id(race_input)
    if not race_id:
        st.error("race_id を認識できませんでした。URL または 12桁のIDを入力してください。")
    else:
        with st.spinner("出馬表を取得中..."):
            df, meta = fetch_shutuba(race_id)

        if df is None or df.empty:
            st.error("出馬表の取得に失敗しました。レースIDやページ構造を確認してください。")
        else:
            race_df, race_meta = df, meta
            st.success("出馬表の取得に成功しました ✅")
            st.write(f"**レース名**: {meta['race_name']}")
            # 頭数は race_info に含まれていればそのまま。なければ num_horses を付け足す
            info_text = meta["race_info"]
            if "頭" not in info_text and meta.get("num_horses"):
                info_text = f"{info_text} / {meta['num_horses']}頭"
            st.write(f"**概要**: {info_text}")
            st.write(f"[netkeiba ページを開く]({meta['url']})")


# ======================
# タブ表示
# ======================
if race_df is not None:

    # スコア計算のベース
    score_base = build_score_base(race_df)

    st.markdown("---")
    st.markdown("### 2. 出馬表 / スコア / 馬券")

    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    # ------------------------------------------------------------------
    # 出馬表タブ
    # ------------------------------------------------------------------
    with tab_ma:
        st.markdown("#### 出馬表（印つき）")

        # ひとまず 年齢スコアのみで仮の合計を作ってランク付け
        tmp = score_base.copy()
        tmp["手動"] = 0
        tmp["合計"] = tmp["年齢"]  # 現状は年齢のみ
        tmp = tmp.sort_values("合計", ascending=False).reset_index(drop=True)
        tmp["スコア順"] = tmp.index + 1

        ma_df = race_df.merge(tmp[["馬名", "合計", "スコア順"]], on="馬名", how="left")

        # 印入力（session_state はいじらない）
        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]
        mark_values = []
        for i, row in ma_df.iterrows():
            label = f"{row.get('馬番', '')} {row['馬名']} 印"
            val = st.selectbox(label, marks, key=f"mark_{i}")
            mark_values.append(val)
        ma_df["印"] = mark_values

        # 表示
        disp_cols = ["枠", "馬番", "馬名", "性齢", "斤量",
                     "前走体重", "騎手", "オッズ", "人気", "合計", "スコア順", "印"]
        st.dataframe(ma_df[disp_cols], use_container_width=True)

    # ------------------------------------------------------------------
    # スコアタブ
    # ------------------------------------------------------------------
    with tab_sc:
        st.markdown("#### スコア（手動補正つき）")

        sc = score_base.copy()

        manual_scores = []
        for i, row in sc.iterrows():
            label = f"{row.get('馬番', '')} {row['馬名']} 手動スコア"
            val = st.selectbox(
                label,
                options=[-3, -2, -1, 0, 1, 2, 3],
                index=3,  # デフォルト 0
                key=f"manual_{i}",
            )
            manual_scores.append(val)

        sc["手動"] = manual_scores

        base_cols = ["年齢", "血統", "騎手スコア", "馬主", "生産者",
                     "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]
        sc["合計"] = sc[base_cols].sum(axis=1) + sc["手動"]

        sc = sc.sort_values("合計", ascending=False).reset_index(drop=True)

        st.dataframe(
            sc[["馬名", "合計", "年齢", "血統", "騎手スコア", "馬主",
                "生産者", "調教師", "成績", "競馬場", "距離",
                "脚質", "枠スコア", "馬場", "手動"]],
            use_container_width=True,
        )

    # ------------------------------------------------------------------
    # AIスコアタブ（今は SC と同じ値）
    # ------------------------------------------------------------------
    with tab_ai:
        st.markdown("#### AIスコア（現状はスコア合計と同一）")
        ai_df = sc[["馬名", "合計"]].rename(columns={"合計": "AIスコア"})
        st.dataframe(ai_df.sort_values("AIスコア", ascending=False), use_container_width=True)

    # ------------------------------------------------------------------
    # 馬券タブ
    # ------------------------------------------------------------------
    with tab_be:
        st.markdown("#### 馬券配分")

        col1, col2 = st.columns(2)
        with col1:
            total_budget = st.number_input("総投資額（円）", 100, 1000000, 1000, 100)
        with col2:
            target_mult = st.slider("希望払い戻し倍率", 1.0, 10.0, 1.5, 0.5)

        st.write("チェックした馬を対象に、どの馬が当たっても同水準の払い戻しになるよう配分します。")

        bet_df = ma_df[["馬名", "オッズ"]].copy()
        bet_df["購入"] = False

        edited = st.data_editor(bet_df, num_rows="fixed", use_container_width=True)

        if st.button("自動配分を計算"):
            if edited["購入"].sum() == 0:
                st.warning("少なくとも1頭は『購入』にチェックしてください。")
            else:
                alloc_df, info = allocate_bets(edited, total_budget, target_mult)
                st.subheader("推奨配分")
                st.dataframe(alloc_df, use_container_width=True)

                st.write(f"- 目標払い戻し額: **{int(info['目標払い戻し額'])}円**")
                st.write(f"- 下限（-10%許容）: **{int(info['許容下限'])}円**")
                st.write(f"- 必要合計金額: **{int(info['必要合計金額'])}円**")
                st.write(f"- 残り予算: **{int(info['残り予算'])}円**")

                if info["必要合計金額"] > total_budget:
                    st.error("現在の総投資額では、全ての馬券で目標払い戻しを達成できません。")

    # ------------------------------------------------------------------
    # 基本情報タブ
    # ------------------------------------------------------------------
    with tab_pr:
        st.markdown("#### 基本情報")
        st.dataframe(
            race_df[["枠", "馬番", "馬名", "性齢", "斤量", "前走体重", "騎手", "オッズ", "人気"]],
            use_container_width=True,
        )

else:
    st.info("上の入力欄に netkeiba のレースURL または race_id を入力し、「このレースを読み込む」を押してください。")
    
