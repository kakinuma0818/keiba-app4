# --- 依存：このブロックは streamlit_app.py 内の既存の imports と conflict しないように貼ってください ---
import streamlit as st
import pandas as pd
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from typing import Optional, List, Tuple, Dict
from datetime import date as dt_date

# --- 基本定義（必要に応じて既存の定義と統合） ---
BASE_URL_SP = "https://race.sp.netkeiba.com/race/shutuba.html?race_id={race_id}"
HEADERS = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
VENUE_CODE_RANGE = list(range(1, 51))  # 1..50 を探索（必要時増やす）
PAUSE = 0.45  # 試行ごとの間隔（秒）

# --- 競馬場名 -> 候補場コードマップ（必要に応じて追加/編集して使ってください）
# ※ 正確な場コードは site 毎に差があるので、未確認なら空にして自動探索にフォールバックします。
VENUE_CODE_MAP: Dict[str, List[int]] = {
    # サンプル（編集推奨）
    "札幌": [1],
    "函館": [2],
    "福島": [3],
    "新潟": [4],
    "東京": [5],
    "中山": [6],
    "中京": [7],
    "京都": [8],
    "阪神": [9],
    "小倉": [10],
    # 上はサンプル。実際に正確なコードが分かればここを更新してください。
}

# ---------------------------
# helper: race_id 組み立て
# ---------------------------
def build_race_id(date_obj: dt_date, venue_code: int, race_no: int) -> str:
    yyyy = date_obj.year
    mm = f"{date_obj.month:02d}"
    dd = f"{date_obj.day:02d}"
    venue = f"{venue_code:02d}"
    rno = f"{race_no:02d}"
    return f"{yyyy}{mm}{dd}{venue}{rno}"

# ---------------------------
# helper: URL 取得試行
# ---------------------------
def try_fetch(url: str, timeout=10) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r
    except Exception:
        pass
    return None

def is_valid_race_page(html_text: str, race_no:int) -> bool:
    lower = html_text.lower()
    # スマホページでは "XR" という表記で判定が難しいこともあるため複合判定
    if f"{race_no}r" in lower:
        return True
    if "出馬" in html_text or "出走表" in html_text:
        return True
    # 加えて「出走表」以外を検出したい場合にここを拡張
    return False

# ---------------------------
# find by venue_codes list (速いパターン)
# ---------------------------
def find_race_url_by_venue_codes(date_obj: dt_date, race_no:int, venue_codes: List[int], pause: float = PAUSE) -> Tuple[Optional[str], List[str]]:
    tried = []
    for v in venue_codes:
        race_id = build_race_id(date_obj, v, race_no)
        url = BASE_URL_SP.format(race_id=race_id)
        tried.append(url)
        res = try_fetch(url)
        if res and is_valid_race_page(res.text, race_no):
            return url, tried
        time.sleep(pause)
    return None, tried

# ---------------------------
# fallback: brute-force search across full range
# ---------------------------
def find_race_url_by_search(date_obj: dt_date, race_no:int, max_tries:int = None, pause:float = PAUSE) -> Tuple[Optional[str], List[str]]:
    tried = []
    rng = VENUE_CODE_RANGE if max_tries is None else VENUE_CODE_RANGE[:max_tries]
    for v in rng:
        race_id = build_race_id(date_obj, v, race_no)
        url = BASE_URL_SP.format(race_id=race_id)
        tried.append(url)
        res = try_fetch(url)
        if res and is_valid_race_page(res.text, race_no):
            return url, tried
        time.sleep(pause)
    return None, tried

