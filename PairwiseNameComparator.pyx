# cython: language_level=3

from cython.parallel import prange
from libc.stdlib cimport malloc, free, realloc
from libc.string cimport strcmp, strcpy, strlen
cimport openmp
import multiprocessing
from collections import defaultdict

# ============================================================================
# C-LEVEL DATA STRUCTURES (No GIL Required)
# ============================================================================

cdef struct StringSet:
    char** strings
    int size
    int capacity

cdef struct WordTradeouts:
    char* word
    StringSet* tradeouts

cdef struct TradeoutTable:
    WordTradeouts* entries
    size_t capacity
    size_t size

cdef struct NamePair:
    char* name1
    char* name2

cdef struct NamePairSet:
    NamePair* pairs
    int size
    int capacity

# ============================================================================
# STRING SET OPERATIONS (Thread-safe for reads)
# ============================================================================

cdef StringSet* create_string_set(int initial_capacity) nogil:
    cdef StringSet* ss = <StringSet*>malloc(sizeof(StringSet))
    if ss == NULL:
        return NULL
    ss.size = 0
    ss.capacity = initial_capacity
    ss.strings = <char**>malloc(initial_capacity * sizeof(char*))
    if ss.strings == NULL:
        free(ss)
        return NULL
    return ss

cdef void free_string_set(StringSet* ss) noexcept nogil:
    if ss != NULL:
        if ss.strings != NULL:
            for i in range(ss.size):
                if ss.strings[i] != NULL:
                    free(ss.strings[i])
            free(ss.strings)
        free(ss)

cdef int string_set_contains(StringSet* ss, const char* s) nogil:
    """Check if string is in set"""
    cdef int i
    for i in range(ss.size):
        if strcmp(ss.strings[i], s) == 0:
            return 1
    return 0

# ============================================================================
# HASH FUNCTIONS
# ============================================================================

cdef unsigned long hash_string(const char* s) nogil:
    cdef unsigned long hash_val = 5381
    cdef int c
    while s[0] != 0:
        c = s[0]
        hash_val = ((hash_val << 5) + hash_val) + c
        s += 1
    return hash_val

# ============================================================================
# TRADEOUT TABLE (Read-only after construction)
# ============================================================================

cdef TradeoutTable* create_tradeout_table(dict word_to_matches) except NULL:
    """Build C-level tradeout table from Python dict"""
    cdef TradeoutTable* tt = <TradeoutTable*>malloc(sizeof(TradeoutTable))
    if tt == NULL:
        raise MemoryError()
    
    cdef size_t dict_size = len(word_to_matches)
    tt.capacity = dict_size * 2
    tt.size = dict_size
    tt.entries = <WordTradeouts*>malloc(tt.capacity * sizeof(WordTradeouts))
    
    if tt.entries == NULL:
        free(tt)
        raise MemoryError()
    
    # Initialize
    cdef size_t i
    for i in range(tt.capacity):
        tt.entries[i].word = NULL
        tt.entries[i].tradeouts = NULL
    
    # Populate from Python dict
    cdef bytes word_bytes, match_bytes
    cdef const char* word_cstr
    cdef const char* match_cstr
    cdef unsigned long hash_val
    cdef size_t index, word_len, match_len
    cdef StringSet* tradeout_set
    
    for word, matches in word_to_matches.items():
        word_bytes = word.encode('utf-8')
        word_cstr = word_bytes
        word_len = len(word_bytes)
        
        # Find slot
        hash_val = hash_string(word_cstr)
        index = hash_val % tt.capacity
        while tt.entries[index].word != NULL:
            index = (index + 1) % tt.capacity
        
        # Copy word
        tt.entries[index].word = <char*>malloc((word_len + 1) * sizeof(char))
        if tt.entries[index].word == NULL:
            free_tradeout_table(tt)
            raise MemoryError()
        strcpy(tt.entries[index].word, word_cstr)
        
        # Create tradeout set
        tradeout_set = create_string_set(len(matches) + 1)
        if tradeout_set == NULL:
            free_tradeout_table(tt)
            raise MemoryError()
        
        # Add the word itself (for single-letter words special case)
        if word_len == 1:
            tradeout_set.strings[tradeout_set.size] = <char*>malloc(2 * sizeof(char))
            strcpy(tradeout_set.strings[tradeout_set.size], word_cstr)
            tradeout_set.size += 1
        
        # Add matches
        for match in matches:
            match_bytes = match.encode('utf-8')
  
            match_cstr = match_bytes
            match_len = len(match_bytes)
            
            if tradeout_set.size >= tradeout_set.capacity:
                break
            
            tradeout_set.strings[tradeout_set.size] = <char*>malloc((match_len + 1) * sizeof(char))
 
            if tradeout_set.strings[tradeout_set.size] == NULL:
                continue
            strcpy(tradeout_set.strings[tradeout_set.size], match_cstr)
            tradeout_set.size += 1
        
        tt.entries[index].tradeouts = tradeout_set
    
    return tt

