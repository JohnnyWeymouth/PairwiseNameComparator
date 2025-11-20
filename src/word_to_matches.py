from rich.progress import track
from rapidfuzz import fuzz

from src.nicknames import get_nickname_set
from src.patterns import SPELLING_PATTERNS, IPA_PATTERNS
from src.pattern_match import pattern_match
from src.convert_to_ipa import get_ipa_of_one_word


def get_word_to_matches(all_names: list[str]) -> dict[str, frozenset[str]]:
    """Finds the matches of each word."""
    # Get matches based on simple fuzzy match
    all_words = frozenset({word for name in all_names for word in name.split()})
    word_to_matches = {
        word_a: {word_b for word_b in all_words if _is_fuzzy_match(word_a, word_b)}
        for word_a in track(all_words, 'For each word, find the set of matching words.')
    }
    # Add matches based on string pattern rules
    for word, matching_words in pattern_match(all_words, SPELLING_PATTERNS).items():
        word_to_matches[word].update(matching_words)
    # Add matches based on ipa pattern rules
    word_to_ipa = {word: get_ipa_of_one_word(word) for word in all_words}
    ipa_to_word = {value: key for key, value in word_to_ipa.items()}
    for ipa, matching_ipas in pattern_match(ipa_to_word.keys(), IPA_PATTERNS).items():
        original_word = ipa_to_word[ipa]
        original_matching_words = {ipa_to_word[matching_ipa] for matching_ipa in matching_ipas}
        word_to_matches[original_word].update(original_matching_words)
    # Add matches based on known nicknames
    for word in all_words:
        nickname_set = get_nickname_set(word)
        word_to_matches[word].update(nickname_set)
    word_to_matches = {word: frozenset(matches) for word, matches in word_to_matches.items()}
    return word_to_matches


def _is_fuzzy_match(word_a: str, word_b: str) -> bool:
    """Determines if the two words match one another by basic string comparison."""
    if len(word_a) == 1 or len(word_b) == 1:
        return word_a[0] == word_b[0]
    return fuzz.ratio(word_a, word_b) >= 75