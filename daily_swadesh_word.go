package main

import (
	"encoding/json"
	"fmt"
	"math/rand"
	"net/http"
	"os"
	"strings"
	"time"

	"golang.org/x/text/unicode/norm"
)

const TOPIC = "daily_swadesh_words_hydragon"
const JSON_PATH = "swadesh_list.json"

var targetLanguages = map[string]bool{
	"Standard Chinese": true,
	"Hindi":            true,
	"Arabic":           true,
	"Bengali":          true,
	"Portuguese":       true,
	"Indonesian":       true,
	"Urdu":             true,
	"Russian":          true,
	"German":           true,
	"Japanese":         true,
	"Marathi":          true,
	"Telugu":           true,
	"Turkish":          true,
	"Tamil":            true,
	"Vietnamese":       true,
	"Tagalog":          true,
	"Wu":               true,
	"Korean":           true,
	"Persian":          true,
	"Hausa":            true,
	"Swahili":          true,
	"Javanese":         true,
	"Italian":          true,
	"Punjabi":          true,
	"Kannada":          true,
	"Gujarati":         true,
	"Thai":             true,
	"Amharic":          true,
	"Cantonese":        true,
	"French":           true,
	"Spanish":          true,
}

func main() {
	_, err := os.Stat("swadesh_list.json")
	if os.IsNotExist(err) {
		CreateSwadeshJson()
	}
	SendWord(false)
	SendWord(true)
}

type LangEntry struct {
	Language string              `json:"language"`
	Entries  []map[string]string `json:"entries"`
}

func SendWord(filtered bool) error {
	f, err := os.Open("swadesh_list.json")
	if err != nil {
		return err
	}
	defer f.Close()

	var data []LangEntry
	if err := json.NewDecoder(f).Decode(&data); err != nil {
		return err
	}

	if filtered {
		var keep []LangEntry
		for _, lang := range data {
			if targetLanguages[lang.Language] {
				keep = append(keep, lang)
			}
		}
		data = keep
	}

	if len(data) == 0 {
		return fmt.Errorf("no languages available")
	}

	langEntry := data[rand.Intn(len(data))]
	if len(langEntry.Entries) == 0 {
		return fmt.Errorf("no entries for language %s", langEntry.Language)
	}
	wordEntry := langEntry.Entries[rand.Intn(len(langEntry.Entries))]

	language := langEntry.Language
	english := wordEntry["english"]

	var words []string
	for k, v := range wordEntry {
		if k != "english" {
			words = append(words, norm.NFC.String(v))
		}
	}

	today := time.Now().Format("2006-01-02")
	prefix := ""
	if filtered {
		prefix = "Common "
	}
	title := prefix + "Word of the Day: " + today

	fmt.Println(title)
	fmt.Printf("%s: %s; %s\n", language, strings.Join(words, ", "), english)

	body := fmt.Sprintf("%s: %s; %s", language, strings.Join(words, ", "), english)
	req, err := http.NewRequest("POST", "https://ntfy.sh/"+TOPIC, strings.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Title", title)
	req.Header.Set("Priority", "default")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return nil
}
