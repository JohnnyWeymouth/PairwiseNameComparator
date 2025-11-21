import re
from typing import NamedTuple
from functools import lru_cache
from collections import defaultdict
from itertools import product, combinations

from rich.progress import track
from rapidfuzz import fuzz

from .patterns import SandwichPattern


class _RegexTup(NamedTuple):
    regex_string: str
    sandwich_pattern: SandwichPattern


class _LiteralTup(NamedTuple):
    literal_string: str
    regex_string: str
    sandwich_pattern: SandwichPattern


class _MatchTup(NamedTuple):
    word: str
    literal_string: str
    regex_string: str
    sandwich_pattern: SandwichPattern


def pattern_match(all_words: set[str], sandwich_patterns: set[SandwichPattern]):
    regex_tups = {
        reg_tup
        for sandwich in sandwich_patterns
        for reg_tup in _sandwich_to_regex_tups(sandwich)
    }

    literal_tups = {
        lit_tup
        for reg_tup in regex_tups
        for lit_tup in _regex_tup_to_literal_tups(reg_tup)
    }

    match_tups = _find_all_match_tups(all_words, literal_tups)

    potential_pairs = _find_potential_pairs(match_tups)

    word_to_matches = _find_word_to_matches(potential_pairs)
    
    return word_to_matches


def _sandwich_to_regex_tups(sandwich: SandwichPattern) -> set[_RegexTup]:
    """
    Convert a SandwichPattern into multiple regex patterns.
    Each combination of (beginning, middle_option, end) creates one regex.
    Returns list of tuples: (regex_pattern_string, min_word_length)
    """
    all_tups: set[_RegexTup] = set()
    
    for begin in sandwich.beginning_options:
        for end in sandwich.end_options:
            # Escape special regex characters in begin/end
            begin_escaped: str = re.escape(begin)
            end_escaped: str = re.escape(end)
            
            # Create pattern: begin(middle_a|middle_b)end
            middle_a_escaped: str = re.escape(sandwich.middle_x)
            middle_b_escaped: str = re.escape(sandwich.middle_y)
            regex_string: str = f"{begin_escaped}({middle_a_escaped}|{middle_b_escaped}){end_escaped}"
            regex_tup = _RegexTup(regex_string, sandwich)
            all_tups.add(regex_tup)
    
    return all_tups


def _regex_tup_to_literal_tups(regex_tup: _RegexTup) -> set[_LiteralTup]:
    """
    Expand a regex pattern like 'j(one|onde)o' into all possible literals.
    Returns a list of strings like ['joneo', 'jondeo']
    """
    # Find all alternations (groups with |)
    alternation_regex: re.Pattern[str] = re.compile(r'\(([^)]+)\)')
    
    parts: list[list[str]] = []
    last_end: int = 0

    regex_string = regex_tup.regex_string
    
    for match in alternation_regex.finditer(regex_string):
        # Add the literal part before this alternation
        parts.append([regex_string[last_end:match.start()]])
        
        # Add the alternation options
        options: list[str] = match.group(1).split('|')
        parts.append(options)
        
        last_end = match.end()
    
    # Add any remaining literal part
    if last_end < len(regex_string):
        parts.append([regex_string[last_end:]])
    
    # Generate all combinations
    return {
        _LiteralTup(''.join(combo), regex_tup.regex_string, regex_tup.sandwich_pattern)
        for combo in product(*parts)
    }


