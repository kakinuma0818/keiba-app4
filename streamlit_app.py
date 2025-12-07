# streamlit_app.py
import streamlit as st
import pandas as pd
import time
import requests
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Tuple

st.set_page_config(page_title="KEIBA Auto Fetch", layout="wide")

# ---------- 設定 ----------
BASE_URL_SP = "https://race.sp.netkeiba.com/race/shutuba.html?race_id={race_id}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
             "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"

HEADERS = {"User-Agent": USER_AGENT}

# 場コードの候補レンジ（01〜30程度を順に試す）
# 実際の場コードは site に依存するため幅を持たせて探索する実装にしています。
VENUE_CODE_RANGE = list(range(1, 31))  # 1..30 を試す。必要に応じ増やす。

# ---------- ヘルパー関数 ----------
def build_race_id(date_obj, venue_code: int, race_no: int) -> str:
    """
    date_obj: datetime.date
    venue_code: int (1..)
    race_no: int (1..12)
    Example pattern (based on your sample): YYYYMMDD vv rr
    returns str like '20250705' + '02' + '11' -> '202507050211'
    """
    yyyy = date_obj.year
    mm = f"{date_obj.month:02d}"
    dd = f"{date_obj.day:02d}"
    venue = f"{venue_code:02d}"
    rno = f"{race_no:02d}"
    return f"{yyyy}{mm}{dd}{venue}{rno}"

def try_fetch(url: str, timeout=10) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r
        else:
            return None
    except Exception as e:
        return None

def is_valid_race_page(html_text: str, race_no:int) -> bool:
    """
    ページが有効かを簡易チェックする関数。
    例：ページ内に「{race_no}R」や "出馬" などのキーワードが含まれているか確認。
    """
    lower = html_text.lower()
    if f"{race_no}r" in lower:
        return True
    # '出馬' が含まれると良し（日本語）
    if "出馬" in html_text or "出走表" in html_text:
        return True
    # その他の判定ロジックはここに追加可能
    return False

def find_race_url_by_search(date_obj, race_no:int, max_tries=30, pause=0.6) -> Tuple[Optional[str], List[str]]:
    """
    date, race_no を与えて、venue_code 候補を順に試し、
    存在する最初の URL を返す（見つからなければ None）。
    戻り値: (found_url_or_None, tried_urls_list)
    """
    tried = []
    for vcode in VENUE_CODE_RANGE[:max_tries]:
        race_id = build_race_id(date_obj, vcode, race_no)
        url = BASE_URL_SP.format(race_id=race_id)
        tried.append(url)
        res = try_fetch(url)
        if res and is_valid_race_page(res.text, race_no):
            return url, tried
        time.sleep(pause)  # サイト負荷を下げる
    return None, tried