cdef void free_tradeout_table(TradeoutTable* tt) noexcept nogil:
    if tt != NULL:
    
        if tt.entries != NULL:
            for i in range(tt.capacity):
                if tt.entries[i].word != NULL:
                    free(tt.entries[i].word)
                if tt.entries[i].tradeouts != NULL:
                    
                    free_string_set(tt.entries[i].tradeouts)
            free(tt.entries)
        free(tt)

cdef StringSet* tradeout_table_lookup(TradeoutTable* tt, const char* word) nogil:
    """Find tradeouts for a word (returns NULL if not found)"""
    cdef unsigned long hash_val = hash_string(word)
    cdef size_t index = hash_val % tt.capacity
    cdef size_t start_index = index
    
    while tt.entries[index].word != NULL:
        if strcmp(tt.entries[index].word, word) == 0:
          
            return tt.entries[index].tradeouts
        index = (index + 1) % tt.capacity
        if index == start_index:
            break
    
    return NULL

# ============================================================================
# STRING UTILITIES (No GIL)
# ============================================================================

cdef int count_words(const char* s) nogil:
    """Count space-separated words"""
    cdef int count = 0
    cdef int in_word = 0
    
    while s[0] != 0:
       
        if s[0] == 32:  # space
            in_word = 0
        elif not in_word:
            in_word = 1
            count += 1
        s += 1
    
    return count

cdef void extract_word(const char* s, int word_index, char* output, int max_len) noexcept nogil:
    """Extract nth word from space-separated string"""
 
    cdef int current_word = 0
    cdef int in_word = 0
    cdef int out_idx = 0
    cdef int i = 0
    
    output[0] = 0
    
    while s[i] != 0:
        if s[i] == 32:  # space
            if in_word and current_word == word_index:
                output[out_idx] = 0
                return
            in_word = 0
        else:
            if not in_word:
                current_word += 1
                in_word = 1
           
            if current_word == word_index + 1:
                if out_idx < max_len - 1:
                    output[out_idx] = s[i]
                    out_idx += 1
        i += 1
    
    output[out_idx] = 0

# ============================================================================
# VALIDATION LOGIC (No GIL)
# ============================================================================

cdef int validate_match(const char* name_a, const char* name_b, TradeoutTable* tt) nogil:
    """
    Validate that two names match according to the rules.
    
    NOTE: Increased word buffer size (1024) to mitigate risk of buffer overflow 
    if a word in an input name exceeds 255 characters.
    """
    cdef int len_a = count_words(name_a)
    cdef int len_b = count_words(name_b)
    
    if len_a < 2 or len_b < 2:
        return 0
    
    
    cdef char word_buf[1024] # FIX: Increased from 256 for buffer safety
    cdef int i, j
    cdef int matches_a_in_b = 0
    cdef int matches_b_in_a = 0
    cdef StringSet* tradeouts
    cdef char word_b[1024] # FIX: Increased from 256
    cdef char word_a[1024] # FIX: Increased from 256
    
    # Count how many words from A match words in B (via tradeouts)
    for i in range(len_a):
        extract_word(name_a, i, word_buf, 1024)
        
        # Check direct match
        for j in range(len_b):
            extract_word(name_b, j, word_b, 1024)
            if strcmp(word_buf, word_b) == 0:
                matches_a_in_b += 1
                break
        else:
            # Check via tradeouts
 
            tradeouts = tradeout_table_lookup(tt, word_buf)
            if tradeouts != NULL:
                for j in range(len_b):
                    extract_word(name_b, j, word_b, 1024)
                    if string_set_contains(tradeouts, word_b):
       
                        matches_a_in_b += 1
                        break
    
    # Count how many words from B match words in A
    for i in range(len_b):
        extract_word(name_b, i, word_buf, 1024)
        
        # Check direct match
  
        for j in range(len_a):
            
            extract_word(name_a, j, word_a, 1024)
            if strcmp(word_buf, word_a) == 0:
                matches_b_in_a += 1
                break
        else:
      
            # Check via tradeouts
            tradeouts = tradeout_table_lookup(tt, word_buf)
            if tradeouts != NULL:
                for j in range(len_a):
                    extract_word(name_a, j, word_a, 1024)
                   
                    if string_set_contains(tradeouts, word_a):
                        matches_b_in_a += 1
                        break
    
    cdef int num_mismatches_a = len_a - matches_a_in_b
    cdef int num_mismatches_b = len_b - matches_b_in_a
    
    # Apply rules
    if len_a == 3 and num_mismatches_a and len_b >= 3:
        return 0
    if len_b == 3 and num_mismatches_b and len_a >= 3:
        return 0
    if (len_b - num_mismatches_b < 2) or (len_a - num_mismatches_a < 2):
        return 0
    
    return 1

