import re
import math
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

# ======================
# ページ基本設定 & テーマ
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
st.markdown('<div class="keiba-subtitle">netkeiba レースURLから出馬表・スコア・馬券配分まで一括サポート</div>', unsafe_allow_html=True)
st.markdown("---")


# ======================
# ユーティリティ
# ======================
def parse_race_id(text: str):
    """
    URLまたは race_id を受け取って 12桁の race_id を返す
    """
    text = text.strip()
    if re.fullmatch(r"\d{12}", text):
        return text
    m = re.search(r"race_id=(\d{12})", text)
    if m:
        return m.group(1)
    # sp 版URLなど、末尾に数字12桁がある場合にも対応
    m2 = re.search(r"(\d{12})", text)
    if m2:
        return m2.group(1)
    return None


def fetch_shutuba(race_id: str):
    """
    PC版 出馬表ページから基本情報を取得
    """
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, None
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")

    # レース概要
    race_name = ""
    race_info = ""
    name_el = soup.select_one(".RaceName")
    if name_el:
        race_name = name_el.get_text(strip=True)
    info_el = soup.select_one(".RaceData01")
    if info_el:
        race_info = info_el.get_text(" ", strip=True)

    # コース種別（芝/ダ）と距離をざっくり抽出
    surface = "不明"
    distance = None
    if "芝" in race_info:
        surface = "芝"
    elif "ダ" in race_info or "ダート" in race_info:
        surface = "ダート"
    m_dist = re.search(r"(\d+)m", race_info)
    if m_dist:
        distance = int(m_dist.group(1))

    # 出馬表テーブル
    table = soup.select_one("table.RaceTable01")
    if table is None:
        return None, {"race_name": race_name, "race_info": race_info, "surface": surface, "distance": distance}

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
    # オッズ・人気は数値化（失敗したらNaN）
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
# スコアリング
# ======================
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


