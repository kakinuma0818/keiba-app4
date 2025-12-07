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
# 出馬表スクレイピング（文字化け + 頭数）
# ======================
def fetch_shutuba(race_id: str):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, None

    # 文字コード自動判別
    r.encoding = r.apparent_encoding

    soup = BeautifulSoup(r.text, "html.parser")

    race_name_el = soup.select_one(".RaceName")
    race_name = race_name_el.get_text(strip=True) if race_name_el else ""

    race_info_el = soup.select_one(".RaceData01")
    race_info_raw = race_info_el.get_text(" ", strip=True) if race_info_el else ""

    # 芝 / ダート & 距離
    surface = "不明"
    distance = None
    if "芝" in race_info_raw:
        surface = "芝"
    elif "ダ" in race_info_raw:
        surface = "ダート"
    m_dist = re.search(r"(\d+)m", race_info_raw)
    if m_dist:
        distance = int(m_dist.group(1))

    # 出馬表テーブル
    table = soup.select_one("table.RaceTable01")
    if table is None:
        # テーブル取れなかった場合も race 情報だけ返す
        meta = {
            "race_name": race_name,
            "race_info": race_info_raw,
            "surface": surface,
            "distance": distance,
            "headcount": None,
            "url": url,
        }
        return None, meta

    header_row = table.find("tr")
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    def find_col(contain_str):
        for i, h in enumerate(headers):
            if contain_str in h:
                return i
        return None

    idx_waku = find_col("枠")
    idx_umaban = find_col("馬番")
    idx_name = find_col("馬名")
    idx_sexage = find_col("性齢")
    idx_weight = find_col("斤量")
    idx_jockey = find_col("騎手")
    idx_body = find_col("馬体重")
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
                "前走体重": safe(idx_body),
                "騎手": safe(idx_jockey),
                "オッズ": safe(idx_odds),
                "人気": safe(idx_pop),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["オッズ"] = pd.to_numeric(df["オッズ"], errors="coerce")
        df["人気"] = pd.to_numeric(df["人気"], errors="coerce")

    headcount = len(df)
    if race_info_raw:
        race_info = f"{race_info_raw} / {headcount}頭立て"
    else:
        race_info = f"{headcount}頭立て"

    meta = {
        "race_name": race_name,
        "race_info": race_info,
        "surface": surface,
        "distance": distance,
        "headcount": headcount,
        "url": url,
    }
    return df, meta


