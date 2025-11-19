# cython: language_level=3

from cython.parallel import prange
from libc.stdlib cimport malloc, free
from libc.string cimport strcmp
cimport openmp
import multiprocessing

# Simple hash function for strings
cdef unsigned long hash_string(const char* s) nogil:
    cdef unsigned long hash_val = 5381
    cdef int c
    while s[0] != 0:
        c = s[0]
        hash_val = ((hash_val << 5) + hash_val) + c
        s += 1
    return hash_val

# C-compatible hash table structure
cdef struct HashEntry:
    char* key
    int exists

cdef struct HashTable:
    HashEntry* entries
    size_t capacity
    size_t size

# Create hash table from Python dict keys
cdef HashTable* create_hash_table(dict py_dict) except NULL:
    cdef HashTable* ht = <HashTable*>malloc(sizeof(HashTable))
    if ht == NULL:
        raise MemoryError()
    
    # Use 2x size for better distribution
    cdef size_t dict_size = len(py_dict)
    ht.capacity = dict_size * 2
    ht.size = dict_size
    ht.entries = <HashEntry*>malloc(ht.capacity * sizeof(HashEntry))
    
    if ht.entries == NULL:
        free(ht)
        raise MemoryError()
    
    # Initialize all entries
    cdef size_t i
    for i in range(ht.capacity):
        ht.entries[i].key = NULL
        ht.entries[i].exists = 0
    
    # Insert keys from dict
    cdef bytes key_bytes
    cdef const char* key_cstr
    cdef unsigned long hash_val
    cdef size_t index

    # Other vars
    cdef size_t key_len
    
    for key in py_dict:
        key_bytes = key.encode('utf-8')
        key_cstr = key_bytes
        
        # Find slot using linear probing
        hash_val = hash_string(key_cstr)
        index = hash_val % ht.capacity
        
        while ht.entries[index].exists:
            index = (index + 1) % ht.capacity
        
        # Allocate and copy string
        key_len = len(key_bytes)
        ht.entries[index].key = <char*>malloc((key_len + 1) * sizeof(char))
        if ht.entries[index].key == NULL:
            free_hash_table(ht)
            raise MemoryError()
        
        # Copy string
        for i in range(key_len):
            ht.entries[index].key[i] = key_cstr[i]
        ht.entries[index].key[key_len] = 0  # null terminator
        ht.entries[index].exists = 1
    
    return ht

# Free hash table memory
cdef void free_hash_table(HashTable* ht) noexcept nogil:
    if ht != NULL:
        if ht.entries != NULL:
            for i in range(ht.capacity):
                if ht.entries[i].key != NULL:
                    free(ht.entries[i].key)
            free(ht.entries)
        free(ht)

# Lookup in hash table (thread-safe for reads)
cdef int hash_table_contains(HashTable* ht, const char* key) nogil:
    cdef unsigned long hash_val = hash_string(key)
    cdef size_t index = hash_val % ht.capacity
    cdef size_t start_index = index
    
    while ht.entries[index].exists:
        if strcmp(ht.entries[index].key, key) == 0:
            return 1
        index = (index + 1) % ht.capacity
        if index == start_index:  # Full circle
            break
    
    return 0

# Example expensive transformation (replace with your actual function)
cdef void transform_string(const char* input, char* output, size_t max_len) noexcept nogil:
    """
    Replace this with your actual expensive transformation.
    For demo: reverse the string
    """
    cdef size_t i = 0
    cdef size_t len_input = 0
    
    # Find length
    while input[len_input] != 0:
        len_input += 1
    
    # Reverse (example transformation)
    for i in range(len_input):
        if i < max_len - 1:
            output[i] = input[len_input - 1 - i]
    
    output[min(len_input, max_len - 1)] = 0  # null terminator

from libc.string cimport strdup

