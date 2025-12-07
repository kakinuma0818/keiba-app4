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
# 出馬表スクレイピング（HTML変更に強い版）
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

    # レース名
    race_name_el = soup.select_one(".RaceName")
    race_name = race_name_el.get_text(strip=True) if race_name_el else ""

    # レース情報（距離・馬場など）
    race_info_el = soup.select_one(".RaceData01")
    race_info = race_info_el.get_text(" ", strip=True) if race_info_el else ""

    # 芝/ダート・距離
    surface = "不明"
    if "芝" in race_info:
        surface = "芝"
    elif "ダ" in race_info:
        surface = "ダート"

    m_dist = re.search(r"(\d+)m", race_info)
    distance = int(m_dist.group(1)) if m_dist else None

    # コース方向（右/左/直線）を race_info からざっくり判定
    direction = ""
    if "右" in race_info:
        direction = "右回り"
    elif "左" in race_info:
        direction = "左回り"
    elif "直線" in race_info:
        direction = "直線"

    # 出馬表テーブル：クラス名が変わっても拾えるように多段フォールバック
    table = (
        soup.select_one("table.RaceTable01")
        or soup.select_one("table.Shutuba_Table")
        or soup.find("table", {"class": lambda x: x and "Table" in x})
        or soup.find("table")
    )

    if table is None:
        # テーブルが見つからない場合でもメタ情報だけ返す
        return None, {
            "race_name": race_name,
            "race_info": race_info,
            "surface": surface,
            "distance": distance,
            "direction": direction,
            "num_horses": 0,
            "url": url,
        }

    header_row = table.find("tr")
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    def idx(key):
        for i, h in enumerate(headers):
            if key in h:
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
        "direction": direction,
        "num_horses": len(df),
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
    else:  # 芝 or 不明
        if 3 <= age <= 5:
            return 3.0
        elif age == 6:
            return 2.0
        else:
            return 1.0


