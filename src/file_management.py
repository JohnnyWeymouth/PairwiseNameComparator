import os
import heapq
import tempfile
import datetime
import uuid
from pathlib import Path

def create_tempdir_file(file_extension: str = 'txt') -> Path:
    temp_dir = Path(tempfile.gettempdir())
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H_%M_%S") + f"_{uuid.uuid4()}"
    output_path = temp_dir / f"output_{timestamp}.{file_extension}"
    output_path.touch()
    return output_path

def remove_duplicates_external_sort(raw_output_file: Path, chunk_size=10_000) -> Path:
    """Remove duplicates using external sorting - works with limited memory"""
    dedupped_output_file = create_tempdir_file()
    
    # Phase 1: Split into sorted chunks
    chunk_files = []
    with open(raw_output_file, 'r') as f:
        while True:
            lines = []
            for _ in range(chunk_size):
                line = f.readline()
                if not line:
                    break
                lines.append(line.rstrip('\n'))
            
            if not lines:
                break
            
            # Sort and deduplicate this chunk
            lines = sorted(set(lines))
            
            # Write to temp file
            temp = tempfile.NamedTemporaryFile(mode='w', delete=False)
            chunk_files.append(temp.name)
            for line in lines:
                temp.write(line + '\n')
            temp.close()
    
    # Phase 2: Merge sorted chunks
    with open(dedupped_output_file, 'w') as out:
        # Open all chunk files
        files = [open(f, 'r') for f in chunk_files]
        
        # Use heap for efficient merging
        heap = []
        for i, f in enumerate(files):
            line = f.readline().rstrip('\n')
            if line:
                heapq.heappush(heap, (line, i))
        
        last_written = None
        while heap:
            line, file_idx = heapq.heappop(heap)
            
            # Only write if different from last (removes duplicates)
            if line != last_written:
                out.write(line + '\n')
                last_written = line
            
            # Read next line from same file
            next_line = files[file_idx].readline().rstrip('\n')
            if next_line:
                heapq.heappush(heap, (next_line, file_idx))
        
        # Cleanup
        for f in files:
            f.close()
        for chunk_file in chunk_files:
            os.unlink(chunk_file)

        # Return the path to the dedupped file
        print(dedupped_output_file)
        return dedupped_output_file
