package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"unicode"

	"golang.org/x/net/html"
	"golang.org/x/text/unicode/norm"
)

const BASE = "https://en.wiktionary.org"

var scraperHeader = http.Header{
	"User-Agent": []string{"SwadeshScraper/1.0"},
}

var httpClient = &http.Client{}

func CreateSwadeshJson() {
	pages := GetSwadeshPages()
	fmt.Printf("Found %v pages to scrape\n", len(pages))

	// create vars to store data and for concurrency stuff
	var (
		allData []map[string]any
		mu      sync.Mutex
		wg      sync.WaitGroup
		sem     = make(chan struct{}, 8) // max 8 concurrent workers
	)

	for i, page := range pages {
		wg.Add(1)
		go func(i int, url, langName string) {
			defer wg.Done()

			sem <- struct{}{}        // sends an empty struct to the channel
			defer func() { <-sem }() // goroutine finishes, calls anonymous func, removes goroutine

			ld := ParsePage(url, langName)
			if len(ld.Entries) > 0 {
				// for checking progress
				fmt.Printf("   [%v/%v] %s - %v\n", i+1, len(pages), langName, ld.Entries[0])

				// lock for writing data
				mu.Lock()
				allData = append(allData, map[string]any{
					"language": ld.LangName,
					"entries":  ld.Entries,
				})
				mu.Unlock()
			}
		}(i, page.URL, page.LangName)
	}
	wg.Wait()

	outputFilename := "swadesh_list.json"
	f, err := os.Create(outputFilename)
	if err != nil {
		fmt.Printf("Error creating output file: %v\n", err)
		return
	}
	defer f.Close()

	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	if err := enc.Encode(allData); err != nil {
		fmt.Printf("Error encoding JSON: %v\n", err)
		return
	}

	fmt.Printf("\nDone! Saved %v entries to %s\n", len(allData), outputFilename)
}

// CleanText normalizes raw HTML cell content into a clean Unicode string.
func CleanText(element string, isLanguageHeader bool) string {
	if element == "" {
		return ""
	}

	text := element
	text = strings.NewReplacer("\n", " ", "\r", " ", "\t", " ").Replace(text)

	// Remove "edit(123)" artifacts from wiktionary
	editRe := regexp.MustCompile(`edit\s*\(\d+\)`)
	text = editRe.ReplaceAllString(text, "")

	if isLanguageHeader {
		// Keep only Latin-range characters (basic + extended), spaces, hyphens, parens
		latinRe := regexp.MustCompile(`[A-Za-z\x{00C0}-\x{024F}\s\-()\[\]]+`)
		parts := latinRe.FindAllString(text, -1)
		text = strings.Join(parts, "")
		text = strings.ReplaceAll(text, "()", "")
		text = strings.TrimSpace(text)
	}

	// Fix spacing around punctuation
	text = regexp.MustCompile(`\(\s+`).ReplaceAllString(text, "(")
	text = regexp.MustCompile(`\s+\)`).ReplaceAllString(text, ")")
	text = regexp.MustCompile(`\s+([*,;:?.])`).ReplaceAllString(text, "$1")

	// NFC normalization
	text = norm.NFC.String(text)

	// Collapse multiple spaces
	text = regexp.MustCompile(`\s+`).ReplaceAllString(text, " ")
	text = strings.TrimSpace(text)

	return text
}

type Page struct {
	URL      string
	LangName string
}

// GetSwadeshPages crawls the Wiktionary Swadesh list category and returns all pages.
func GetSwadeshPages() []Page {
	var pages []Page
	seen := map[string]bool{}

	url := BASE + "/wiki/Category:Swadesh_lists_by_language"

	nextPageRe := regexp.MustCompile(`(?i)next\s+(page|200)`)

	for url != "" {
		fmt.Printf("Crawling Category Page: %s\n", url)

		doc, err := fetchHTML(url)
		if err != nil {
			fmt.Printf("Error fetching %s: %v\n", url, err)
			break
		}

		// Find all <a> tags inside .mw-category
		var nextURL string
		var walk func(*html.Node, bool)
		walk = func(n *html.Node, inCategory bool) {
			if n.Type == html.ElementNode && n.Data == "div" {
				for _, a := range n.Attr {
					if a.Key == "class" && strings.Contains(a.Val, "mw-category") {
						inCategory = true
					}
				}
			}
			if n.Type == html.ElementNode && n.Data == "a" {
				href := attrVal(n, "href")
				text := extractText(n)
				if inCategory && strings.HasPrefix(href, "/wiki/Appendix:") && strings.Contains(href, "Swadesh") {
					langName := strings.TrimSpace(strings.Split(strings.ReplaceAll(text, "Appendix:", ""), "Swadesh")[0])
					fullURL := BASE + href
					if !seen[fullURL] {
						seen[fullURL] = true
						pages = append(pages, Page{URL: fullURL, LangName: langName})
					}
				}
				// Detect "next page" / "next 200" link
				if nextPageRe.MatchString(text) {
					if href != "" {
						nextURL = BASE + href
					}
				}
			}
			for c := n.FirstChild; c != nil; c = c.NextSibling {
				walk(c, inCategory)
			}
		}
		walk(doc, false)

		url = nextURL
	}

	return pages
}

