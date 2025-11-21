from functools import lru_cache
from typing import NamedTuple

from fuzzywuzzy import fuzz
from HungarianScorer.HungarianScorer import HungarianScorer

from PairwiseNameComparator.src.nicknames import get_nickname_set
from PairwiseNameComparator.src.convert_to_ipa import get_ipa_of_one_word

class WordInName(NamedTuple):
    string: str
    index: int


class Matchup(NamedTuple):
    word_in_name_a: WordInName
    word_in_name_b: WordInName
    score: float


def find_which_words_match_and_how_well(name_a: str, name_b: str) -> list[Matchup]:
    """Identifies which words in either name are a match, and how well they match.

    Args:
        name_a: the name of a person
        name_b: the name of a person

    Returns:
        list[tuple[str, str, int]]: a list of tuples idenifying the index of the word in the first name,
            the index of the word in the second name, and the score of how well they match
    """
    all_words_a = [WordInName(string=word, index=i) for i, word in enumerate(name_a.split())]
    all_words_b = [WordInName(string=word, index=i) for i, word in enumerate(name_b.split())]
    get_word_matchup_score_lambda = lambda a, b: _get_word_matchup_score_helper(a.string, b.string)
    optimal_matchups = HungarianScorer.getBestCombo(all_words_a, all_words_b, get_word_matchup_score_lambda)
    return [Matchup(*triple) for triple in optimal_matchups]


@lru_cache(maxsize=50_000)
def _get_word_matchup_score_helper(word_a: str, word_b: str) -> float:
    has_same_first_letter = (word_a[0] == word_b[0])
    either_is_initial = (len(word_a) == 1) or (len(word_b) == 1)
    ratio = fuzz.ratio(word_a, word_b)
    initial_score = 100 if (has_same_first_letter and either_is_initial) else 0
    partial_ratio = fuzz.partial_ratio(word_a, word_b) if has_same_first_letter else 0
    nickname_score = 100 if word_b in get_nickname_set(word_a) else 0
    ipa_score = fuzz.ratio(get_ipa_of_one_word(word_a), get_ipa_of_one_word(word_b))
    return max(ratio, partial_ratio, nickname_score, ipa_score, initial_score)