def parallel_lookup(list strings, dict lookup_dict, int num_threads=0):
    cdef int n_threads
    if num_threads == 0:
        n_threads = multiprocessing.cpu_count()
    elif num_threads == -1:
        n_threads = max(1, multiprocessing.cpu_count() - 1)
    else:
        n_threads = num_threads
    
    cdef HashTable* ht = create_hash_table(lookup_dict)
    cdef int n_strings = len(strings)
    cdef int i
    
    # 1. Keep Python objects alive
    cdef list bytes_list = [s.encode('utf-8') for s in strings]
    
    # 2. Create C-array for inputs
    cdef char** input_ptrs = <char**>malloc(n_strings * sizeof(char*))
    if input_ptrs == NULL:
        free_hash_table(ht)
        raise MemoryError()

    # 3. Populate pointers
    for i in range(n_strings):
        input_ptrs[i] = bytes_list[i] 
    
    # 4. Result array
    cdef int* results = <int*>malloc(n_strings * sizeof(int))
    if results == NULL:
        free(input_ptrs)
        free_hash_table(ht)
        raise MemoryError()

    cdef int max_transform_len = 1000 
    cdef char* transformed

    try:
        # 5. Parallel loop (PURE C, NO GIL)
        for i in prange(n_strings, nogil=True, num_threads=n_threads):
            transformed = <char*>malloc(max_transform_len * sizeof(char))
            if transformed != NULL:
                transform_string(input_ptrs[i], transformed, max_transform_len)
                results[i] = hash_table_contains(ht, transformed)
                free(transformed)
            else:
                results[i] = 0
        
        # 6. Collect results
        matches = []
        for i in range(n_strings):
            if results[i]:
                matches.append(i)
        return matches
    
    finally:
        free(input_ptrs)
        free(results)
        free_hash_table(ht)

def parallel_lookup_with_values(list strings, dict lookup_dict, int num_threads=0):
    cdef int n_threads
    if num_threads == 0:
        n_threads = multiprocessing.cpu_count()
    elif num_threads == -1:
        n_threads = max(1, multiprocessing.cpu_count() - 1)
    else:
        n_threads = num_threads
    
    cdef HashTable* ht = create_hash_table(lookup_dict)
    cdef int n_strings = len(strings)
    cdef int i
    
    # Pre-convert inputs
    cdef list bytes_list = [s.encode('utf-8') for s in strings]
    cdef char** input_ptrs = <char**>malloc(n_strings * sizeof(char*))
    
    # Output array to hold SUCCESSFUL transformed strings (NULL if failed)
    cdef char** output_ptrs = <char**>malloc(n_strings * sizeof(char*))
    
    if input_ptrs == NULL or output_ptrs == NULL:
        free(input_ptrs)
        free(output_ptrs)
        free_hash_table(ht)
        raise MemoryError()

    for i in range(n_strings):
        input_ptrs[i] = bytes_list[i]
        output_ptrs[i] = NULL # Initialize outputs to NULL

    cdef int max_transform_len = 1000
    cdef char* temp_buf
    cdef str py_transformed
    
    try:
        # Parallel Loop: Pure C, No GIL, No Python Objects
        for i in prange(n_strings, nogil=True, num_threads=n_threads):
            temp_buf = <char*>malloc(max_transform_len * sizeof(char))
            if temp_buf != NULL:
                transform_string(input_ptrs[i], temp_buf, max_transform_len)
                
                if hash_table_contains(ht, temp_buf):
                    # If found, save a copy of the transformed string to output
                    # We must copy it because temp_buf is freed below
                    output_ptrs[i] = strdup(temp_buf)
                
                free(temp_buf)
        
        # Serial Loop: Re-enter Python to build the result list
        matches = []
        for i in range(n_strings):
            if output_ptrs[i] != NULL:
                # Convert C string back to Python string
                py_transformed = output_ptrs[i].decode('utf-8')
                matches.append((strings[i], py_transformed, lookup_dict[py_transformed]))
                # Free the copy we made with strdup
                free(output_ptrs[i])
        
        return matches
    
    finally:
        free(input_ptrs)
        free(output_ptrs)
        free_hash_table(ht)