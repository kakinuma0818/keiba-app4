# streamlit_app.py (debug helper + fallback)
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

st.set_page_config(page_title="KEIBA APP - Debug", layout="wide")
st.title("🐎 KEIBA APP — Debug & Fallback Mode")

# basic maps
KEIBAJO_LIST = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]
KEIBAJO_ID = {"札幌":1,"函館":2,"福島":3,"新潟":4,"東京":5,"中山":6,"中京":7,"京都":8,"阪神":9,"小倉":10}

# helper functions
def fetch_url_text(url):
    try:
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
        r.encoding = r.apparent_encoding
        return r.status_code, r.text
    except Exception as e:
        return None, f"ERROR: {e}"

def debug_calendar(date_str):
    # date_str: "YYYY-MM-DD"
    year, month, day = date_str.split("-")
    cal_url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month}"
    status, text = fetch_url_text(cal_url)
    if status != 200:
        return {"ok": False, "reason": f"calendar fetch failed: status={status}", "url": cal_url}
    soup = BeautifulSoup(text, "html.parser")
    # collect td cells and find those that contain the day number
    results = []
    # try several approaches: td text, div with day, data-day attributes etc.
    # 1) all td
    tds = soup.find_all("td")
    for i, td in enumerate(tds):
        cell_text = td.get_text(" ", strip=True)
        # match exact day at start or standalone
        if re.search(rf"(^|\D){int(day)}(\D|$)", cell_text):
            # collect link texts + inner html
            links = []
            for a in td.find_all("a"):
                links.append({"text": a.get_text(" ", strip=True), "href": a.get("href")})
            results.append({
                "index": i,
                "cell_text": cell_text,
                "inner_html": str(td)[:4000],  # first 4k chars
                "links": links
            })
    # 2) fallback: find any element that contains the day number as separate element
    if not results:
        # search for elements that contain day as an element (class names)
        candidates = soup.find_all(lambda tag: tag.name in ["div","span"] and str(int(day)) in tag.get_text())
        for c in candidates[:20]:
            links = []
            for a in c.find_all("a"):
                links.append({"text": a.get_text(" ", strip=True), "href": a.get("href")})
            results.append({
                "index_desc": c.name,
                "cell_text": c.get_text(" ", strip=True),
                "inner_html": str(c)[:4000],
                "links": links
            })
    return {"ok": True, "url": cal_url, "results": results}

def find_kaisaibi_and_day_from_calendar_html(soup, day_int, keibajo):
    # Try to find strings like "中京4回2日" inside the calendar html
    for a in soup.find_all("a"):
        txt = a.get_text(" ", strip=True)
        if keibajo in txt and re.search(rf"{day_int}\D", txt):
            m = re.search(r"(\d+)回(\d+)日", txt)
            if m:
                return int(m.group(1)), int(m.group(2))
    return None, None

# --- UI ---
st.header("操作モード")

col1, col2, col3 = st.columns([2,2,1])
with col1:
    date_input = st.date_input("開催日を選択", value=None)
with col2:
    keibajo = st.selectbox("競馬場", KEIBAJO_LIST)
with col3:
    race_no = st.number_input("R", min_value=1, max_value=12, value=11)

st.markdown("---")
st.subheader("A: 自動取得（デバッグ実行）")
if st.button("デバッグ：カレンダー取得と候補表示"):
    if date_input is None:
        st.error("まず日付を選択して下さい")
    else:
        date_str = date_input.strftime("%Y-%m-%d")
        st.info(f"calendar URL を取得しています（{date_str}）...")
        out = debug_calendar(date_str)
        if not out.get("ok"):
            st.error(out.get("reason"))
            st.write("calendar URL:", out.get("url"))
        else:
            st.write("calendar URL:", out.get("url"))
            results = out.get("results", [])
            if not results:
                st.warning("カレンダー中に該当セルが見つかりませんでした（HTML 構造が予想と異なります）。")
                st.info("次は画面のスクショを送ってください、私が解析してセレクタを作ります。")
            else:
                st.success(f"{len(results)} 件の候補セルを発見。下に表示します。")
                for i, r in enumerate(results):
                    st.markdown(f"### 候補セル {i+1}")
                    st.write("cell_text:", r.get("cell_text"))
                    st.write("inner_html（先頭4k文字）:")
                    st.code(r.get("inner_html"))
                    st.write("リンク一覧（text / href）:")
                    if r.get("links"):
                        st.table(pd.DataFrame(r.get("links")))
                    else:
                        st.write("リンクなし")

st.markdown("---")
st.subheader("B: race_id 直接指定（回避用）")
race_id_input = st.text_input("race_id を直接入力（例: 202507050211）", value="")
if st.button("race_id で出馬表取得"):
    if not race_id_input:
        st.error("race_id を入力してください")
    else:
        url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id_input}"
        st.write("アクセスURL:", url)
        status, text = fetch_url_text(url)
        if status != 200:
            st.error(f"ページ取得失敗 status={status}")
        else:
            soup = BeautifulSoup(text, "html.parser")
            table = soup.select_one("table.RaceTable01")
            if table is None:
                st.error("出馬表テーブルが見つかりません (table.RaceTable01 が存在しない)")
                st.code(text[:4000])
            else:
                # parse simple columns (attempt)
                rows = table.select("tr")
                data = []
                for row in rows[1:]:
                    cols = [c.get_text(strip=True) for c in row.select("td")]
                    if cols:
                        data.append(cols)
                if data:
                    st.dataframe(pd.DataFrame(data).head(50), use_container_width=True)
                else:
                    st.warning("テーブルは見つかったがデータ解析に失敗しました。HTML を確認してください。")

st.markdown("---")
st.write("----")
st.caption("※ デバッグ実行で 'inner_html' を貼ってくれれば私がピンポイントで修正します。")
