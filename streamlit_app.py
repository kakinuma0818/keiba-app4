import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

st.set_page_config(page_title="KEIBA APP", layout="wide")

# ▼ 競馬場リスト
KEIBAJO_LIST = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]


# ---------------------------------------------------------
# ▼ 1) カレンダーから「●回●日」を取得（2025対応）
# ---------------------------------------------------------
def find_kaisaibi_and_day(date_str, keibajo):
    year, month, day = date_str.split("-")
    day_int = int(day)
    cal_url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month}"

    r = requests.get(cal_url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")

    # td を全部見る
    day_cells = soup.select("td")

    for cell in day_cells:
        txt = cell.get_text(strip=True)

        # 「7」「07」が含まれているセルを探す
        if re.match(rf"^{day_int}(\D|$)", txt):
            links = cell.find_all("a")

            for link in links:
                ltxt = link.get_text(strip=True)

                # 「中京4回2日」「中京競馬場4回2日」など対応
                if keibajo in ltxt:
                    m = re.search(r"(\d+)回(\d+)日", ltxt)
                    if m:
                        return int(m.group(1)), int(m.group(2))

    return None, None


# ---------------------------------------------------------
# ▼ 2) 開催日 + 競馬場 + レース番号 → race_id生成
# ---------------------------------------------------------
def build_race_id(date_str, keibajo, race_no):
    year, month, day = date_str.split("-")

    kaisaibi, day_count = find_kaisaibi_and_day(date_str, keibajo)
    if kaisaibi is None:
        return None

    # 競馬場ID
    KEIBAJO_ID = {
        "札幌": 1, "函館": 2, "福島": 3, "新潟": 4,
        "東京": 5, "中山": 6, "中京": 7,
        "京都": 8, "阪神": 9, "小倉": 10
    }

    jyo_id = KEIBAJO_ID.get(keibajo)
    if jyo_id is None:
        return None

    # race_id = YYYYMMDD + 場ID + 回数 + 日 + レース番号（2桁）
    race_id = f"{year}{month}{day}{jyo_id:02d}{kaisaibi}{day_count}{int(race_no):02d}"

    return race_id


# ---------------------------------------------------------
# ▼ 3) 出馬表ページから馬データ取得
# ---------------------------------------------------------
def get_shutsuba_table(race_id):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    table = soup.select_one("table.RaceTable01")
    if table is None:
        return None

    rows = table.select("tr")
    data = []

    for row in rows[1:]:
        cols = row.select("td")
        if not cols:
            continue

        try:
            umaban = cols[0].text.strip()
            uma = cols[3].text.strip()
            sex_age = cols[4].text.strip()
            jockey = cols[6].text.strip()
        except:
            continue

        # ▼ 文字化け対策（半角カナ強制変換）
        uma = bytes(uma, "utf-8").decode("utf-8", "ignore")

        data.append([umaban, uma, sex_age, jockey])

    df = pd.DataFrame(data, columns=["馬番", "馬名", "性齢", "騎手"])
    return df


# ---------------------------------------------------------
# ▼ 画面UI
# ---------------------------------------------------------
st.title("🐎 KEIBA APP - 出馬表 自動取得 β")

st.write("開催日 → 競馬場 → レース番号 を選ぶと自動で race_id を生成して出馬表を取得します。")

# 日付入力
date_str = st.date_input("開催日を選択", format="YYYY-MM-DD")
date_str = str(date_str)

# 競馬場
keibajo = st.selectbox("競馬場を選択", KEIBAJO_LIST)

# レース番号
race_no = st.number_input("レース番号", min_value=1, max_value=12, value=11, step=1)

# 実行ボタン
if st.button("出馬表を取得"):
    with st.spinner("レースIDを生成中…"):

        race_id = build_race_id(date_str, keibajo, race_no)

        if race_id is None:
            st.error("開催情報が取得できませんでした。開催日 or 競馬場の指定に誤りがある可能性があります。")
            st.stop()

        st.success(f"race_id = {race_id}")

    with st.spinner("出馬表を取得中…"):
        df = get_shutsuba_table(race_id)

        if df is None or len(df) == 0:
            st.error("出馬表の取得に失敗しました。")
        else:
            st.dataframe(df, use_container_width=True)
            st.success("出馬表取得成功！")
