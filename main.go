package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// InputData matches the JSON structure
type InputData struct {
	AllNames      []string            `json:"all_names"`
	WordToMatches map[string][]string `json:"word_to_matches"`
	PairToNames   map[string][]string `json:"pair_to_names"`
}

// --- INTERNING SYSTEM ---
// We convert strings to uint32 to avoid string hashing in the hot path
type Dictionary struct {
	strToInt map[string]uint32
	intToStr []string
}

func NewDictionary() *Dictionary {
	return &Dictionary{
		strToInt: make(map[string]uint32),
		intToStr: make([]string, 0),
	}
}

func (d *Dictionary) GetID(s string) uint32 {
	if id, ok := d.strToInt[s]; ok {
		return id
	}
	id := uint32(len(d.intToStr))
	d.intToStr = append(d.intToStr, s)
	d.strToInt[s] = id
	return id
}

func (d *Dictionary) GetStr(id uint32) string {
	return d.intToStr[id]
}

// --- DATA STRUCTURES ---

type ProcessedData struct {
	// Names converted to lists of word IDs
	NameWords map[string][]uint32
	// Matches converted to lists of word IDs
	WordToMatches map[uint32][]uint32
	// Tradeouts converted to lists of word IDs
	TradeoutSets map[uint32][]uint32
	// Pair keys remain strings as they are composite keys, 
	// but we could optimize this too if needed.
	PairToNames map[string][]string
	
	Dict *Dictionary
}

var namesProcessed uint64

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: ./pair_comparator <input.json> <output.txt>")
		return
	}
	inputPath := os.Args[1]
	outputPath := os.Args[2]

	// 1. Load Data
	fmt.Println("Loading JSON data...")
	rawData, err := loadData(inputPath)
	if err != nil {
		panic(err)
	}

	// 2. Preprocess & Intern Strings (The Speedup Layer)
	fmt.Println("Interning strings to integers...")
	data := preprocessData(rawData)
	
	totalNames := len(rawData.AllNames)
	allNamesList := rawData.AllNames
	
	// Clear raw data to free massive RAM
	rawData = nil
	runtime.GC()

	// 3. Setup Workers
	numWorkers := runtime.NumCPU()
	jobs := make(chan string, 1000)
	var wg sync.WaitGroup

	tempDir, err := os.MkdirTemp("", "name_match_batches")
	if err != nil {
		panic(err)
	}
	defer os.RemoveAll(tempDir)

	fmt.Printf("Processing %d names with %d workers...\n", totalNames, numWorkers)

	// Start Monitor
	doneMonitor := make(chan bool)
	go func() {
		ticker := time.NewTicker(1 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-doneMonitor:
				return
			case <-ticker.C:
				current := atomic.LoadUint64(&namesProcessed)
				percent := (float64(current) / float64(totalNames)) * 100
				fmt.Printf("\rProgress: %d / %d (%.2f%%)", current, totalNames, percent)
			}
		}
	}()

	// Launch Workers
	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()
			// Pass the dictionary size to pre-allocate buffers
			processBatch(workerID, tempDir, jobs, data, len(data.Dict.intToStr))
		}(i)
	}

	for _, name := range allNamesList {
		jobs <- name
	}
	close(jobs)

	wg.Wait()
	doneMonitor <- true
	fmt.Printf("\rProgress: %d / %d (100.00%%)\n", totalNames, totalNames)

	fmt.Println("Merging results...")
	if err := mergeFiles(tempDir, outputPath); err != nil {
		panic(err)
	}
	fmt.Println("Done.")
}

func preprocessData(raw *InputData) *ProcessedData {
	dict := NewDictionary()
	
	// Convert WordToMatches
	w2m := make(map[uint32][]uint32, len(raw.WordToMatches))
	tradeouts := make(map[uint32][]uint32)

	for k, v := range raw.WordToMatches {
		kID := dict.GetID(k)
		
		// Convert match list to IDs
		matchIDs := make([]uint32, len(v))
		for i, m := range v {
			matchIDs[i] = dict.GetID(m)
		}
		w2m[kID] = matchIDs

		// Logic: v if len(k) != 1 else set(k)
		if len(k) != 1 {
			// Use the slice we just created (read-only shared is fine)
			tradeouts[kID] = matchIDs
		} else {
			tradeouts[kID] = []uint32{kID}
		}
	}

	// Pre-tokenize all names so we don't do strings.Fields repeatedly
	nameWords := make(map[string][]uint32, len(raw.AllNames))
	for _, name := range raw.AllNames {
		parts := strings.Fields(name)
		ids := make([]uint32, len(parts))
		for i, p := range parts {
			ids[i] = dict.GetID(p)
		}
		nameWords[name] = ids
	}

	return &ProcessedData{
		NameWords:     nameWords,
		WordToMatches: w2m,
		TradeoutSets:  tradeouts,
		PairToNames:   raw.PairToNames,
		Dict:          dict,
	}
}

