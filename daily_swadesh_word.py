"""Send a random Swadesh word-of-the-day notification via ntfy.sh.

Reads the scraped Swadesh JSON, picks a random language and word entry,
and POSTs it to a configured ntfy.sh topic. Calling ``send_word`` twice
- once unfiltered and once filtered to ``TARGET_LANGUAGES`` - produces
two daily notifications: one from any available language and one from
the most-spoken language set.
"""

import requests
import json
import random
import unicodedata
from datetime import date

# ntfy.sh topic name; replace with your own before running
TOPIC = "put_your_topic_name_here"

# Path to the JSON file produced by get-swadesh.py
JSON_PATH = "swadesh_list.json"

# Top ~30 most-spoken languages represented in the Swadesh dataset.
# "Nigerian Pidgin" omitted - no Swadesh list on Wiktionary exists for it.
TARGET_LANGUAGES = [
    "Standard Chinese",
    "Hindi",
    "Arabic",
    "Bengali",
    "Portuguese",
    "Indonesian",
    "Urdu",
    "Russian",
    "German",
    "Japanese",
    "Marathi",
    "Telugu",
    "Turkish",
    "Tamil",
    "Vietnamese",
    "Tagalog",
    "Wu",
    "Korean",
    "Persian",
    "Hausa",
    "Swahili",
    "Javanese",
    "Italian",
    "Punjabi",
    "Kannada",
    "Gujarati",
    "Thai",
    "Amharic",
    "Cantonese",
    "French",
    "Spanish",
]


def send_word(filtered=False):
    """Pick a random Swadesh entry and push it to ntfy.sh.

    Args:
        filtered: If True, restrict the candidate pool to
            ``TARGET_LANGUAGES`` before sampling. The notification title
            will include the prefix "Common" to distinguish the two
            daily sends.
    """
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    if filtered:
        data = [lang for lang in data if lang["language"] in TARGET_LANGUAGES]

    lang_entry = random.choice(data)
    word_entry = random.choice(lang_entry["entries"])

    language = lang_entry["language"]
    english = word_entry["english"]
    # Collect all word-form values; skip the "english" key
    words = [v for k, v in word_entry.items() if k != "english"]

    # Re-normalize to NFC in case JSON roundtrip introduced variation
    clean_words = [unicodedata.normalize('NFC', w) for w in words]
    today_str = date.today().strftime("%Y-%m-%d")
    title_str = ("Common " if filtered else "") + f"Word of the Day: {today_str}"

    # Uncomment the two print lines and comment out the POST for local testing
    # print(title_str)
    # print(f"{language}: {', '.join(clean_words)}; {english}")

    requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=f"{language}: {', '.join(clean_words)}; {english}".encode("utf-8"),
        headers={
            "Title": title_str,
            "Priority": "default",
        },
    )


if __name__ == "__main__":
    # Send one notification from all languages, one from common languages only
    send_word()
    send_word(filtered=True)