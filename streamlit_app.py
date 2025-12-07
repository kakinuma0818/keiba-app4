import re
import math
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

# ======================
# 初期化（セッション）
# ======================
if "race_df" not in st.session_state:
    st.session_state["race_df"] = None
    st.session_state["race_meta"] = None
    st.session_state["marks"] = {}           # 馬ごとの印 {馬番(str): "◎" など}
    st.session_state["manual_scores"] = {}   # 馬ごとの手動スコア {馬番(str): int}


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
st.markdown(
    '<div class="keiba-subtitle">出馬表 → スコア → 馬券配分まで一括サポート（netkeiba 連携）</div>',
    unsafe_allow_html=True,
)
st.markdown("---")


# ======================
# race_id 抽出
# ======================
def parse_race_id(text: str):
    """
    URL または 12桁の race_id から race_id を取り出す
    """
    if not text:
        return None
    text = text.strip()

    # 「12桁だけ」の場合
    if re.fullmatch(r"\d{12}", text):
        return text

    # URLパラメータから
    m = re.search(r"race_id=(\d{12})", text)
    if m:
        return m.group(1)

    # URL末尾に12桁がある場合
    m2 = re.search(r"(\d{12})", text)
    if m2:
        return m2.group(1)

    return None


# ======================
# 出馬表スクレイピング
# ======================
def fetch_shutuba(race_id: str):
    """
    netkeiba PC版 出馬表ページから
    ・レース名 / 概要 / 頭数（あれば）
    ・出馬表（枠, 馬番, 馬名, 性齢, 斤量, 前走体重, 騎手, オッズ, 人気）
    を取得する
    """
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

    # レース情報（距離・クラス・頭数などまとまってるところ）
    race_info_el = soup.select_one(".RaceData01")
    race_info_raw = race_info_el.get_text(" ", strip=True) if race_info_el else ""

    # 頭数（「18頭」みたいなの）
    num_runners = None
    m_head = re.search(r"(\d+)頭", race_info_raw)
    if m_head:
        num_runners = int(m_head.group(1))

    # 表示用 race_info（既に「頭」が含まれていなければ補完）
    if num_runners is not None and "頭" not in race_info_raw:
        race_info = f"{race_info_raw} / {num_runners}頭"
    else:
        race_info = race_info_raw

    # コース種別と距離
    surface = "不明"
    distance = None
    if "芝" in race_info_raw:
        surface = "芝"
    elif "ダ" in race_info_raw or "ダート" in race_info_raw:
        surface = "ダート"
    m_dist = re.search(r"(\d+)m", race_info_raw)
    if m_dist:
        distance = int(m_dist.group(1))

    # 出馬表テーブル
    table = soup.select_one("table.RaceTable01")
    if table is None:
        meta = {
            "race_name": race_name,
            "race_info": race_info,
            "surface": surface,
            "distance": distance,
            "num_runners": num_runners,
            "url": url,
        }
        return None, meta

    header_row = table.find("tr")
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    def idx(contain_str: str):
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
    # 数値化
    df["オッズ"] = pd.to_numeric(df["オッズ"], errors="coerce")
    df["人気"] = pd.to_numeric(df["人気"], errors="coerce")

    meta = {
        "race_name": race_name,
        "race_info": race_info,
        "surface": surface,
        "distance": distance,
        "num_runners": num_runners,
        "url": url,
    }
    return df, meta


