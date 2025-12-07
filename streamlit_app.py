import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd

def fetch_race_page(race_id: str):
    url = f"https://race.sp.netkeiba.com/race/shutuba.html?race_id={race_id}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.text
    except Exception:
        return None
    return None

def parse_shutuba(html):
    soup = BeautifulSoup(html, "html.parser")
    horses = []
    for a in soup.find_all("a"):
        name = a.get_text().strip()
        href = a.get("href", "")
        if name and len(name) <= 15 and any("馬" not in name for ch in name):
            if any('\u4e00' <= ch <= '\u9fff' for ch in name):
                horses.append({"馬名": name, "href": href})
    return horses

st.title("レース取得（race_id 直接指定）")

race_id = st.text_input("race_id を入力してください", value="202507050211")

if st.button("出馬表取得"):
    html = fetch_race_page(race_id)
    if html:
        horses = parse_shutuba(html)
        if horses:
            st.success("取得成功！")
            st.dataframe(pd.DataFrame(horses))
        else:
            st.error("HTMLは取得できましたが出馬表の解析ができませんでした。")
            st.code(html[:5000])
    else:
        st.error("レースページを取得できませんでした。")