func processBatch(
	id int,
	tempDir string,
	jobs <-chan string,
	data *ProcessedData,
	dictSize int,
) {
	tempFileName := filepath.Join(tempDir, fmt.Sprintf("worker_%d.txt", id))
	f, _ := os.Create(tempFileName)
	defer f.Close()
	writer := bufio.NewWriter(f)

	matchesBuffer := make([]uint64, dictSize)
	
	// FIX: Start higher to avoid 0 issues, though unlikely
	currentGen := uint64(10) 

	seenMatches := make(map[string]struct{})

	for name := range jobs {
		atomic.AddUint64(&namesProcessed, 1)
		
		namePartsIDs := data.NameWords[name]
		if len(namePartsIDs) < 2 {
			continue
		}
		
		for k := range seenMatches { delete(seenMatches, k) }

		pairs := buildExpandedPairMappings(namePartsIDs, data.TradeoutSets, data.Dict)

		for _, pairStr := range pairs {
			otherNames, exists := data.PairToNames[pairStr]
			if !exists {
				continue
			}

			for _, other := range otherNames {
				if other == name {
					continue
				}
				
				n1, n2 := name, other
				if n1 > n2 {
					n1, n2 = n2, n1
				}

				ids1 := data.NameWords[n1]
				ids2 := data.NameWords[n2]

				// FIX: Increment by 2!
				// We use (gen) for Step 1 and (gen+1) for Step 2
				// This ensures the next iteration (gen+2) hits clean RAM.
				currentGen += 2
				
				if validateOptimized(ids1, ids2, data.WordToMatches, matchesBuffer, currentGen) {
					matchStr := fmt.Sprintf("('%s', '%s')", n1, n2)
					if _, seen := seenMatches[matchStr]; !seen {
						seenMatches[matchStr] = struct{}{}
						writer.WriteString(matchStr + "\n")
					}
				}
			}
		}
		
		if writer.Buffered() > 4096 {
			writer.Flush()
		}
	}
	writer.Flush()
}

// validateOptimized performs the check with ZERO allocations
func validateOptimized(
	partsA []uint32,
	partsB []uint32,
	wordToMatches map[uint32][]uint32,
	matchesBuffer []uint64,
	gen uint64,
) bool {
	lenA := len(partsA)
	lenB := len(partsB)

	// --- Step 1: Check Mismatches in A (relative to B) ---
	// We use 'gen' for this phase
	
	// Populate Buffer with matches from B
	for _, wordID := range partsB {
		if matches, ok := wordToMatches[wordID]; ok {
			for _, matchID := range matches {
				// Bounds check to be safe, though dictSize should cover it
				if int(matchID) < len(matchesBuffer) {
					matchesBuffer[matchID] = gen
				}
			}
		}
	}

	// Check A against Buffer
	mismatchesA := 0
	for i := 0; i < len(partsA); i++ {
		wID := partsA[i]
		// Naive dupe check
		isDupe := false
		for k := 0; k < i; k++ {
			if partsA[k] == wID {
				isDupe = true
				break
			}
		}
		if isDupe { continue }

		if int(wID) < len(matchesBuffer) {
			if matchesBuffer[wID] != gen {
				mismatchesA++
			}
		} else {
			mismatchesA++
		}
	}

	// --- Step 2: Check Mismatches in B (relative to A) ---
	// FIX: Use 'gen + 1' for this phase so we don't have to clear the buffer
	gen2 := gen + 1
	
	// Populate Buffer with matches from A
	for _, wordID := range partsA {
		if matches, ok := wordToMatches[wordID]; ok {
			for _, matchID := range matches {
				if int(matchID) < len(matchesBuffer) {
					matchesBuffer[matchID] = gen2
				}
			}
		}
	}

	// Check B against Buffer
	mismatchesB := 0
	for i := 0; i < len(partsB); i++ {
		wID := partsB[i]
		isDupe := false
		for k := 0; k < i; k++ {
			if partsB[k] == wID {
				isDupe = true
				break
			}
		}
		if isDupe { continue }

		if int(wID) < len(matchesBuffer) {
			if matchesBuffer[wID] != gen2 {
				mismatchesB++
			}
		} else {
			mismatchesB++
		}
	}

	// --- Step 3: Thresholds (Variable Mapping Correction) ---
	// Python: num_mismatches_a = len(set(name_b) - matches_of_a)
	// Go: mismatchesA = words in A - matches of B (This maps to Python's mismatches_b)
	
	// Python: if (len_a == 3) and (num_mismatches_a) and (len_b >= 3): return False
	// (Where len_a is name_b length). 
	// So strict translation: if len(B)==3 and mismatches(in B relative to A) > 0 and len(A) >= 3
	
	if lenB == 3 && mismatchesB > 0 && lenA >= 3 {
		return false
	}
	if lenA == 3 && mismatchesA > 0 && lenB >= 3 {
		return false
	}
	
	// Python: if (len_b - num_mismatches_b < 2) or (len_a - num_mismatches_a < 2)
	// Python len_b is Name A. Python num_mismatches_b is mismatches in A.
	
	if (lenA - mismatchesA < 2) || (lenB - mismatchesB < 2) {
		return false
	}

	return true
}

