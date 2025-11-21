import os
import sys

def print_directory_structure_filtered(root_dir, ignore_dirs=['__pycache__'], hide_files_in=[]):
    """
    Recursively prints the directory structure with filters.

    Args:
        root_dir (str): The starting directory path.
        ignore_dirs (list): A list of directory names to completely ignore.
        hide_files_in (list): A list of directory names where files should not be printed.
    """
    if not os.path.isdir(root_dir):
        print(f"Error: '{root_dir}' is not a valid directory.", file=sys.stderr)
        return

    print(f"**{os.path.basename(root_dir)}/**")

    def generate_tree(dir_path, prefix=''):
        current_dir_name = os.path.basename(dir_path)
        
        try:
            # Filter out ignored directories immediately from the contents list
            contents = [
                c for c in os.listdir(dir_path) 
                if c not in ignore_dirs and not os.path.islink(os.path.join(dir_path, c))
            ]
        except PermissionError as e:
            print(f"{prefix}└── [Permission Denied: {e.filename}]")
            return
        
        # Separate directories and files
        dirs = sorted([c for c in contents if os.path.isdir(os.path.join(dir_path, c))])
        
        # Only include files if the current directory is NOT in the hide_files_in list
        if current_dir_name in hide_files_in:
             files = []
        else:
             files = sorted([c for c in contents if os.path.isfile(os.path.join(dir_path, c))])
        
        all_entries = dirs + files
        
        for i, entry in enumerate(all_entries):
            is_last = (i == len(all_entries) - 1)
            
            connector = '└── ' if is_last else '├── '
            full_path = os.path.join(dir_path, entry)
            
            is_dir = os.path.isdir(full_path)
            
            # Print the current entry
            print(prefix + connector + entry + ('/' if is_dir else ''))
            
            # If it's a directory, recursively call the generator
            if is_dir:
                new_prefix = prefix + ('    ' if is_last else '│   ')
                yield from generate_tree(full_path, new_prefix)

    # Start the traversal
    for _ in generate_tree(root_dir):
        pass

# --- Example Usage ---

# 1. Set the starting directory (e.g., the current directory)
START_PATH = '.' 

# 2. Define the directories to IGNORE completely
DIRS_TO_IGNORE = ['__pycache__', '.git', 'node_modules']

# 3. Define directories where only SUBDIRECTORIES should be shown (files are hidden)
# The user asked to hide files in 'src', so we include it here.
FOLDERS_TO_HIDE_FILES = ['dist'] 

print_directory_structure_filtered(
    root_dir=START_PATH, 
    ignore_dirs=DIRS_TO_IGNORE,
    hide_files_in=FOLDERS_TO_HIDE_FILES
)