type LanguageData struct {
	LangName string
	Entries  []map[string]string
}

var blacklist = []string{
	"no", "no.", "№", "number", "example", "term?",
	"ipa", "transcription", "phonetic", "transliteration",
	"notes", "gloss", "reconstruction", "cognate", "literal",
}

// ParsePage parses a single Wiktionary Swadesh list page into structured entries.
func ParsePage(url, langName string) LanguageData {
	doc, err := fetchHTML(url)
	if err != nil {
		fmt.Printf("Error fetching %s: %v\n", url, err)
		return LanguageData{}
	}

	// Find the first wikitable
	table := findNode(doc, func(n *html.Node) bool {
		return n.Type == html.ElementNode && n.Data == "table" &&
			strings.Contains(attrVal(n, "class"), "wikitable")
	})
	if table == nil {
		return LanguageData{}
	}

	rows := findNodes(table, func(n *html.Node) bool {
		return n.Type == html.ElementNode && n.Data == "tr"
	})
	if len(rows) == 0 {
		return LanguageData{}
	}

	// Parse header row
	headerCells := findNodes(rows[0], func(n *html.Node) bool {
		return n.Type == html.ElementNode && (n.Data == "th" || n.Data == "td")
	})
	colNames := make([]string, len(headerCells))
	for i, cell := range headerCells {
		colNames[i] = CleanText(extractText(cell), true)
	}

	idxEng := -1
	var targetIndices []int
	for i, name := range colNames {
		nameLow := strings.ToLower(name)
		if strings.Contains(nameLow, "english") {
			idxEng = i
			continue
		}
		isBlacklisted := name == ""
		for _, term := range blacklist {
			if strings.Contains(nameLow, term) {
				isBlacklisted = true
				break
			}
		}
		if !isBlacklisted {
			targetIndices = append(targetIndices, i)
		}
	}
	if idxEng == -1 {
		idxEng = 1
	}

	var entries []map[string]string
	for _, row := range rows[1:] {
		cols := findNodes(row, func(n *html.Node) bool {
			return n.Type == html.ElementNode && (n.Data == "td" || n.Data == "th")
		})

		maxIdx := idxEng
		for _, idx := range targetIndices {
			if idx > maxIdx {
				maxIdx = idx
			}
		}
		if len(cols) <= maxIdx {
			continue
		}

		englishVal := CleanText(extractText(cols[idxEng]), false)
		if englishVal == "" {
			continue
		}

		entry := map[string]string{"english": englishVal}
		for _, idx := range targetIndices {
			if idx >= len(cols) {
				continue
			}
			wordVal := CleanText(extractText(cols[idx]), false)
			if wordVal == "" || wordVal == "-" || wordVal == "–" || wordVal == "?" || wordVal == "？" {
				continue
			}
			key := fmt.Sprintf("col_%d", idx)
			if colNames[idx] != "" {
				key = strings.ToLower(colNames[idx])
			}
			entry[key] = wordVal
		}

		if len(entry) > 1 {
			entries = append(entries, entry)
		}
	}

	return LanguageData{LangName: langName, Entries: entries}
}

// --- HTML helpers ---

func fetchHTML(url string) (*html.Node, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	for key, vals := range scraperHeader {
		for _, v := range vals {
			req.Header.Set(key, v)
		}
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	return html.Parse(strings.NewReader(string(body)))
}

func attrVal(n *html.Node, key string) string {
	for _, a := range n.Attr {
		if a.Key == key {
			return a.Val
		}
	}
	return ""
}

func extractText(n *html.Node) string {
	var sb strings.Builder
	var walk func(*html.Node)
	walk = func(n *html.Node) {
		if n.Type == html.TextNode {
			sb.WriteString(n.Data)
		}
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			walk(c)
		}
	}
	walk(n)
	// Remove non-printable characters
	return strings.Map(func(r rune) rune {
		if unicode.IsPrint(r) || r == ' ' {
			return r
		}
		return -1
	}, sb.String())
}

func findNode(n *html.Node, match func(*html.Node) bool) *html.Node {
	if match(n) {
		return n
	}
	for c := n.FirstChild; c != nil; c = c.NextSibling {
		if found := findNode(c, match); found != nil {
			return found
		}
	}
	return nil
}

func findNodes(n *html.Node, match func(*html.Node) bool) []*html.Node {
	var results []*html.Node
	var walk func(*html.Node)
	walk = func(n *html.Node) {
		if match(n) {
			results = append(results, n)
			return // don't descend into matched node (e.g. nested rows)
		}
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			walk(c)
		}
	}
	walk(n)
	return results
}
