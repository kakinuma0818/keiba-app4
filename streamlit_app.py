def find_kaisaibi_and_day(date_str, keibajo):
    """
    netkeiba カレンダーの HTML 構造が頻繁に変わるため、
    2025年最新版に合わせて強化した解析ロジック。
    """

    year, month, day = date_str.split("-")
    target_day = str(int(day))  # "07"→"7" に揃える
    cal_url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month}"

    r = requests.get(cal_url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")

    # ▼ 改良ポイント1：曜⽇セル table 全体から "7" を含むセルを探す
    day_cells = soup.select("td")

    for cell in day_cells:
        cell_text = cell.get_text(strip=True)

        # "7" or "07" を含むセルを探す
        if re.match(rf"^{int(day)}(\D|$)", cell_text):
            # ▼ 改良ポイント2：同じセル内のリンクに競馬場名が含まれるか確認
            links = cell.find_all("a")

            for link in links:
                txt = link.get_text(strip=True)

                # 例：「中京4回2日」「中京競馬場4回2日」など両方対応
                if keibajo in txt:
                    m = re.search(r"(\d+)回(\d+)日", txt)
                    if m:
                        return int(m.group(1)), int(m.group(2))

    return None, None
