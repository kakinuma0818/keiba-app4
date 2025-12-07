import streamlit as st
import requests
from bs4 import BeautifulSoup
import re

# -------------------------------
# 開催情報取得関数
# -------------------------------
def find_kaisaibi_and_day(date_str, keibajo):
    """
    netkeiba カレンダーから「回」と「日」を取得
    """
    year, month, day = date_str.split("-")
    cal_url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month}"

    try:
        r = requests.get(cal_url, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
    except:
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")
    day_cells = soup.select("td.RaceCellBox")

    for cell in day_cells:
        cell_text = cell.get_text(strip=True)
        # 日付と競馬場名を含むか確認
        if str(int(day)) in cell_text and keibajo in cell_text:
            links = cell.find_all("a")
            for link in links:
                txt = link.get_text(strip=True)
                if keibajo in txt:
                    m = re.search(r"(\d+)回(\d+)日", txt)
                    if m:
                        return int(m.group(1)), int(m.group(2))
    return None, None

# -------------------------------
# Streamlit UI
# -------------------------------
st.set_page_config(page_title="開催情報取得テスト", layout="wide")
st.title("開催情報取得テスト")

# 入力欄
date_input = st.date_input("開催日")
keibajo_input = st.selectbox("競馬場", ["中山", "阪神", "中京", "京都", "新潟", "札幌", "函館"])
race_num_input = st.number_input("レース番号", min_value=1, max_value=12, value=11)

# 更新ボタン
if st.button("更新"):
    date_str = date_input.strftime("%Y-%m-%d")
    kai, day = find_kaisaibi_and_day(date_str, keibajo_input)
    if kai and day:
        st.success(f"{keibajo_input} {kai}回{day}日 の情報を取得しました")
        st.write(f"レース番号: {race_num_input}")
    else:
        st.error("開催情報が取得できませんでした。開催日 or 競馬場が未該当の可能性があります。")
