"""Scrape Swadesh word lists from Wiktionary and save to JSON.

Crawls the Wiktionary Swadesh list category, parses each language's
table into English-keyed word entries, and writes the full dataset
to ``swadesh_list_2.json``.
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://en.wiktionary.org"
CATEGORY_URL = BASE + "/wiki/Category:Swadesh_lists_by_language"
HEADERS = {"User-Agent": "SwadeshScraper/1.0"}


def clean_text(element, is_language_header=False):
    """Normalize raw HTML cell content into a clean Unicode string.

    Strips newlines, citation brackets, and edit links. When
    ``is_language_header`` is True, non-Latin characters are dropped so
    that column headers contain only ASCII/extended-Latin text.

    Args:
        element: A BeautifulSoup tag, a plain string, or ``None``.
        is_language_header: If True, strip non-Latin characters.

    Returns:
        A NFC-normalized, whitespace-collapsed string, or ``""`` if the
        input is falsy.
    """
    if not element:
        return ""
    text = element if isinstance(element, str) else element.get_text(separator=" ")
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    # Remove "edit (N)" links injected by MediaWiki
    text = re.sub(r'edit\s*\(\d+\)', '', text)
    # Remove footnote references like [1], [2]
    text = re.sub(r'\[\d+\]', '', text)
    if is_language_header:
        # Keep only Latin-script characters and basic punctuation
        latin_only = re.findall(r'[A-Za-z\u00C0-\u024F\s\-\(\)]+', text)
        text = "".join(latin_only)
        text = text.replace('()', '').strip()
    # Tidy up stray whitespace around punctuation
    text = re.sub(r'\(\s+', '(', text)
    text = re.sub(r'\s+\)', ')', text)
    text = re.sub(r'\s+([*,;:?\.])', r'\1', text)
    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def get_swadesh_pages():
    """Return all Swadesh list page URLs and their language names.

    Paginates through the Wiktionary category until no "next page" link
    is found.

    Returns:
        A deduplicated list of ``(url, language_name)`` tuples.
    """
    pages = []
    url = CATEGORY_URL
    while url:
        print(f"Crawling Category Page: {url}")
        r = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select(".mw-category a"):
            href = a.get("href", "")
            if href.startswith("/wiki/Appendix:") and "Swadesh" in href:
                lang_name = a.get_text().replace("Appendix:", "").split("Swadesh")[0].strip()
                pages.append((BASE + href, lang_name))
        next_link = soup.find("a", string=re.compile(r"next (page|200)", re.I))
        url = BASE + next_link["href"] if next_link and "href" in next_link.attrs else None
    return list(set(pages))


def parse_page(url, lang_name):
    """Parse a single Wiktionary Swadesh list page into structured entries.

    Locates the first ``wikitable`` on the page, identifies the English
    column and any non-blacklisted target-language columns, then yields
    one dict per row mapping ``"english"`` and column-name keys to cell
    text.

    Columns whose headers match terms like "ipa", "notes", "cognate", etc.
    are skipped to avoid including metadata in word entries.

    Args:
        url: Full URL of the Wiktionary appendix page.
        lang_name: Human-readable language name used as the ``"language"``
            field in the returned data.

    Returns:
        A list containing a single ``{"language": ..., "entries": [...]}``
        dict, or an empty list if no usable table was found.
    """
    r = requests.get(url, headers=HEADERS)
    r.encoding = 'utf-8'
    soup = BeautifulSoup(r.text, "html.parser")

    table = soup.find("table", class_="wikitable")
    if not table:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    header_cells = rows[0].find_all(["th", "td"])
    col_names = [clean_text(c) for c in header_cells]

    # Column header fragments that indicate metadata rather than word forms
    BLACKLIST = [
        "no.", "№", "number", "example", "term?",
        "ipa", "transcription", "phonetic", "transliteration",
        "notes", "gloss", "reconstruction", "cognate", "literal"
    ]

    idx_eng = -1
    target_indices = []

    for i, name in enumerate(col_names):
        name_low = name.lower()
        if "english" in name_low:
            idx_eng = i
            continue
        if not any(term in name_low for term in BLACKLIST):
            target_indices.append(i)

    # Fall back to column 1 if no explicit English header was found
    if idx_eng == -1:
        idx_eng = 1

    entries = []
    for row in rows[1:]:
        cols = row.find_all(["td", "th"])
        max_idx = max(idx_eng, max(target_indices, default=0))
        if len(cols) <= max_idx:
            continue

        english_val = clean_text(cols[idx_eng])
        if not english_val:
            continue

        entry = {"english": english_val}
        for idx in target_indices:
            if idx >= len(cols):
                continue
            word_val = clean_text(cols[idx])
            # Skip cells that are clearly empty or placeholder dashes
            if not word_val or word_val in ["-", "-", "?", "？"]:
                continue
            key = col_names[idx].lower() if col_names[idx] else f"col_{idx}"
            entry[key] = word_val

        # Only keep entries that have at least one non-English word
        if len(entry) > 1:
            entries.append(entry)

    return [{"language": lang_name, "entries": entries}] if entries else []


def main():
    """Scrape all Swadesh pages and write results to ``swadesh_list_2.json``."""
    pages = get_swadesh_pages()
    print(f"Found {len(pages)} pages to scrape.")

    all_data = []

    def scrape(i, url, lang_name):
        """Fetch and parse one page; print a progress line on success."""
        entries = parse_page(url, lang_name)
        if entries:
            print(f"   [{i+1}/{len(pages)}] {lang_name} - {entries[0]['entries'][0]}")
        return entries

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(scrape, i, url, lang_name): url
            for i, (url, lang_name) in enumerate(pages)
        }
        for future in as_completed(futures):
            try:
                entries = future.result()
                if entries:
                    all_data.extend(entries)
            except Exception as e:
                print(f"   Error: {e}")

    output_filename = "swadesh_list.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"\nDone! Saved {len(all_data)} entries to {output_filename}")


if __name__ == "__main__":
    main()