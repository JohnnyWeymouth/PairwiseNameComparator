import os
import gc
import ast
import json
import random
import subprocess
import platform
from pathlib import Path
from typing import Callable

from rich.progress import track

from src.clean import clean_name
from src.word_to_matches import get_word_to_matches
from src.pair_to_names import build_simple_pair_mappings
from src.file_management import create_tempdir_file, remove_duplicates_external_sort
from src.find_which import find_which_words_match_and_how_well


def compare_all_names(all_names: list[str], word_to_matches: dict[str, frozenset[str]] | None = None) -> Path:
    # Prepare vars
    all_names = list({clean_name(name) for name in all_names})
    random.shuffle(all_names)
    if not word_to_matches:
        word_to_matches = get_word_to_matches(all_names)
    pair_to_names = build_simple_pair_mappings(all_names)

    # Write variables to a json file to pass large data to Go
    data = {
        "all_names": all_names,
        "word_to_matches": {k: list(v) for k, v in word_to_matches.items()},
        "pair_to_names": {k: list(v) for k, v in pair_to_names.items()}
    }
    json_filepath = create_tempdir_file('json')
    with open(json_filepath, "w") as f:
        json.dump(data, f)
    all_names, word_to_matches, pair_to_names, data = None, None, None, None
    gc.collect()

    # Create raw output file (has results, but could contain dups)
    raw_output_filepath = create_tempdir_file()

    # Get the binary path
    binary_path = _get_binary_path()

    # Call Go program
    import time
    start = time.perf_counter()
    result = subprocess.run(
        [str(binary_path), str(json_filepath), str(raw_output_filepath)],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Go binary error: {result.stderr}")
        raise RuntimeError(f"Go binary failed with return code {result.returncode}")
    
    print(f"Processing time: {time.perf_counter() - start:.2f}s")

    # Remove duplicates
    output_filepath = remove_duplicates_external_sort(raw_output_filepath)

    # Cleanup
    os.remove(json_filepath)
    os.remove(raw_output_filepath)
    return output_filepath


def simple_scoring_func(name_a: str, name_b: str) -> float:
    final_score = 100.0
    num_without_initials = 0
    num_mid_matchup_scores = 0
    num_bad_matchup_scores = 0
    num_real_bad_matchup_scores = 0
    num_total = 0
    max_index_a = -1
    max_index_b = -1
    index_violation = False
    for matchup in find_which_words_match_and_how_well(name_a, name_b):
        num_total += 1
        idx_a = matchup.word_in_name_a.index
        idx_b = matchup.word_in_name_b.index
        if (idx_a < max_index_a) or (idx_b < max_index_b):
            index_violation = True
        if len(matchup.word_in_name_a.string) != 1 and len(matchup.word_in_name_b.string) != 1:
            num_without_initials += 1
        if 75 < matchup.score <= 83:
            num_mid_matchup_scores += 1
        if 60 < matchup.score <= 75:
            num_bad_matchup_scores += 1
        if matchup.score <= 60:
            num_real_bad_matchup_scores += 1
        max_index_a = idx_a
        max_index_b = idx_b
    if num_without_initials == 1:
        final_score -= 20
    if num_without_initials == 0:
        final_score -= 40
    if index_violation:
        final_score -= 7
    for _ in range(num_mid_matchup_scores):
        final_score -= 5 if (num_total <= 2) else 3
    for _ in range(num_bad_matchup_scores):
        final_score -= 9 if (num_total <= 2) else 5
    for _ in range(num_real_bad_matchup_scores):
        final_score -= 20 if (num_total <= 2) else 12
    return max(final_score, 0)


def add_scrutiny(original_filepath: Path, scoring_func: Callable[[str, str], float] = simple_scoring_func, threshold: float = 0.0) -> Path:
    """Reads the original file line by line, applies a scoring function to each line, and writes the lines that pass the threshold to a new file.

    Args:
        original_filepath: The path to the file to be read
        scoring_func: A callable that takes two names as input and returns the score for that name comparison
        threshold: the threshold that each line must score in order to be included within the filtered

    Returns:
        A new path to a filtered file where each line has the two names and their score
    """
    filtered_filepath = create_tempdir_file()
    print(f'Filtered filepath is at {filtered_filepath}, and will be populated shortly.')
    with open(filtered_filepath, 'a', encoding='utf-8') as filtered_file:
        with open(original_filepath, 'r', encoding='utf-8') as original_file:
            for line in track(original_file, 'Scoring the results'):
                name_a, name_b = ast.literal_eval(line)
                score = scoring_func(name_a, name_b)
                if score < threshold:
                    continue
                filtered_file.write(f'("{name_a}", "{name_b}", {score})\n')
    return filtered_filepath


def _get_binary_path() -> Path:
    """
    Locate the PairwiseNameComparator binary.
    Searches in order:
    1. Current directory (for development)
    2. Package installation directory
    3. PATH
    """
    system = platform.system().lower()
    binary_name = "PairwiseNameComparator.exe" if system == "windows" else "PairwiseNameComparator"
    
    # 1. Check current directory (development)
    local_binary = Path.cwd() / binary_name
    if local_binary.exists():
        return local_binary
    
    # 2. Check package installation directory
    try:
        import src
        package_dir = Path(src.__file__).parent
        installed_binary = package_dir / "bin" / binary_name
        if installed_binary.exists():
            return installed_binary
    except (ImportError, AttributeError):
        pass
    
    # 3. Check if it's in PATH
    import shutil
    path_binary = shutil.which(binary_name)
    if path_binary:
        return Path(path_binary)
    
    raise FileNotFoundError(
        f"Could not find {binary_name}. Please ensure the package is properly installed "
        "or the binary is in your current directory."
    )