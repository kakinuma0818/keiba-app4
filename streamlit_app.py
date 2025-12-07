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
st.markdown('<div class="keiba-subtitle">出馬表 → スコア → 馬券配分まで一括サポート（安定版）</div>', unsafe_allow_html=True)
st.markdown("---")


# ======================
# race_id 抽出
# ======================
def parse_race_id(text: str):
    text = text.strip()
    # 12桁だけ渡されたケース
    if re.fullmatch(r"\d{12}", text):
        return text
    # URLに race_id= があるケース
    m = re.search(r"race_id=(\d{12})", text)
    if m:
        return m.group(1)
    # 末尾12桁だけ拾えるケース
    m2 = re.search(r"(\d{12})", text)
    if m2:
        return m2.group(1)
    return None


# ======================
# 出馬表スクレイピング
# ======================
def fetch_shutuba(race_id: str):
    """
    PC版 https://race.netkeiba.com/race/shutuba.html?race_id=XXXX から
    出馬表とレース概要を取得
    """
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None, None

    # 文字化け対策
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")

    # レース名・概要
    race_name_el = soup.select_one(".RaceName")
    race_name = race_name_el.get_text(strip=True) if race_name_el else ""

    race_info_el = soup.select_one(".RaceData01")
    race_info = race_info_el.get_text(" ", strip=True) if race_info_el else ""

    # コース・距離だけ軽く抜き出し（今後使う用）
    surface = "不明"
    if "芝" in race_info:
        surface = "芝"
    elif "ダ" in race_info or "ダート" in race_info:
        surface = "ダート"

    distance = None
    m_dist = re.search(r"(\d+)m", race_info)
    if m_dist:
        distance = int(m_dist.group(1))

    # 出馬表テーブル（PC版の RaceTable01 を想定）
    table = soup.select_one("table.RaceTable01")
    if table is None:
        # 構造変わっていたときも meta だけ返す
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
    # 数値化できるものだけ数値に
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
# 年齢スコア（仮）
# ======================
def score_age(sexage: str, surface: str) -> float:
    """
    性齢 例: '牡4' '牝3'
    芝: 3〜5歳 3点, 6歳 2点, その他 1点
    ダ: 3〜4歳 3点, 5歳 2点, 6歳 1.5点, その他1点
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
    else:
        if 3 <= age <= 5:
            return 3.0
        elif age == 6:
            return 2.0
        else:
            return 1.0


# ======================
# スコア用テーブル作成（現時点は年齢＋空カラム＋手動）
# ======================
def build_score_base(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    surface = meta.get("surface", "不明")
    sc = df.copy()

    sc["年齢"] = sc["性齢"].fillna("").apply(lambda x: score_age(x, surface))

    # 枠だけ用意（今は全部0、あとで拡張）
    for col in ["血統", "騎手スコア", "馬主", "生産者", "調教師",
                "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]:
        sc[col] = 0.0

    # 手動スコアは 0 でスタート（UI側で編集）
    sc["手動"] = 0.0

    # 合計（初期値）は年齢だけ
    base_cols = ["年齢", "血統", "騎手スコア", "馬主", "生産者",
                 "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]
    sc["合計"] = sc[base_cols].sum(axis=1) + sc["手動"]

    return sc


# ======================
# 1. レース指定
# ======================
st.markdown("### 1. レース指定（URL または race_id）")

race_input = st.text_input(
    "netkeiba レースURL または race_id（12桁）",
    placeholder="例）https://race.netkeiba.com/race/shutuba.html?race_id=202507050211",
)

race_id = None
race_df = None
race_meta = None

if race_input.strip():
    race_id = parse_race_id(race_input)

if race_id:
    with st.spinner("出馬表を取得中..."):
        df, meta = fetch_shutuba(race_id)
    if df is None or df.empty:
        st.error("出馬表の取得に失敗しました。レースIDやページ構造を確認してください。")
        race_id = None
    else:
        race_df = df
        race_meta = meta
        st.success("出馬表取得 OK ✅")
        st.write(f"**レース名**: {meta.get('race_name','')}")
        st.write(f"**概要**: {meta.get('race_info','')}")
        st.write(f"[netkeibaで見る]({meta.get('url','')})")

st.markdown("---")

# ======================
# 2. タブ（常に表示）
# ======================
tab_ma, tab_sc, tab_ai, tab_be, tab_pr = st.tabs(
    ["出馬表", "スコア", "AIスコア", "馬券", "基本情報"]
)

# ======================
# 出馬表タブ
# ======================
with tab_ma:
    st.markdown("#### 出馬表（印つき・行ごと選択）")

    if race_df is None:
        st.info("上でレースURL / race_id を入力すると出馬表が表示されます。")
    else:
        # スコアベース作成
        score_base = build_score_base(race_df, race_meta)
        score_base = score_base.sort_values("合計", ascending=False).reset_index(drop=True)
        score_base["スコア順"] = score_base.index + 1

        # 出馬表側にスコアと順番を結合
        ma_df = race_df.merge(
            score_base[["馬名", "合計", "スコア順"]],
            on="馬名",
            how="left",
        ).sort_values("スコア順").reset_index(drop=True)

        # 印を行ごとに selectbox で入力
        marks = ["", "◎", "○", "▲", "△", "⭐︎", "×"]
        mark_list = []
        st.caption("※ 下の表に反映される印を、上のプルダウンで1頭ずつ選択してください。")

        for i, row in ma_df.iterrows():
            val = st.selectbox(
                f"{row['馬番']} {row['馬名']} の印",
                marks,
                key=f"mark_{i}",
            )
            mark_list.append(val)

        ma_df["印"] = mark_list

        st.dataframe(
            ma_df[["枠", "馬番", "馬名", "性齢", "斤量", "前走体重",
                   "騎手", "オッズ", "人気", "合計", "スコア順", "印"]],
            use_container_width=True,
        )

# ======================
# スコアタブ
# ======================
with tab_sc:
    st.markdown("#### スコア（年齢＋手動スコア 仮）")

    if race_df is None:
        st.info("レースを指定するとスコアが表示されます。")
    else:
        base_sc = build_score_base(race_df, race_meta)

        st.caption("※ 手動スコアを編集 → 下で合計とスコア順を再計算します。")

        # 手動だけ編集できるテーブル
        editable_sc = st.data_editor(
            base_sc,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "手動": st.column_config.NumberColumn(
                    "手動",
                    min_value=-3,
                    max_value=3,
                    step=1,
                )
            },
            hide_index=True,
            key="sc_editor",
        )

        # edited 手動を使って合計再計算
        base_cols = ["年齢", "血統", "騎手スコア", "馬主", "生産者",
                     "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場"]
        editable_sc["合計"] = editable_sc[base_cols].sum(axis=1) + editable_sc["手動"]
        editable_sc = editable_sc.sort_values("合計", ascending=False).reset_index(drop=True)
        editable_sc["スコア順"] = editable_sc.index + 1

        st.markdown("##### 合計スコア（再計算後）")
        st.dataframe(
            editable_sc[[
                "馬名", "合計", "スコア順",
                "年齢", "血統", "騎手スコア", "馬主", "生産者",
                "調教師", "成績", "競馬場", "距離", "脚質", "枠スコア", "馬場", "手動"
            ]],
            use_container_width=True,
        )

# ======================
# AIスコアタブ（仮）
# ======================
with tab_ai:
    st.markdown("#### AIスコア（仮置き）")
    if race_df is None:
        st.info("レースを指定するとAIスコア枠が使えるようになります（ロジックは今後実装）。")
    else:
        base_sc = build_score_base(race_df, race_meta)
        ai_df = base_sc[["馬名", "合計"]].copy()
        ai_df.rename(columns={"合計": "AIスコア"}, inplace=True)
        ai_df = ai_df.sort_values("AIスコア", ascending=False).reset_index(drop=True)
        st.dataframe(ai_df, use_container_width=True)
        st.caption("※ 現時点では SCタブ合計と同じ値です。今後、別ロジックに差し替えます。")

# ======================
# 馬券タブ（超仮）
# ======================
with tab_be:
    st.markdown("#### 馬券（超仮実装）")
    if race_df is None:
        st.info("レースを指定すると、ここに馬券配分UIを作り込んでいきます。")
    else:
        st.write("・総投資額、希望払い戻し倍率、馬券の種類などをここに実装予定。")
        st.write("・今は仕様確認用の仮置きです。")

# ======================
# 基本情報タブ（仮）
# ======================
with tab_pr:
    st.markdown("#### 基本情報（仮）")
    if race_df is None:
        st.info("レースを指定すると出走馬の基本情報がここに表示されます。")
    else:
        st.dataframe(
            race_df[["枠", "馬番", "馬名", "性齢", "斤量", "前走体重", "騎手", "オッズ", "人気"]],
            use_container_width=True,
        )
