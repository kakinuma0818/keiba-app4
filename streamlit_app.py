import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime

st.set_page_config(page_title="KEIBA APP", layout="wide")

st.title("🏇 KEIBA APP（自動出馬表）")


# -----------------------------
# 競馬場コード変換
# -----------------------------
COURSE_MAP = {
    "札幌": "01",
    "函館": "02",
    "福島": "03",
    "新潟": "04",
    "東京": "05",
    "中山": "06",
    "中京": "07",
    "京都": "08",
    "阪神": "09",
    "小倉": "10",
}


# -----------------------------
# レースID生成（例：202507050211）
# -----------------------------
def generate_race_id(date, course_name, race_num):
    course_code = COURSE_MAP[course_name]
    date_str = date.strftime("%Y%m%d")
    race_num_str = str(race_num).zfill(2)

    # 例：2025/07/05 東京11R → 202507050511
    return f"{date_str}{course_code}{race_num_str}"


# -----------------------------
# 出馬表取得（文字化け対応済）
# -----------------------------
def get_shutuba_table(race_id):

    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"

    response = requests.get(url)
    response.encoding = response.apparent_encoding  # ← これが文字化け修正の核心

    soup = BeautifulSoup(response.text, "html.parser")

    # 出馬表テーブル
    table = soup.select_one("table.RaceTable01")
    if table is None:
        return None

    rows = table.select("tr")

    data = []
    for row in rows[1:]:
        cols = [col.get_text(strip=True) for col in row.select("td")]
        if cols:
            data.append(cols)

    # 列名（netkeibaの列構成に合わせる）
    columns = [
        "枠", "馬番", "馬名", "性齢", "斤量",
        "騎手", "厩舎", "馬体重", "オッズ", "人気"
    ]

    # 列が多い/少ない対応
    df = pd.DataFrame(data)
    df = df.iloc[:, :len(columns)]
    df.columns = columns[: df.shape[1]]

    return df



# -----------------------------
# UI（競馬場・日付・レース番号）
# -----------------------------
st.subheader("🔧 レース選択")

col1, col2, col3 = st.columns(3)

with col1:
    date = st.date_input("日付を選択", datetime.today())

with col2:
    course = st.selectbox("競馬場", list(COURSE_MAP.keys()))

with col3:
    race_num = st.number_input("レース番号（1〜12）", 1, 12, 11)


# -----------------------------
# 実行
# -----------------------------
if st.button("出馬表を取得する"):

    race_id = generate_race_id(date, course, race_num)
    st.write(f"レースID: `{race_id}`")

    df = get_shutuba_table(race_id)

    if df is None:
        st.error("レースページが見つかりませんでした。開催日が違う可能性があります。")
    else:
        st.success("出馬表の取得に成功しました！")
        st.dataframe(df, use_container_width=True)

        st.download_button(
            "📥 CSVとして保存",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"shutuba_{race_id}.csv",
            mime="text/csv"
        )