# ======================
# 年齢スコア
# ======================
def score_age(sexage: str, surface: str) -> float:
    """
    性齢(例: 牡4, 牝3) と 芝/ダートから年齢スコア
    芝: 3〜5歳=3, 6歳=2, 7歳以上=1
    ダ: 3〜4歳=3, 5歳=2, 6歳=1.5, 7歳以上=1
    """
    m = re.search(r"(\d+)", sexage or "")
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
# スコアテーブル生成
# ======================
def build_score_df(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """
    ・年齢スコア
    ・手動スコア（session_state["manual_scores"]）
    を合算して「合計」を作る。
    その他の項目（血統〜馬場）は今は 0 で枠だけ確保。
    """
    surface = (meta or {}).get("surface", "不明")

    sc = df.copy()
    sc["年齢"] = sc["性齢"].fillna("").apply(lambda x: score_age(x, surface))

    # 他項目は今は 0（ロジック追加用の枠）
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

    # 手動スコア：馬番ベースで session_state から取得
    manual_scores = st.session_state.get("manual_scores", {})
    sc["手動"] = sc["馬番"].astype(str).map(lambda b: manual_scores.get(b, 0)).fillna(0).astype(float)

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
def allocate_bets(bets_df: pd.DataFrame, total_budget: int, target_multiplier: float, loss_tolerance: float = 0.1):
    """
    bets_df: ["馬名","オッズ","購入"] を含む DataFrame
    total_budget: 総投資額
    target_multiplier: 希望払い戻し倍率（例:1.5）
    loss_tolerance: 目標払い戻しに対してどこまで下回りOKか（0.1 = -10%）

    目標払い戻し額 P = total_budget * target_multiplier
    各馬券について、「当たったときに >= P*(1-loss_tolerance)」となる最小金額(100円単位)を計算。
    """
    P = total_budget * target_multiplier
    threshold = P * (1 - loss_tolerance)

    results = []
    needed = 0

    selected = bets_df[bets_df["購入"] & bets_df["オッズ"].notna()].copy()
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

    alloc_df = pd.DataFrame(results)
    info = {
        "目標払い戻し額": P,
        "許容下限": threshold,
        "必要合計金額": needed,
        "残り予算": total_budget - needed,
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

col_go1, col_go2 = st.columns([1, 3])
with col_go1:
    go = st.button("このレースを読み込む")

if go and race_input:
    race_id = parse_race_id(race_input)
    if not race_id:
        st.error("race_id を認識できませんでした。URL または 12桁の数字を入力してください。")
    else:
        with st.spinner("出馬表を取得中..."):
            df, meta = fetch_shutuba(race_id)
        if df is None or df.empty:
            st.error("出馬表の取得に失敗しました。レースIDやページ構造を確認してください。")
        else:
            st.session_state["race_df"] = df
            st.session_state["race_meta"] = meta
            # 新しいレースを読んだときは印・手動スコアをリセット
            st.session_state["marks"] = {}
            st.session_state["manual_scores"] = {}
            st.success("出馬表の取得に成功しました ✅")

# 現在のレースデータ
race_df = st.session_state["race_df"]
race_meta = st.session_state["race_meta"]

if race_df is not None and race_meta is not None:
    st.markdown("### 2. レース概要")

    race_name = race_meta.get("race_name", "")
    race_info = race_meta.get("race_info", "")
    num_runners = race_meta.get("num_runners", None)
    url = race_meta.get("url", "")

    st.write(f"**レース名**：{race_name}")
    if num_runners is not None and "頭" not in race_info:
        st.write(f"**情報**：{race_info} / {num_runners}頭")
    else:
        st.write(f"**情報**：{race_info}")
    if url:
        st.write(f"[netkeibaページを開く]({url})")

    st.markdown("---")

    # ======================
    # 3. タブ定義
    # ======================
    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    # まず現時点のスコアを一度計算（手動スコアは session_state から）
    score_df_base = build_score_df(race_df, race_meta)
    score_df_base = score_df_base.sort_values("合計", ascending=False).reset_index(drop=True)
    score_df_base["スコア順"] = score_df_base.index + 1

    # 出馬表にスコアを結合
    ma_df_base = race_df.merge(
        score_df_base[["馬名", "合計", "スコア順"]],
        on="馬名",
        how="left",
    )
    ma_df_base = ma_df_base.sort_values("スコア順").reset_index(drop=True)

    # ----------------------
    # 出馬表タブ
    # ----------------------
    with tab_ma:
        st.markdown("#### 出馬表（スコア順＋印）")

        marks_session = st.session_state.get("marks", {})
        marks_options = ["", "◎", "○", "▲", "△", "⭐︎", "×"]

        # 印入力UI（馬ごとに1行ずつ）
        new_marks = {}
        for _, row in ma_df_base.iterrows():
            horse_key = str(row["馬番"])
            default_val = marks_session.get(horse_key, "")
            try:
                default_index = marks_options.index(default_val)
            except ValueError:
                default_index = 0

            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} の印",
                marks_options,
                index=default_index,
                key=f"mark_select_{horse_key}",
            )
            new_marks[horse_key] = val

        # 更新された印を保存
        st.session_state["marks"] = new_marks

        # データフレームに印を反映
        ma_df = ma_df_base.copy()
        ma_df["印"] = ma_df["馬番"].astype(str).map(new_marks).fillna("")

        # 表示カラム（順番）
        ma_display_cols = [
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
        st.dataframe(ma_df[ma_display_cols], width="stretch")
        st.caption("※スコア順で並び替え。オッズ順や人気順での並び替えは列ヘッダーから可能。")

    # ----------------------
    # スコアタブ
    # ----------------------
    with tab_sc:
        st.markdown("#### スコア詳細（手動補正つき）")

        manual_session = st.session_state.get("manual_scores", {})
        new_manual = {}

        # 手動スコア入力（-3〜+3）
        for _, row in race_df.iterrows():
            horse_key = str(row["馬番"])
            default_val = int(manual_session.get(horse_key, 0))
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} 手動スコア",
                options=[-3, -2, -1, 0, 1, 2, 3],
                index=[-3, -2, -1, 0, 1, 2, 3].index(default_val) if default_val in [-3, -2, -1, 0, 1, 2, 3] else 3,
                key=f"manual_select_{horse_key}",
            )
            new_manual[horse_key] = int(val)

        # 手動スコアを session_state に保存
        st.session_state["manual_scores"] = new_manual

        # 手動込みで再計算したスコアテーブル
        score_df = build_score_df(race_df, race_meta)
        score_df = score_df.sort_values("合計", ascending=False).reset_index(drop=True)
        score_df["スコア順"] = score_df.index + 1

        sc_display_cols = [
            "馬名",
            "合計",
            "スコア順",
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
        st.dataframe(score_df[sc_display_cols], width="stretch")
        st.caption("※今は「年齢＋手動」のみ有効。他項目はロジック追加用の枠として0点。")

    # ----------------------
    # AIスコアタブ（仮）
    # ----------------------
    with tab_ai:
        st.markdown("#### AIスコア（仮実装）")
        # 現時点では合計スコアのコピー
        ai_df = score_df[["馬名", "合計", "スコア順"]].copy()
        ai_df.rename(columns={"合計": "AIスコア"}, inplace=True)
        st.dataframe(ai_df.sort_values("AIスコア", ascending=False), width="stretch")
        st.caption("※将来的に別ロジック（ラップ・脚質・血統など）でAIスコアを算出予定。")

    # ----------------------
    # 馬券タブ
    # ----------------------
    with tab_be:
        st.markdown("#### 馬券配分（希望払い戻し倍率ベース）")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            total_budget = st.number_input("総投資額（円）", min_value=100, max_value=1_000_000, value=1000, step=100)
        with col_b2:
            target_mult = st.slider("希望払い戻し倍率", min_value=1.0, max_value=10.0, value=1.5, step=0.5)

        st.write("チェックした行を「1点」とみなし、どの点が当たってもほぼ同じ払い戻しになるよう自動配分します。")
        st.write("（単勝・複勝・馬連・3連複など、券種は問わず「1点＝1行」としてオッズを入れればOK）")

        bet_df = ma_df_base[["馬番", "馬名", "オッズ", "人気"]].copy()
        bet_df["購入"] = False

        edited = st.data_editor(bet_df, num_rows="fixed", width="stretch")

        if st.button("自動配分を計算"):
            if edited["購入"].sum() == 0:
                st.warning("少なくとも1点は購入にチェックしてください。")
            else:
                alloc_df, info = allocate_bets(edited, total_budget, target_mult, loss_tolerance=0.1)

                st.subheader("推奨配分結果")
                st.dataframe(alloc_df, width="stretch")

                st.write(f"- 目標払い戻し額: **{int(info['目標払い戻し額'])} 円**")
                st.write(f"- 下限（-10%許容）: **{int(info['許容下限'])} 円**")
                st.write(f"- 必要合計金額: **{int(info['必要合計金額'])} 円**")
                st.write(f"- 残り予算: **{int(info['残り予算'])} 円**")

                if info["必要合計金額"] > total_budget:
                    st.error("💡 現在の総投資額では、全ての点で目標払い戻しを達成できません。")
                    st.write("・総投資額を増やすか、")
                    st.write("・希望払い戻し倍率を下げるか、")
                    st.write("・購入する点数（チェックする行）を減らしてください。")
                else:
                    st.success("この配分なら、どれか1点的中で少なくとも下限払い戻しを確保できます。")

    # ----------------------
    # 基本情報タブ
    # ----------------------
    with tab_pr:
        st.markdown("#### 基本情報")
        pr_cols = ["枠", "馬番", "馬名", "性齢", "斤量", "前走体重", "騎手", "オッズ", "人気"]
        st.dataframe(race_df[pr_cols], width="stretch")
        st.caption("※今後ここに馬主・生産者・調教師などの情報も追加予定。")

else:
    st.info("上の入力欄に netkeiba のレースURL または race_id を入力して「このレースを読み込む」を押してください。")