# ======================
# 年齢スコア（仮ロジック）
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
# ベーススコア DataFrame
# ======================
def build_base_score_df(race_df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    surface = meta.get("surface", "不明")
    sc = race_df.copy()

    sc["年齢"] = sc["性齢"].fillna("").apply(lambda x: score_age(x, surface))

    # ここは今後ロジック拡張予定
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
    sc["ベーススコア"] = sc[base_cols].sum(axis=1)

    return sc


# ======================
# 馬券 自動配分（単勝的な想定）
# ======================
def allocate_bets(bets_df, total_budget, target_multiplier, loss_tolerance=0.1):
    P = total_budget * target_multiplier
    threshold = P * (1 - loss_tolerance)

    results = []
    needed = 0

    selected = bets_df[bets_df["購入"] & bets_df["オッズ"].notna()]
    for _, row in selected.iterrows():
        odds = float(row["オッズ"])
        if odds <= 0:
            continue
        raw = threshold / odds
        stake = int(math.ceil(raw / 100) * 100)

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
# UI：レース入力
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
        if df is None or df.empty:
            st.error("出馬表の取得に失敗しました。")
        else:
            race_df = df
            race_meta = meta

            st.success("出馬表の取得に成功しました ✅")
            st.write(f"**レース名**：{meta.get('race_name', '')}")
            st.write(f"**概要**：{meta.get('race_info', '')}")
            st.write(f"[netkeibaページを開く]({meta.get('url','')})")

# ======================
# タブ表示
# ======================
if race_df is not None and race_meta is not None:
    base_score_df = build_base_score_df(race_df, race_meta)

    st.markdown("---")
    st.markdown("### 2. 解析タブ")

    tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
        ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
    )

    # ========== 出馬表タブ ==========
    with tab_ma:
        st.markdown("#### 出馬表 ＋ 印")

        # 出馬表に印列を追加（初期値は空文字）
        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]

        shutuba_df = race_df.copy()
        if "印" not in shutuba_df.columns:
            shutuba_df["印"] = ""

        # 編集用テーブル
        edited_ma = st.data_editor(
            shutuba_df[
                ["枠", "馬番", "馬名", "性齢", "斤量", "前走体重", "騎手", "オッズ", "人気", "印"]
            ],
            column_config={
                "印": st.column_config.SelectboxColumn(
                    "印",
                    options=marks,
                    required=False,
                    help="各馬の印を選択してください",
                )
            },
            hide_index=True,
            width="stretch",
            key="marks_editor",
        )

        # ここで edited_ma が「印付き出馬表」として完成
        st.markdown("##### 印付き出馬表（確認用）")
        st.dataframe(edited_ma, hide_index=True, width="stretch")

    # ========== スコアタブ ==========
    with tab_sc:
        st.markdown("#### スコア（ベース＋手動調整）")

        score_base = base_score_df.copy()

        # 手動スコア編集用のテーブル（馬番・馬名＋手動）
        edit_target = score_base[["馬番", "馬名"]].copy()
        edit_target["手動"] = 0

        edited_score = st.data_editor(
            edit_target,
            column_config={
                "手動": st.column_config.SelectboxColumn(
                    "手動スコア",
                    options=[-3, -2, -1, 0, 1, 2, 3],
                    required=False,
                    help="直感や追加情報で補正したい場合に使用",
                )
            },
            hide_index=True,
            width="stretch",
            key="score_manual_editor",
        )

        # 手動スコアを反映して合計スコアを計算
        merged = score_base.merge(
            edited_score[["馬番", "手動"]], on="馬番", how="left"
        )
        merged["手動"] = merged["手動"].fillna(0)
        merged["合計"] = merged["ベーススコア"] + merged["手動"]

        merged = merged.sort_values("合計", ascending=False).reset_index(drop=True)
        merged["スコア順"] = merged.index + 1

        st.markdown("##### スコア一覧")
        st.dataframe(
            merged[
                [
                    "スコア順",
                    "馬番",
                    "馬名",
                    "合計",
                    "ベーススコア",
                    "手動",
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
            ],
            hide_index=True,
            width="stretch",
        )

    # ========== AIスコア（仮置き：ベーススコアをそのまま利用） ==========
    with tab_ai:
        st.markdown("#### AIスコア（暫定：ベーススコアをAIスコアとして表示）")

        ai_df = base_score_df[["馬番", "馬名", "ベーススコア"]].rename(
            columns={"ベーススコア": "AIスコア"}
        )
        ai_df = ai_df.sort_values("AIスコア", ascending=False).reset_index(drop=True)
        st.dataframe(ai_df, hide_index=True, width="stretch")

    # ========== 馬券タブ ==========
    with tab_be:
        st.markdown("#### 馬券配分（単勝想定の簡易版）")

        col1, col2 = st.columns(2)
        with col1:
            total_budget = st.number_input("総投資額（円）", 100, 1_000_000, 1000, 100)
        with col2:
            target_mult = st.slider(
                "希望払い戻し倍率（例：1.5倍なら1.5）",
                min_value=1.0,
                max_value=10.0,
                value=1.5,
                step=0.5,
            )

        st.write("チェックした馬すべてが、ほぼ同じ払い戻しになるよう自動で金額を調整します。")

        bet_df = race_df[["馬番", "馬名", "オッズ"]].copy()
        bet_df["購入"] = False

        edited_bet = st.data_editor(
            bet_df,
            hide_index=True,
            width="stretch",
            key="bet_editor",
        )

        if st.button("自動配分を計算する"):
            if edited_bet["購入"].sum() == 0:
                st.warning("少なくとも1頭は『購入』にチェックを入れてください。")
            else:
                alloc, info = allocate_bets(edited_bet, total_budget, target_mult)

                st.markdown("##### 推奨配分")
                if alloc.empty:
                    st.warning("有効なオッズがありませんでした。")
                else:
                    st.dataframe(alloc, hide_index=True, width="stretch")

                st.markdown("##### 概要")
                st.write(f"- 目標払い戻し額：{info['目標払い戻し額']:.0f} 円")
                st.write(f"- 下限（許容）　：{info['許容下限']:.0f} 円")
                st.write(f"- 必要合計　　　：{info['必要合計金額']} 円")
                st.write(f"- 残り予算　　　：{info['残り予算']} 円")

                if info["必要合計金額"] > total_budget:
                    st.error("この設定では予算オーバーです。倍率を下げるか、対象馬を減らしてください。")

    # ========== 基本情報タブ ==========
    with tab_pr:
        st.markdown("#### 基本情報（生データ）")

        st.markdown("##### 出馬表（元データ）")
        st.dataframe(
            race_df[
                ["枠", "馬番", "馬名", "性齢", "斤量", "前走体重", "騎手", "オッズ", "人気"]
            ],
            hide_index=True,
            width="stretch",
        )

        st.markdown("##### レースメタ情報")
        st.json(race_meta)

else:
    st.info("上の入力欄に URL または race_id を入れて『このレースを読み込む』を押してください。")