def build_score_df(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """
    SCタブ用スコアテーブルを作成
    今は「年齢スコア + 手動」を基本にして合計スコアを作る。
    他の項目は枠だけ用意してあとから拡張しやすくしておく。
    """
    surface = meta.get("surface", "不明")

    sc = df.copy()
    sc["年齢"] = sc["性齢"].fillna("").apply(lambda x: score_age(x, surface))
    # 他のスコア項目は0で初期化（あとから拡張）
    sc["血統"] = 0.0
    sc["騎手スコア"] = 0.0
    sc["馬主"] = 0.0
    sc["生産者"] = 0.0
    sc["調教師"] = 0.0
    sc["成績"] = 0.0
    sc["競馬場"] = 0.0
    sc["距離"] = 0.0
    sc["脚質"] = 0.0
    sc["枠スコア"] = 0.0
    sc["馬場"] = 0.0

    # 手動スコアは session_state から読み書き
    manual_scores = []
    for i, row in sc.iterrows():
        key = f"manual_score_{i}"
        if key not in st.session_state:
            st.session_state[key] = 0
        manual_scores.append(st.session_state[key])
    sc["手動"] = manual_scores

    # 合計 = 各スコアの単純合算（今は年齢だけ有効で、他は0 + 手動）
    base_cols = ["年齢", "血統", "騎手スコア", "馬主", "生産者", "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]
    sc["合計"] = sc[base_cols].sum(axis=1) + sc["手動"]

    return sc


# ======================
# 馬券 自動配分ロジック
# ======================
def allocate_bets(bets_df: pd.DataFrame, total_budget: int, target_multiplier: float, loss_tolerance: float = 0.1):
    """
    bets_df: columns=["馬名","オッズ","購入"]（購入=True の行だけ対象）
    total_budget: 総投資額
    target_multiplier: 希望払い戻し倍率（例:1.5）
    loss_tolerance: 目標払い戻しに対してどこまで下回りOKか（0.1 = -10%まで）

    目標払い戻し額 P = total_budget * target_multiplier
    各馬券について、「当たったときに >= P*(1-loss_tolerance)」となる最小金額(100円単位)を計算。
    """
    P = total_budget * target_multiplier
    threshold = P * (1 - loss_tolerance)

    result_rows = []
    needed_total = 0

    selected = bets_df[bets_df["購入"] & bets_df["オッズ"].notna()].copy()
    for _, row in selected.iterrows():
        odds = float(row["オッズ"])
        if odds <= 0:
            stake = 0
        else:
            raw = threshold / odds
            stake = int(math.ceil(raw / 100.0) * 100)  # 100円単位切り上げ

        needed_total += stake
        payout = stake * odds
        result_rows.append(
            {
                "馬名": row["馬名"],
                "オッズ": odds,
                "推奨金額": stake,
                "想定払い戻し": payout,
            }
        )

    result_df = pd.DataFrame(result_rows)

    info = {
        "目標払い戻し額": P,
        "許容下限": threshold,
        "必要合計金額": needed_total,
        "残り予算": total_budget - needed_total,
    }
    return result_df, info


# ======================
# 上部：レースURL / race_id 入力
# ======================
st.markdown("### 1. レース指定")

col_url, col_dummy = st.columns([3, 1])

with col_url:
    race_input = st.text_input(
        "netkeiba のレースURL または race_id（12桁）を入力",
        placeholder="例）https://race.netkeiba.com/race/shutuba.html?race_id=202507050211",
    )

go = st.button("このレースを読み込む")

race_df = None
race_meta = None

if go and race_input.strip():
    race_id = parse_race_id(race_input)
    if not race_id:
        st.error("race_id を認識できませんでした。URLまたは12桁のIDを入力してください。")
    else:
        with st.spinner("出馬表を取得中..."):
            df, meta = fetch_shutuba(race_id)
        if df is None or df.empty:
            st.error("出馬表の取得に失敗しました。レースIDやページ構造を確認してください。")
        else:
            race_df = df
            race_meta = meta

            st.success("出馬表の取得に成功しました ✅")
            st.write(f"**レース名**: {meta.get('race_name','')}  ")
            st.write(f"**概要**: {meta.get('race_info','')}  ")
            st.write(f"**URL**: {meta.get('url','')}")


# ======================
# レースデータがあるときだけタブ表示
# ======================
if race_df is not None:

    st.markdown("---")
    st.markdown("### 2. 分析タブ")

    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(["出馬表", "スコア", "AIスコア", "馬券", "基本情報"])

    # ---------- スコア計算 ----------
    score_df = build_score_df(race_df, race_meta)
    # 合計スコア順のランク
    score_df = score_df.sort_values("合計", ascending=False).reset_index(drop=True)
    score_df["スコア順"] = score_df.index + 1

    # MA用に結合
    ma_df = race_df.merge(score_df[["馬名", "合計", "スコア順"]], on="馬名", how="left")
    ma_df = ma_df.sort_values("スコア順").reset_index(drop=True)

    # ---------------- 出馬表タブ ----------------
    with tab_ma:
        st.markdown("#### 出馬表（スコア順 + 印）")

        # 印プルダウン
        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]
        mark_values = []
        for i, row in ma_df.iterrows():
            key = f"mark_{i}"
            if key not in st.session_state:
                st.session_state[key] = ""
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} の印",
                marks,
                index=marks.index(st.session_state[key]) if st.session_state[key] in marks else 0,
                key=key,
            )
            st.session_state[key] = val
            mark_values.append(val)
        ma_df["印"] = mark_values

        display_cols = ["枠", "馬番", "馬名", "性齢", "斤量", "前走体重", "騎手", "オッズ", "人気", "合計", "スコア順", "印"]
        st.dataframe(ma_df[display_cols], use_container_width=True)

        st.caption("※オッズ10倍以下やスコア上位6頭は、今後太字や色付けなどでハイライト予定。")

    # ---------------- スコアタブ ----------------
    with tab_sc:
        st.markdown("#### スコア詳細（手動補正あり）")

        # 手動スコア入力UI（ここで session_state を更新してもう一度合計計算してもOK）
        new_manuals = []
        for i, row in score_df.iterrows():
            key = f"manual_score_{i}"
            current = st.session_state.get(key, 0)
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 手動スコア",
                options=[-3, -2, -1, 0, 1, 2, 3],
                index=[-3, -2, -1, 0, 1, 2, 3].index(current),
                key=key,
            )
            st.session_state[key] = val
            new_manuals.append(val)

        score_df["手動"] = new_manuals
        base_cols = ["年齢", "血統", "騎手スコア", "馬主", "生産者", "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]
        score_df["合計"] = score_df[base_cols].sum(axis=1) + score_df["手動"]

        # 再ソート
        score_df = score_df.sort_values("合計", ascending=False).reset_index(drop=True)

        sc_display = score_df[
            ["馬名", "合計", "年齢", "血統", "騎手スコア", "馬主", "生産者", "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場", "手動"]
        ]
        st.dataframe(sc_display, use_container_width=True)
        st.caption("※今は年齢スコア＋手動のみ有効。他項目は枠だけ用意してあり、あとから精密ロジックを追加予定。")

    # ---------------- AIスコアタブ ----------------
    with tab_ai:
        st.markdown("#### AIスコア（枠だけ）")
        st.write("※現時点では SCタブの合計スコアと同じ値を表示。将来的に別ロジックのAIスコアを追加予定。")

        ai_df = score_df[["馬名", "合計"]].copy()
        ai_df.rename(columns={"合計": "AIスコア"}, inplace=True)
        st.dataframe(ai_df.sort_values("AIスコア", ascending=False), use_container_width=True)

    # ---------------- 馬券タブ ----------------
    with tab_be:
        st.markdown("#### 馬券配分")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            total_budget = st.number_input("総投資額（円）", min_value=100, max_value=1000000, value=1000, step=100)
        with col_b2:
            target_mult = st.slider("希望払い戻し倍率", min_value=1.0, max_value=10.0, value=1.5, step=0.5)

        st.write("チェックした馬券（今は単純に各馬の“1点”想定）に対して、自動で金額配分します。")

        # 購入フラグ
        bet_df = ma_df[["馬名", "オッズ"]].copy()
        bet_df["購入"] = False

        edited = st.data_editor(bet_df, num_rows="fixed", use_container_width=True)

        if st.button("自動配分を計算"):
            if edited["購入"].sum() == 0:
                st.warning("少なくとも1頭は購入にチェックしてください。")
            else:
                alloc_df, info = allocate_bets(edited, total_budget, target_mult, loss_tolerance=0.1)
                st.subheader("推奨配分結果")
                st.dataframe(alloc_df, use_container_width=True)

                st.write(f"- 目標払い戻し額: **{int(info['目標払い戻し額'])}円**")
                st.write(f"- 下限（-10%許容）: **{int(info['許容下限'])}円**")
                st.write(f"- 必要合計金額: **{int(info['必要合計金額'])}円**")
                st.write(f"- 残り予算: **{int(info['残り予算'])}円**")

                if info["必要合計金額"] > total_budget:
                    st.error("💡 現在の総投資額では、全ての馬券で目標払い戻しを達成できません。")
                    st.write("・総投資額を増やすか、")
                    st.write("・希望払い戻し倍率を下げるか、")
                    st.write("・購入する点数（チェックする馬）を減らしてください。")
                else:
                    st.success("この配分なら、どれか1点的中で少なくとも下限払い戻しを確保できます。")

    # ---------------- 基本情報タブ ----------------
    with tab_pr:
        st.markdown("#### 基本情報（PR）")
        st.write("※今は出馬表の基本情報のみ表示。馬主・生産者・調教師などは今後追加予定。")
        pr_cols = ["枠", "馬番", "馬名", "性齢", "斤量", "前走体重", "騎手", "オッズ", "人気"]
        st.dataframe(race_df[pr_cols], use_container_width=True)

else:
    st.info("上の入力欄に netkeiba のレースURL または race_id を入力して「このレースを読み込む」を押してください。")