# ======================
# スコアベース作成（年齢＋空の項目）
# ======================
def build_base_score_df(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    surface = meta.get("surface", "不明")

    sc = df.copy()
    sc["年齢"] = sc["性齢"].fillna("").apply(lambda x: score_age(x, surface))

    # 他スコア（今はまだ0、あとで本格ロジック追加）
    zero_cols = [
        "血統", "騎手スコア", "馬主", "生産者",
        "調教師", "成績", "競馬場", "距離",
        "脚質", "枠スコア", "馬場"
    ]
    for c in zero_cols:
        sc[c] = 0.0

    # 手動は後で付与
    return sc


# ======================
# 馬券 自動配分
# ======================
def allocate_bets(bets_df, total_budget, target_multiplier, loss_tolerance=0.1):
    """
    bets_df: 馬名・オッズ・購入(True/False)
    total_budget: 総投資額
    target_multiplier: 希望払戻倍率
    loss_tolerance: 何%まで目標を下回ることを許容するか（0.1 = -10%）
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
            payout = 0
        else:
            raw = threshold / odds
            stake = int(math.ceil(raw / 100) * 100)  # 100円単位
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

    alloc_df = pd.DataFrame(results)
    info = {
        "目標払い戻し額": P,
        "許容下限": threshold,
        "必要合計金額": needed,
        "残り予算": total_budget - needed,
    }
    return alloc_df, info


# ======================
# UI：レース指定
# ======================
st.markdown("### 1. レース指定")

race_input = st.text_input(
    "netkeiba のレースURL または race_id（12桁）を入力",
    placeholder="例：https://race.netkeiba.com/race/shutuba.html?race_id=202507050211",
)
go = st.button("このレースを読み込む")

race_df = None
race_meta = None

if go and race_input:
    race_id = parse_race_id(race_input)
    if not race_id:
        st.error("race_id を認識できませんでした。URL または 12桁のIDを入力してください。")
    else:
        with st.spinner("出馬表を取得中…"):
            df, meta = fetch_shutuba(race_id)
        if df is None:
            st.error("出馬表の取得に失敗しました。ページ構造または race_id を確認してください。")
        else:
            race_df, race_meta = df, meta
            st.success("出馬表の取得に成功しました ✅")

            # レース概要ボックス
            st.markdown("#### レース概要")
            col_a, col_b = st.columns([3, 2])
            with col_a:
                st.write(f"**レース名**：{meta.get('race_name', '')}")
                st.write(f"**情報**：{meta.get('race_info', '')}")
            with col_b:
                surface = meta.get("surface", "")
                distance = meta.get("distance", None)
                direction = meta.get("direction", "")
                num_horses = meta.get("num_horses", 0)

                if surface and distance:
                    st.write(f"**コース**：{surface} {distance}m {f'({direction})' if direction else ''}")
                elif surface:
                    st.write(f"**コース**：{surface} {f'({direction})' if direction else ''}")

                if num_horses:
                    st.write(f"**頭数**：{num_horses}頭")

                st.write(f"[netkeiba で開く]({meta.get('url', '')})")


# ======================
# タブ群
# ======================
if race_df is not None:

    # ベーススコア（年齢＋空枠）
    base_score_df = build_base_score_df(race_df, race_meta)

    st.markdown("---")
    st.markdown("### 2. 出馬表・スコア・馬券")

    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    # --------------------------------------------------
    # 出馬表タブ
    # --------------------------------------------------
    with tab_ma:
        st.markdown("#### 出馬表（印入力）")

        # 合計スコア（手動は session_state から復元）
        tmp_sc = base_score_df.copy()
        manual_list = []
        for _, row in tmp_sc.iterrows():
            key = f"manual_{row['馬名']}"
            val = st.session_state.get(key, 0)
            manual_list.append(val)
        tmp_sc["手動"] = manual_list

        base_cols = [
            "年齢", "血統", "騎手スコア", "馬主", "生産者",
            "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"
        ]
        tmp_sc["合計"] = tmp_sc[base_cols].sum(axis=1) + tmp_sc["手動"]
        tmp_sc = tmp_sc.sort_values("合計", ascending=False).reset_index(drop=True)
        tmp_sc["スコア順"] = tmp_sc.index + 1

        ma_df = race_df.merge(tmp_sc[["馬名", "合計", "スコア順"]], on="馬名", how="left")
        ma_df = ma_df.sort_values("スコア順").reset_index(drop=True)

        # 印入力（馬名ベースの key にして衝突防止）
        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]
        mark_list = []
        for _, row in ma_df.iterrows():
            key = f"mark_{row['馬名']}"
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 印",
                marks,
                key=key,
            )
            mark_list.append(val)
        ma_df["印"] = mark_list

        # 出馬表表示
        ma_display = ma_df[
            ["枠", "馬番", "馬名", "性齢", "斤量", "前走体重",
             "騎手", "オッズ", "人気", "合計", "スコア順", "印"]
        ]
        st.dataframe(ma_display, use_container_width=True)

    # --------------------------------------------------
    # スコアタブ
    # --------------------------------------------------
    with tab_sc:
        st.markdown("#### スコア（手動補正あり）")

        sc_df = base_score_df.copy()

        # 手動スコア入力（ここで初めてウィジェットを作る）
        manual_vals = []
        for _, row in sc_df.iterrows():
            key = f"manual_{row['馬名']}"
            # selectbox の選択値は Streamlit 側が自動で保持してくれる
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 手動スコア",
                [-3, -2, -1, 0, 1, 2, 3],
                key=key,
            )
            manual_vals.append(val)
        sc_df["手動"] = manual_vals

        base_cols = [
            "年齢", "血統", "騎手スコア", "馬主", "生産者",
            "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"
        ]
        sc_df["合計"] = sc_df[base_cols].sum(axis=1) + sc_df["手動"]
        sc_df = sc_df.sort_values("合計", ascending=False).reset_index(drop=True)

        sc_display = sc_df[
            ["馬名", "合計", "年齢", "血統", "騎手スコア", "馬主",
             "生産者", "調教師", "成績", "競馬場", "距離",
             "脚質", "枠スコア", "馬場", "手動"]
        ]
        st.dataframe(sc_display, use_container_width=True)

    # --------------------------------------------------
    # AIスコアタブ（現状は合計スコアのコピー）
    # --------------------------------------------------
    with tab_ai:
        st.markdown("#### AIスコア（暫定）")

        # SCタブと同じ計算を再利用
        ai_df = sc_df[["馬名", "合計"]].copy()
        ai_df.rename(columns={"合計": "AIスコア"}, inplace=True)
        st.dataframe(ai_df.sort_values("AIスコア", ascending=False), use_container_width=True)

    # --------------------------------------------------
    # 馬券タブ
    # --------------------------------------------------
    with tab_be:
        st.markdown("#### 馬券配分")

        col1, col2 = st.columns(2)
        with col1:
            total_budget = st.number_input("総投資額（円）", 100, 1_000_000, 1000, 100)
        with col2:
            target_mult = st.slider("希望払い戻し倍率", 1.0, 10.0, 1.5, 0.5)

        st.write("チェックした馬すべてで、ほぼ同じ払い戻し額になるように自動配分します。")

        bet_df = ma_df[["馬名", "オッズ"]].copy()
        bet_df["購入"] = False

        edited = st.data_editor(bet_df, num_rows="fixed", use_container_width=True)

        if st.button("自動配分を計算"):
            if edited["購入"].sum() == 0:
                st.warning("少なくとも1頭は『購入』にチェックを入れてください。")
            else:
                alloc_df, info = allocate_bets(edited, total_budget, target_mult, loss_tolerance=0.1)

                st.subheader("推奨配分結果")
                st.dataframe(alloc_df, use_container_width=True)

                st.write(f"- 目標払い戻し額: {info['目標払い戻し額']:.0f} 円")
                st.write(f"- 許容下限（-10%）: {info['許容下限']:.0f} 円")
                st.write(f"- 必要合計金額: {info['必要合計金額']} 円")
                st.write(f"- 残り予算: {info['残り予算']} 円")

                if info["必要合計金額"] > total_budget:
                    st.error("総投資額が不足しています。投資額を増やすか、倍率を下げるか、点数を絞ってください。")
                else:
                    st.success("この配分なら、どれか1点的中でほぼ目標払い戻し以上を確保できます。")

    # --------------------------------------------------
    # 基本情報タブ
    # --------------------------------------------------
    with tab_pr:
        st.markdown("#### 基本情報")

        pr_display = race_df[
            ["枠", "馬番", "馬名", "性齢", "斤量", "前走体重", "騎手", "オッズ", "人気"]
        ]
        st.dataframe(pr_display, use_container_width=True)

else:
    st.info("上の欄に URL または race_id を入力して、「このレースを読み込む」を押してください。")
