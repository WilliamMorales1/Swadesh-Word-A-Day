# swadesh-notify

Daily word-of-the-day push notifications drawn from Wiktionary's Swadesh lists, delivered via [ntfy.sh](https://ntfy.sh/).

## What it does

**`daily_swadesh_word.py`** — Scrapes every Swadesh list appendix on Wiktionary (~200+ languages), parses each table into English-keyed word entries, writes the result to `swadesh_list.json`, then POSTs two daily notifications to an ntfy.sh topic: one from the full dataset and one filtered to the ~30 most-spoken languages. Scraping is parallelized across 8 workers.

## Setup

Install Python 3.10+, then install dependencies:

```bash
pip install requests beautifulsoup4
```

1. Set `TOPIC` in `daily_swadesh_word.py` to your ntfy.sh topic name.
2. Run the script — if `swadesh_list.json` is missing it will scrape Wiktionary automatically before sending notifications:
   ```bash
   python daily_swadesh_word.py
   ```
3. Schedule with cron or a similar scheduler:
   ```
   0 8 * * * /usr/bin/python3 /path/to/daily_swadesh_word.py
   ```

## Running

```bash
python daily_swadesh_word.py
```

If `swadesh_list.json` does not exist, the script scrapes Wiktionary first and writes it. Then it sends two notifications — one drawn from all languages, one filtered to the ~30 most-spoken languages in `TARGET_LANGUAGES`.

## Data format

`swadesh_list.json` is a list of language objects:

```json
[
  {
    "language": "Spanish",
    "entries": [
      {
        "english": "I (1sg)",
        "spanish español": "yo"
      },
      {
        "english": "you (2sg)",
        "spanish español": "tú, vos, usted (formal)"
      }
    ]
  }
]
```

## Notes

* The scraper skips metadata columns (IPA, notes, cognates, etc.) automatically.
* All text is NFC-normalized throughout.
* `TARGET_LANGUAGES` in `daily_swadesh_word.py` can be edited freely to change the "common languages" pool.
