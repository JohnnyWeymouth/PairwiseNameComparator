from collections import defaultdict
from itertools import combinations

from rich.progress import track

def build_simple_pair_mappings(all_names: list[str]) -> defaultdict[str, set[str]]:
    pair_to_names: defaultdict[str, set[str]] = defaultdict(set)
    for name in track(all_names, 'Bucketing names into their possible two word pairs'):
        words = name.split()
        if len(words) < 2:
            continue
        for combo in combinations(words, 2):
            temp = tuple(sorted(combo))
            two_word_pair = f'{temp[0]}_{temp[1]}'
            pair_to_names[two_word_pair].add(name)
    return dict(pair_to_names)