# ---------------------------
# 出馬表解析（簡易版 / 必要に応じ調整）
# ---------------------------
from bs4 import BeautifulSoup
def parse_sp_netkeiba_shutuba(html_text: str):
    soup = BeautifulSoup(html_text, "html.parser")
    horses = []
    # mobile layout の場合は div や li に馬情報がまとまっているケースがあるので多角的に試す
    # ここはまず「馬名を含むリンク」を探して順に収集するシンプル実装
    anchors = soup.find_all("a")
    for a in anchors:
        txt = a.get_text().strip()
        href = a.get("href","")
        if not txt:
            continue
        # 馬名らしい（簡易ヒューリスティック）
        if len(txt) <= 15 and any('\u4e00' <= ch <= '\u9fff' for ch in txt):  # 含漢字 && 文字数控えめ
            horses.append({"馬名": txt, "detail_href": href})
    # Dedup
    seen = set()
    final = []
    for h in horses:
        if h["馬名"] in seen:
            continue
        seen.add(h["馬名"])
        final.append(h)
    return final

# ---------------------------
# Streamlit UI: ここを既存のレース取得UIと置き換えてください
# ---------------------------
st.markdown("## レース取得（競馬場選択方式）")
col1, col2, col3 = st.columns([2,3,2])

with col1:
    date = st.date_input("レース日", value=None)

# 競馬場リスト（表示用）
venue_list = ["自動探索（全場）"] + sorted(list(VENUE_CODE_MAP.keys()))
venue_list.append("その他（自分で場コード入力）")

with col2:
    venue_choice = st.selectbox("競馬場を選ぶ（自動化）", venue_list, index=0)

with col3:
    race_no = st.number_input("R", min_value=1, max_value=12, value=11, step=1)

# 場コードを手入力する欄（必要な場合のみ表示）
manual_code = ""
if venue_choice == "その他（自分で場コード入力）":
    manual_code = st.text_input("場コード（2桁）を入力", value="")

# 実行ボタン
if st.button("レース取得（競馬場名で検索）"):
    if date is None:
        st.error("日付を選択してください")
    else:
        found_url = None
        tried_urls = []

        # 1) venue_choice が地名リストにあるなら、その候補コードだけ試す（速い）
        if venue_choice != "自動探索（全場）" and venue_choice != "その他（自分で場コード入力）":
            candidate_codes = VENUE_CODE_MAP.get(venue_choice, [])
            if candidate_codes:
                st.info(f"{venue_choice} の候補場コードを試行します: {candidate_codes}")
                url, tried = find_race_url_by_venue_codes(date, race_no, candidate_codes)
                tried_urls.extend(tried)
                if url:
                    found_url = url

        # 2) ユーザが手入力した場コードがある場合はまずそれを試す
        if not found_url and manual_code and manual_code.isdigit():
            v = int(manual_code)
            st.info(f"手動で場コード {v:02d} を試行します")
            url_try = BASE_URL_SP.format(race_id=build_race_id(date, v, race_no))
            tried_urls.append(url_try)
            res = try_fetch(url_try)
            if res and is_valid_race_page(res.text, race_no):
                found_url = url_try

        # 3) fallback: 全場を brute-force 探索（時間かかるが見つかる確率が高い）
        if not found_url:
            with st.spinner("候補場コードを総当たりで探索しています（時間がかかる場合があります）..."):
                url, tried = find_race_url_by_search(date, race_no, max_tries=None)
                tried_urls.extend(tried)
                if url:
                    found_url = url

        # 結果表示
        if not found_url:
            st.error("レースページが見つかりませんでした。候補URLの一部を表示します。")
            st.write(pd.DataFrame({"tried_urls": tried_urls[:40]}))
        else:
            st.success("レースページを発見しました！")
            st.write(found_url)
            res = try_fetch(found_url)
            if res:
                horses = parse_sp_netkeiba_shutuba(res.text)
                if not horses:
                    st.warning("出馬表の抽出に失敗しました（HTML構造が想定と異なる可能性があります）。")
                    # デバッグ用として一部HTMLを表示（必要なら）
                    st.code(res.text[:4000])
                else:
                    st.markdown("### 出馬表（自動取得）")
                    st.dataframe(pd.DataFrame(horses), use_container_width=True)
