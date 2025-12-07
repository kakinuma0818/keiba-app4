import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

# -------------------------
# 競馬場 → コード変換
# -------------------------
KEIBAJO_CODE = {
    "札幌": "01",
    "函館": "02",
    "福島": "03",
    "新潟": "04",
    "東京": "05",
    "中山": "06",
    "中京": "07",
    "京都": "08",
    "阪神": "09",
    "小倉": "10"
}

# -------------------------------------------------------
# 【1】開催カレンダーから開催回・日数を取得
# -------------------------------------------------------
def find_kaisaibi_and_day(date_str, keibajo):
    """
    入力日付と競馬場を元に netkeiba の開催情報を抽出して
    ・開催回(1〜n回)
    ・開催日（開催中の何日目か）
    を返す
    """
    year, month, day = date_str.split("-")
    cal_url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month}"

    r = requests.get(cal_url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")

    # カレンダーの日付セルを探索
    cells = soup.select("td.Calendar_Day")

    target_kaiji = None
    target_day = None

    for cell in cells:
        # 日付マッチ
        if cell.text.strip().startswith(str(int(day))):
            # 同日の開催競馬場一覧取得
            venues = cell.select("div.Calendar_Inner > a")
            for v in venues:
                if keibajo in v.text:
                    # "中京4回2日" のような文字が入っている
                    info = v.text.strip()
                    m = re.search(r"(\d+)回(\d+)日", info)
                    if m:
                        target_kaiji = int(m.group(1))
                        target_day = int(m.group(2))
                        return target_kaiji, target_day

    return None, None

# -------------------------------------------------------
# 【2】race_id を生成する
# -------------------------------------------------------
def generate_race_id(date_str, keibajo, race_no):
    year = date_str.split("-")[0]
    keibajo_code = KEIBAJO_CODE.get(keibajo)

    kaiji, nichime = find_kaisaibi_and_day(date_str, keibajo)

    if kaiji is None:
        return None  # 開催情報が見つからない

    # race_id 仕様：
    #   YYYY + 場所コード + 開催回(2桁) + 日数(2桁) + レース番号(2桁)
    race_id = f"{year}{keibajo_code}{kaiji:02d}{nichime:02d}{int(race_no):02d}"
    return race_id

# -------------------------------------------------------
# 【3】race_id から出馬表を取得
# -------------------------------------------------------
def fetch_shutuba(race_id):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None, url

    soup = BeautifulSoup(r.text, "html.parser")

    # 馬名
    names = [e.text.strip() for e in soup.select(".HorseName")]

    # 人気・オッズ
    odds = [e.text.strip() for e in soup.select(".Odds")]  
    ninki = [e.text.strip() for e in soup.select(".Popular")]

    if len(names) == 0:
        return None, url

    df = pd.DataFrame({
        "馬名": names,
        "人気": ninki if len(ninki)==len(names) else ["-"]*len(names),
        "オッズ": odds if len(odds)==len(names) else ["-"]*len(names),
    })

    return df, url

# -------------------------------------------------------
# STREAMLIT UI
# -------------------------------------------------------
st.title("KEIBA APP 出馬表（自動 race_id 検索版）")

st.write("日付・競馬場・レース番号を選ぶだけでOK。race_id は自動生成されます。")

# 入力UI
date_input = st.date_input("日付を選択", format="YYYY-MM-DD")
keibajo = st.selectbox("競馬場", list(KEIBAJO_CODE.keys()))
race_no = st.number_input("レース番号", 1, 12, 11)

if st.button("出馬表を取得"):
    date_str = date_input.strftime("%Y-%m-%d")

    st.write(f"入力：{date_str} / {keibajo} / {race_no}R")

    # race_id を生成
    race_id = generate_race_id(date_str, keibajo, race_no)

    if race_id is None:
        st.error("開催情報が取得できませんでした。（開催日 or 競馬場が未該当）")
        st.info("→ 開催のない日付か、過去のデータの可能性があります。")
    else:
        st.success(f"生成された race_id：{race_id}")

        df, url = fetch_shutuba(race_id)

        if df is None:
            st.error("出馬表が取得できませんでした。")
            st.write("アクセスしたURL：", url)
        else:
            st.dataframe(df)
            st.write("取得元：", url)
