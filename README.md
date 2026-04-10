# swadesh-notify

Daily word-of-the-day push notifications drawn from Wiktionary's Swadesh lists, delivered via [ntfy.sh](https://ntfy.sh/).

## What it does

* **`get-swadesh.go`** — Scrapes every Swadesh list appendix on Wiktionary (~200+ languages), parses each table into English-keyed word entries, and writes the result to `swadesh_list.json`. Scraping is parallelized across 8 workers.
* **`daily_swadesh_word.go`** — Reads the JSON, picks a random language and word entry, and POSTs two daily notifications to an ntfy.sh topic: one from the full dataset and one filtered to the ~30 most-spoken languages.

## Setup

Install Go (1.25+), then fetch dependencies:

```bash
go mod tidy
```

1. Set `TOPIC` in `daily_swadesh_word.go` to your ntfy.sh topic name.
2. Run the program — if `swadesh_list.json` is missing it will scrape Wiktionary automatically before sending notifications:
   ```bash
   go run .
   ```
3. Schedule with cron or a similar scheduler:
   ```
   0 8 * * * /path/to/swadesh-notify
   ```
   Build the binary with `go build -o swadesh-notify .`

## Running

```bash
go run .
```

If `swadesh_list.json` does not exist, the program scrapes Wiktionary first and writes it. Then it sends two notifications — one drawn from all languages, one filtered to the ~30 most-spoken languages in `targetLanguages`.

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
* `targetLanguages` in `daily_swadesh_word.go` can be edited freely to change the "common languages" pool.