# ---------- 出馬表解析 ----------
def parse_sp_netkeiba_shutuba(html_text: str) -> List[Dict]:
    """
    race.sp.netkeiba の出馬表（shutuba）ページから馬情報を抽出して
    リスト（dict）で返す。抽出する主な項目:
      - 馬番, 馬名, 性齢, 騎手, 調教師, 斤量, 前走体重, 脚質, 馬詳細URL(相対)
    注意: HTML 構造が変わることがあるため、セレクタは柔軟にしています。
    """
    soup = BeautifulSoup(html_text, "html.parser")
    horses = []

    # まず、出走馬を含むテーブルやリストを探す。
    # ここでは「馬番」や「出走馬」というテキストを含む要素を探してから
    # 近傍の table / ul を解析する戦略。
    # Common pattern: <table class="db_h_race_results"> など（もしあれば）
    # We'll try multiple heuristics.

    # Heuristic 1: find rows that contain 馬番 and 馬名 consistently
    # Search for elements with class or id likely to contain horse rows
    candidate_rows = []

    # Try to find table rows first
    for table in soup.find_all("table"):
        # Heuristic: table has header containing '馬番' or '馬名' or '馬'
        th_text = " ".join([th.get_text() for th in table.find_all("th")]).strip()
        if "馬番" in th_text or "馬名" in th_text or "馬" in th_text:
            # collect rows
            for tr in table.find_all("tr"):
                candidate_rows.append(tr)

    # If no table-based rows, try list items (mobile layout)
    if not candidate_rows:
        # mobile site often uses divs with class containing 'horse' or 'Shutuba'
        divs = soup.find_all("div")
        for d in divs:
            txt = d.get_text().strip()
            if txt and ("馬" in txt or "馬番" in txt) and len(txt) < 200:
                # small heuristic
                candidate_rows.append(d)

    # Now from candidate_rows, attempt to parse horse entries
    parsed = []
    for r in candidate_rows:
        text = r.get_text(separator=" ").strip()
        # naive parse: look for pattern like "1 馬名 牡4 ..."
        # We'll attempt to extract digits at start (馬番)
        parts = text.split()
        if not parts:
            continue
        # find first numeric token (1..18)
        horse_no = None
        for tok in parts[:5]:
            if tok.isdigit():
                horse_no = int(tok)
                break
        # look for jockey token (assume Kanji + space + 例 '川田将雅' - heuristic)
        # We will fallback to include the entire row as name if parsing isn't exact
        if horse_no is None:
            continue
        # determine horse name: token right after number
        try:
            idx = parts.index(str(horse_no))
            horse_name = parts[idx+1] if len(parts) > idx+1 else ""
        except ValueError:
            horse_name = parts[1] if len(parts) > 1 else ""

        parsed.append({
            "馬番": horse_no,
            "馬名": horse_name,
            "raw_text": text
        })

    # If parsed is empty, fallback parse by searching specific class patterns
    if not parsed:
        # Attempt second heuristic: find anchor tags which link to horse details
        anchors = soup.find_all("a")
        for a in anchors:
            href = a.get("href","")
            if "horse" in href and a.text.strip():
                # extract surrounding number if present
                txt = a.text.strip()
                parsed.append({"馬番": None, "馬名": txt, "raw_text": txt, "detail_href": href})

    # Normalize and sort by 馬番 if available
    horses_clean = []
    for p in parsed:
        horses_clean.append({
            "馬番": p.get("馬番"),
            "馬名": p.get("馬名"),
            "raw": p.get("raw_text"),
            # other fields can be filled later by visiting horse detail page if needed
        })

    # Deduplicate by horse name
    seen = set()
    final = []
    for h in sorted(horses_clean, key=lambda x: (x["馬番"] if x["馬番"] is not None else 999)):
        key = (h["馬番"], h["馬名"])
        if key in seen:
            continue
        seen.add(key)
        final.append(h)

    return final

# ---------- Streamlit UI ----------
st.title("KEIBA Auto Fetch — レース取得")

st.markdown("""
- 日付・レース番号を指定すると、netkeiba（sp版）ページを自動で探して出馬表を取得します。  
- ※ 個人利用で行ってください。短時間で何度もアクセスするとブロックされることがあります。
""")

col1, col2, col3 = st.columns([2,2,1])

with col1:
    date = st.date_input("レース日", value=None)

with col2:
    race_no = st.number_input("レース番号 (R)", min_value=1, max_value=12, value=11, step=1)

with col3:
    optional_venue = st.text_input("任意：場コード（2桁）", value="")  # if user knows venue code

if st.button("レース取得（自動探索）"):
    if date is None:
        st.error("日付を選択してください")
    else:
        # if user provided venue code, try that first
        found_url = None
        tried = []
        if optional_venue and optional_venue.isdigit():
            v = int(optional_venue)
            rid = build_race_id(date, v, race_no)
            url_try = BASE_URL_SP.format(race_id=rid)
            st.info(f"指定場コードで試行: {url_try}")
            res = try_fetch(url_try)
            if res and is_valid_race_page(res.text, race_no):
                found_url = url_try
                tried = [url_try]
            else:
                st.warning("指定場コードでは見つかりませんでした。全探索を開始します...")
        if not found_url:
            with st.spinner("race_id を自動探索しています（候補を順にチェックしています）..."):
                url, tried = find_race_url_by_search(date, race_no, max_tries=len(VENUE_CODE_RANGE))
                found_url = url

        if not found_url:
            st.error("レースページを自動で見つけられませんでした。手動で race_id を指定するか、時間をあけて再試行してください。")
            st.write("試行したURL候補の一部：")
            st.write(pd.DataFrame({"tried_urls": tried[:30]}))
        else:
            st.success("レースページを発見しました！")
            st.write(found_url)
            res = requests.get(found_url, headers=HEADERS, timeout=15)
            horses = parse_sp_netkeiba_shutuba(res.text)
            if not horses:
                st.warning("ページは見つかりましたが、出馬表の解析に失敗しました。HTML構造が想定と異なる可能性があります。")
                st.write(res.text[:5000])  # debug, remove in production
            else:
                df = pd.DataFrame(horses)
                st.markdown("### 出馬表（自動取得）")
                st.dataframe(df, use_container_width=True)

# ---------- end ----------
