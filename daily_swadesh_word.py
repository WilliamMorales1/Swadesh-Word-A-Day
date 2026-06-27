import json
import os
import random
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import requests
from bs4 import BeautifulSoup

TOPIC = "daily_swadesh_words_hydragon"
JSON_PATH = "swadesh_list.json"
BASE = "https://en.wiktionary.org"

TARGET_LANGUAGES = {
    "Standard Chinese", "Hindi", "Arabic", "Bengali", "Portuguese",
    "Indonesian", "Urdu", "Russian", "German", "Japanese", "Marathi",
    "Telugu", "Turkish", "Tamil", "Vietnamese", "Tagalog", "Wu",
    "Korean", "Persian", "Hausa", "Swahili", "Javanese", "Italian",
    "Punjabi", "Kannada", "Gujarati", "Thai", "Amharic", "Cantonese",
    "French", "Spanish",
}

BLACKLIST = [
    "no", "no.", "№", "number", "example", "term?",
    "ipa", "transcription", "phonetic", "transliteration",
    "notes", "gloss", "reconstruction", "cognate", "literal",
]

SCRAPER_HEADERS = {"User-Agent": "SwadeshScraper/1.0"}
session = requests.Session()
session.headers.update(SCRAPER_HEADERS)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def clean_text(text: str, is_language_header: bool) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = re.sub(r"edit\s*\(\d+\)", "", text)
    if is_language_header:
        parts = re.findall(r"[A-Za-z\xC0-ɏ\s\-()\[\]]+", text)
        text = "".join(parts).replace("()", "")
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\s+([*,;:?.])", r"\1", text)
    text = nfc(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_text(tag) -> str:
    return tag.get_text()


def get_swadesh_pages() -> list[dict]:
    pages = []
    seen = set()
    url = BASE + "/wiki/Category:Swadesh_lists_by_language"
    next_page_re = re.compile(r"(?i)next\s+(page|200)")

    while url:
        print(f"Crawling Category Page: {url}")
        resp = session.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        next_url = None
        cat_div = soup.find("div", class_=re.compile(r"mw-category"))
        if cat_div:
            for a in cat_div.find_all("a", href=True):
                href = str(a.get("href") or "")
                text = a.get_text()
                if href.startswith("/wiki/Appendix:") and "Swadesh" in href:
                    lang_name = text.replace("Appendix:", "").split("Swadesh")[0].strip()
                    full_url = BASE + href
                    if full_url not in seen:
                        seen.add(full_url)
                        pages.append({"url": full_url, "lang_name": lang_name})

        for a in soup.find_all("a", href=True):
            if next_page_re.search(a.get_text()):
                next_url = BASE + str(a.get("href") or "")
                break

        url = next_url

    return pages


def parse_page(url: str, lang_name: str) -> dict | None:
    try:
        resp = session.get(url)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_=re.compile(r"wikitable"))
    if not table:
        return None

    rows = table.find_all("tr")
    if not rows:
        return None

    header_cells = rows[0].find_all(["th", "td"])
    col_names = [clean_text(extract_text(c), True) for c in header_cells]

    idx_eng = -1
    target_indices = []
    for i, name in enumerate(col_names):
        name_low = name.lower()
        if "english" in name_low:
            idx_eng = i
            continue
        if name == "" or any(b in name_low for b in BLACKLIST):
            continue
        target_indices.append(i)

    if idx_eng == -1:
        idx_eng = 1

    entries = []
    for row in rows[1:]:
        cols = row.find_all(["td", "th"])
        max_idx = max([idx_eng] + target_indices) if target_indices else idx_eng
        if len(cols) <= max_idx:
            continue

        english_val = clean_text(extract_text(cols[idx_eng]), False)
        if not english_val:
            continue

        entry = {"english": english_val}
        for idx in target_indices:
            if idx >= len(cols):
                continue
            word_val = clean_text(extract_text(cols[idx]), False)
            if not word_val or word_val in ("-", "–", "?", "？"):
                continue
            key = col_names[idx].lower() if col_names[idx] else f"col_{idx}"
            entry[key] = word_val

        if len(entry) > 1:
            entries.append(entry)

    if not entries:
        return None

    return {"language": lang_name, "entries": entries}


def create_swadesh_json():
    pages = get_swadesh_pages()
    print(f"Found {len(pages)} pages to scrape")

    all_data = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(parse_page, p["url"], p["lang_name"]): (i, p)
            for i, p in enumerate(pages)
        }
        for future in as_completed(futures):
            i, p = futures[future]
            result = future.result()
            if result:
                print(f"   [{i+1}/{len(pages)}] {p['lang_name']} - {result['entries'][0]}")
                all_data.append(result)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Saved {len(all_data)} entries to {JSON_PATH}")


def send_word(filtered: bool):
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    if filtered:
        data = [d for d in data if d["language"] in TARGET_LANGUAGES]

    if not data:
        raise RuntimeError("no languages available")

    lang_entry = random.choice(data)
    if not lang_entry["entries"]:
        raise RuntimeError(f"no entries for language {lang_entry['language']}")

    word_entry = random.choice(lang_entry["entries"])
    language = lang_entry["language"]
    english = word_entry["english"]
    words = [nfc(v) for k, v in word_entry.items() if k != "english"]

    today = date.today().isoformat()
    prefix = "Common " if filtered else ""
    title = f"{prefix}Word of the Day: {today}"

    print(title)
    print(f"{language}: {', '.join(words)}; {english}")

    body = f"{language}: {', '.join(words)}; {english}"
    requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=body,
        headers={"Title": title, "Priority": "default"},
    )


def main():
    if not os.path.exists(JSON_PATH):
        create_swadesh_json()
    send_word(False)
    send_word(True)


if __name__ == "__main__":
    main()