def _find_all_match_tups(all_words: set[str], literal_tups: set[_LiteralTup]) -> set[_MatchTup]:
    words_by_len = defaultdict(list[str])
    for word in all_words:
        words_by_len[len(word)].append(word)
    
    sorted_lits = sorted(literal_tups, key=lambda x: len(x.literal_string), reverse=True)
    match_tups: set[_MatchTup] = set()
    for lit_tup in track(sorted_lits, 'Finding words that match patterns, to compare with words that match similar patterns.'):
        min_len = lit_tup.sandwich_pattern.min_length
        literal_string = lit_tup.literal_string.replace(r'\-', '-')
        regex_string = lit_tup.regex_string
        sandwich_pattern = lit_tup.sandwich_pattern
        
        for word_len, word_list in words_by_len.items():
            if word_len < min_len:
                continue
            for word in word_list:
                if literal_string not in f'-{word}-':
                    continue
                m_tup = _MatchTup(word, literal_string, regex_string, sandwich_pattern)
                match_tups.add(m_tup)
    
    return match_tups


def _find_potential_pairs(match_tups: set[_MatchTup]) ->  set[tuple[_MatchTup, _MatchTup]]:
    groups: dict[str, list[_MatchTup]] = defaultdict(list[_MatchTup])
    for match in match_tups:
        groups[match.regex_string].append(match)
    return {
        (a, b)
        for group in groups.values()
        for a, b in combinations(group, 2)
        if a.literal_string != b.literal_string
    }


def _find_word_to_matches(potential_pairs: set[tuple[_MatchTup, _MatchTup]]):
    word_to_matches = defaultdict(set[str])
    for match_tup_a, match_tup_b in potential_pairs:
        if not _test_pair(match_tup_a, match_tup_b):
            continue
        word_to_matches[match_tup_a.word].add(match_tup_b.word)
        word_to_matches[match_tup_b.word].add(match_tup_a.word)
    return word_to_matches


def _test_pair(match_tup_a: _MatchTup, match_tup_b: _MatchTup) -> bool:
    """Modifies two words based on the pattern. Takes a list of potential starts and a list of potential ends (the breads),
    that a substring within could begin or end with, within two words. The same beginning and ends must be present in each word,
    even though many beginnings or ends may be in the list. Each word must have one of two middle that matches, one of which
    will be replaced. If this pattern does not match, or the words are too short or too far apart, then the changes don't happen.

    Args:


    Returns:
        _description_
    """        
    # Add word breaks once
    padded_a = f"-{match_tup_a.word}-"
    padded_b = f"-{match_tup_b.word}-"
    
    # Use cached compiled pattern
    compiled_pattern = _get_compiled_regex_pattern(match_tup_a.regex_string)
    
    # Find matches
    match_a = compiled_pattern.search(padded_a)
    match_b = compiled_pattern.search(padded_b)
        
    # return if both have identical groups (same middles)
    if match_a.group(0) == match_b.group(0):
        return False
    
    # Check span proximity efficiently
    span_a = match_a.span()
    span_b = match_b.span()
    if abs(span_a[0] - span_b[0]) > 2 or abs(span_a[1] - span_b[1]) > 2:
        return False
    
    # Calculate middle coordinates
    start_len = len(match_tup_a.regex_string.split('(')[0].replace(r'\-', '-'))
    end_len = len(match_tup_a.regex_string.split(')')[1].replace(r'\-', '-'))
    index_of_middle_a = span_a[0] + start_len
    index_of_end_middle_a = span_a[1] - end_len
    index_of_middle_b = span_b[0] + start_len
    index_of_end_middle_b = span_b[1] - end_len
    middle_y = match_tup_a.sandwich_pattern.middle_y
    
    # Replace middles with middle_a and remove dashes in one operation
    result_a = (padded_a[:index_of_middle_a] + middle_y + padded_a[index_of_end_middle_a:]).replace('-', '')
    result_b = (padded_b[:index_of_middle_b] + middle_y + padded_b[index_of_end_middle_b:]).replace('-', '')
    
    return fuzz.ratio(result_a, result_b) >= 75


@lru_cache(maxsize=10_000)
def _get_compiled_regex_pattern(regex_string: str) -> re.Pattern[str]:
    """Cache compiled regex patterns to avoid recompilation.

    Args:

    Returns:
        the pattern for identifying modification possibilities
    """    
    return re.compile(regex_string)
