# swadesh-notify

Daily word-of-the-day push notifications drawn from Wiktionary's Swadesh lists, delivered via [ntfy.sh](https://ntfy.sh/).

## What it does

* **`get-swadesh.py`** — Scrapes every Swadesh list appendix on Wiktionary (~200+ languages), parses each table into English-keyed word entries, and writes the result to `swadesh_list.json`.
* **`daily_swadesh_word.py`** — Reads the JSON, picks a random language and word entry, and POSTs two daily notifications to an ntfy.sh topic: one from the full dataset and one filtered to the ~30 most-spoken languages.

## Setup

```bash
pip install requests beautifulsoup4
```

1. Run the scraper once to build the dataset:
   ```bash
   python get-swadesh.py   # produces swadesh_list.json
   ```
2. Edit `daily_swadesh_word.py` and set `TOPIC` to your ntfy.sh topic name.
3. Schedule `daily_swadesh_word.py` with cron or a similar scheduler:
   ```
   0 8 * * * python /path/to/daily_swadesh_word.py
   ```

## Testing locally

Uncomment the two `print` lines in `send_word()` and comment out the `requests.post` call — it'll print the notification body to stdout instead of sending it.

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
    }
]
```

## Notes

* The scraper skips metadata columns (IPA, notes, cognates, etc.) automatically.
* All text is NFC-normalized throughout.
* `TARGET_LANGUAGES` in `daily_swadesh_word.py` can be edited freely to change the "common languages" pool.