func buildExpandedPairMappings(parts []uint32, tradeoutSets map[uint32][]uint32, dict *Dictionary) []string {
	// 1. Position Options (IDs)
	positionOptions := make([][]uint32, len(parts))
	for i, wordID := range parts {
		opts := make([]uint32, 0, 5)
		opts = append(opts, wordID)
		
		if replacements, ok := tradeoutSets[wordID]; ok {
			opts = append(opts, replacements...)
		}
		
		// Sort and Unique IDs (This is internal for the 'seenPairs' dedupe logic, 
        // so sorting by ID here is fine and faster)
		sort.Slice(opts, func(a, b int) bool { return opts[a] < opts[b] })
		
		uniqueOpts := opts[:0]
		var last uint32
		for j, v := range opts {
			if j == 0 || v != last {
				uniqueOpts = append(uniqueOpts, v)
				last = v
			}
		}
		positionOptions[i] = uniqueOpts
	}

	// 2. Pairs
	seenPairs := make(map[string]struct{})
	var results []string
	var sb strings.Builder 

	for i := 0; i < len(positionOptions); i++ {
		for j := i + 1; j < len(positionOptions); j++ {
			
			// Deduplication Logic (Internal to Go, can use ID sorting)
			sb.Reset()
			writeIDs(&sb, positionOptions[i])
			s1 := sb.String()
			sb.Reset()
			writeIDs(&sb, positionOptions[j])
			s2 := sb.String()

			first, second := s1, s2
			if first > second {
				first, second = second, first
			}
			key := first + "|" + second
			
			if _, ok := seenPairs[key]; ok {
				continue
			}
			seenPairs[key] = struct{}{}

			// Generation Logic (External Map Lookup - MUST MATCH PYTHON)
			for _, wI := range positionOptions[i] {
				for _, wJ := range positionOptions[j] {
                    // Retrieve the actual strings
					str1 := dict.GetStr(wI)
					str2 := dict.GetStr(wJ)

                    // FIX: Sort by STRING value, not ID value
                    if str1 > str2 {
                        str1, str2 = str2, str1
                    }
					
					results = append(results, str1 + "_" + str2)
				}
			}
		}
	}
	return results
}

func writeIDs(sb *strings.Builder, ids []uint32) {
	for k, id := range ids {
		if k > 0 {
			sb.WriteString(",")
		}
		fmt.Fprintf(sb, "%d", id)
	}
}

func loadData(path string) (*InputData, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var data InputData
	decoder := json.NewDecoder(file)
	if err := decoder.Decode(&data); err != nil {
		return nil, err
	}
	return &data, nil
}

func mergeFiles(tempDir, finalOutput string) error {
	outFile, err := os.Create(finalOutput)
	if err != nil {
		return err
	}
	defer outFile.Close()
	bufWriter := bufio.NewWriter(outFile)
	defer bufWriter.Flush()
	files, err := os.ReadDir(tempDir)
	if err != nil {
		return err
	}
	for _, fileEntry := range files {
		path := filepath.Join(tempDir, fileEntry.Name())
		in, err := os.Open(path)
		if err != nil {
			return err
		}
		_, err = io.Copy(bufWriter, in)
		in.Close()
	}
	return nil
}