# ============================================================================
# PARALLEL MATCHING FUNCTION
# ============================================================================

def parallel_find_matches(list all_names, dict word_to_matches, dict pair_to_names, int num_threads=0): #
    """
    Find all valid name matches in parallel.
    Returns: list of tuples (name1, name2) where name1 < name2 lexicographically
    """
    cdef int n_threads
    cdef int i, j, tid
    
    if num_threads == 0:
        n_threads = multiprocessing.cpu_count()
    elif num_threads == -1:
        n_threads = max(1, multiprocessing.cpu_count() - 1)
    else:
        n_threads = num_threads
    
    
    # Build C tradeout table
    cdef TradeoutTable* tt = create_tradeout_table(word_to_matches)
    
    # Filter to names with 2+ words
    valid_names = [n for n in all_names if len(n.split()) >= 2]
    cdef int n_names = len(valid_names)
    
    # Pre-convert names to bytes
    cdef list bytes_list = [n.encode('utf-8') for n in valid_names]
    cdef char** name_ptrs = <char**>malloc(n_names * sizeof(char*))
    
    if name_ptrs == NULL:
 
        free_tradeout_table(tt)
        raise MemoryError()
    
    for i in range(n_names):
        name_ptrs[i] = bytes_list[i]
    
    # Per-thread result storage
    cdef NamePairSet** thread_results = <NamePairSet**>malloc(n_threads * sizeof(NamePairSet*))
    if thread_results == NULL:
        free(name_ptrs)
        free_tradeout_table(tt)
        raise MemoryError()
    
   
    for i in range(n_threads):
        thread_results[i] = <NamePairSet*>malloc(sizeof(NamePairSet))
        if thread_results[i] == NULL:
            free_tradeout_table(tt)
            free(name_ptrs)
            # Cannot safely free other thread_results; rely on finally block for cleanup
            raise MemoryError()
        thread_results[i].capacity = 1000
        thread_results[i].size = 0
   
        thread_results[i].pairs = <NamePair*>malloc(1000 * sizeof(NamePair))
    
    cdef NamePair* pair
    cdef int new_capacity
    cdef NamePair* new_pairs
    
    try:
        # PARALLEL LOOP: No GIL, Pure C
        # NOTE ON O(N^2) COMPLEXITY: The smart lookup logic using pair_to_names is not
        # implemented here in C. This loop is O(N^2) and may be slow for large N.
        # To fix this, a C-level hash map (PairMap) must be built outside the prange
        # and used inside the loop to look up candidate names.
        for i in prange(n_names, nogil=True, num_threads=n_threads, schedule='dynamic'):
            tid = openmp.omp_get_thread_num()
     
            # For each name, check against all other names
            for j in range(i + 1, n_names):
                if validate_match(name_ptrs[i], name_ptrs[j], tt):
                 
                    # Store valid match in thread-local storage
                    if thread_results[tid].size >= thread_results[tid].capacity:
                        # Reallocate
                        new_capacity = thread_results[tid].capacity * 2
                        new_pairs = <NamePair*>realloc(
                            thread_results[tid].pairs,
                            new_capacity * sizeof(NamePair)
                        )
                        
                        # CRITICAL FIX: Check for realloc failure
                        if new_pairs == NULL:
                            # Cannot proceed safely. Must acquire GIL to raise exception.
                            # Set current thread_results to NULL so finally block doesn't try to free bad pointer
                            thread_results[tid].pairs = NULL
                            with gil:
                                raise MemoryError("Failed to reallocate NamePairSet storage.")
                        
                        thread_results[tid].pairs = new_pairs
                        thread_results[tid].capacity = new_capacity
         
                    # Store the pair
                    pair = &thread_results[tid].pairs[thread_results[tid].size]
                    pair.name1 = name_ptrs[i]
   
                    pair.name2 = name_ptrs[j]
                    thread_results[tid].size += 1
        
        # SERIAL COLLECTION: Convert C results back to Python
        results = []
        for tid in range(n_threads):
           
            for i in range(thread_results[tid].size):
                name1 = thread_results[tid].pairs[i].name1.decode('utf-8')
                name2 = thread_results[tid].pairs[i].name2.decode('utf-8')
                results.append((name1, name2))
        
        return results
    
    finally:
        # Cleanup C memory
        for i in range(n_threads):
    
            if thread_results[i] != NULL:
                if thread_results[i].pairs != NULL: #
                    free(thread_results[i].pairs)
                free(thread_results[i])
        free(thread_results)
        free(name_ptrs)
        free_tradeout_table(tt)