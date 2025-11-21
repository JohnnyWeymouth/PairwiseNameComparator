from functools import lru_cache

from unidecode import unidecode

from .ipaAllNames import data as ipaAllNames
from .ipaCommonWordParts import data as ipaCommonWordParts


@lru_cache(50_000)
def get_ipa_of_one_word(word: str) -> str:
    """Gets the pronunciation of one word.

    Args:
        word: a word

    Returns:
        str: the ipa of the word
    """
    # Setup
    word = word.strip()
    word = unidecode(word)
    word = word.lower()
    ipa_words = [""] * len(word)

    # Tries to get the ipa from the plain word
    first_attempt, success = _word_pronunciation_hail_mary(word)
    if success:
        return _clean_ipa(first_attempt)

    # While there are still letters in the word
    substring_added = True
    while substring_added:
        # Initialize variables to store the largest matching substring and its length
        substring_added = False
        largest_substring = ""
        pronunciation_of_largest_substring = ""
        largest_substring_len = 0
        beginning_index_of_substring = 0
        end_index_of_substring = 0

        # Iterate over every possible substring
        for i in range(len(word)):
            for j in range(i + 1, len(word) + 1):
                substring = word[i:j]

                if len(substring) <= largest_substring_len:
                    continue
                if " " in substring:
                    continue
                if len(substring) > 1:
                    substring_ipa, success = _stringPronuncationHailMary(substring)
                    if (not success) or (len(substring_ipa) >= len(substring) * 2) or (substring_splits_th(substring, word, i, j)):
                        continue
                    else:
                        pronunciation_of_largest_substring = substring_ipa
                elif len(substring) == 1:
                    letter_to_pronunciation = {
                        "a": "æ", "b": "b", "c": "k", "d": "d", "e": "ɛ", "f": "f", "g": "g", "h": "h", "i": "ɪ",
                        "j": "ʤ", "k": "k", "l": "l", "m": "m", "n": "n", "o": "o", "p": "p", "q": "k", "r": "r",
                        "s": "s", "t": "t", "u": "u", "v": "v", "w": "w", "x": "ks", "y": "j", "z": "z"
                    }
                    pronunciation_of_largest_substring = letter_to_pronunciation.get(substring, largest_substring)

                largest_substring = substring
                substring_added = True
                largest_substring_len = len(substring)
                beginning_index_of_substring = i
                end_index_of_substring = j

        # Adds the substring to the list
        if substring_added:
            ipa_words[beginning_index_of_substring] = pronunciation_of_largest_substring
        spaces = " " * largest_substring_len
        word = word.rstrip()
        word = word[:beginning_index_of_substring] + spaces + word[end_index_of_substring:]

    # Concatenates the list together at the end to get the pronunciation
    pronunciation = "".join(ipa_words)
    pronunciation = _clean_ipa(pronunciation)
    return pronunciation

def _word_pronunciation_hail_mary(word: str) -> tuple[str, bool]:
    """Tries to get the pronunciation from the predefined ipa dictionary.

    Args:
        word (str): the regular word

    Returns:
        tuple[str, bool]: the ipa of the word (or the original word if not found), and whether it was found.
    """        
    word_pronuncation = ipaAllNames.get(word)
    if word_pronuncation != None:
        return word_pronuncation, True
    return word, False

def _stringPronuncationHailMary(string: str) -> tuple[str, bool]:
    """Helper function of _getIpaOfOneWord.
    Tries to get the ipa of a string (with more than one letter).

    Args:
        string (str): a string that is longer than one letter

    Returns:
        tuple[str, bool]: the ipa of the string (or the original string if not found), and whether it was found.
    """        
    ipa_pronunciation = ipaCommonWordParts.get(string)
    if ipa_pronunciation != None:
        return ipa_pronunciation, True
    return string, False


def substring_splits_th(substring: str, word: str, i: int, j: int) -> bool:
    """Helps to identify poor substring choices for words for ipa.

    Args:
        substring (str): the ipa dissection
        word (str): the full word
        i (int): the start index of the substring
        j (int): the end index of the substring

    Returns:
        bool: whether it was a good substring
    """            
    if i == j:
        return False
    if i >= 0 and substring[0] == 'h' and word[i - 1] == 't':
        return True
    if j <= len(word) - 1 and substring[-1] == 't' and word[j] == 'h':
        return True
    return False


def _clean_ipa(ipa: str) -> str:
    """Cleans ipa to get rid of double ipa-consonants and other mistakes.

    Args:
        ipa: the raw ipa of a word

    Returns:
        the cleaned ipa
    """        
    all_ipa_consonants = ['l', 'd', 'z', 'b', 't', 'k', 'n', 's', 'w', 'v', 'ð', 'ʒ', 'ʧ', 'θ', 'h', 'g', 'ʤ', 'ŋ', 'p', 'm', 'ʃ', 'f', 'j', 'r']
    for consonant in all_ipa_consonants:
        double_consonant = consonant + consonant
        if double_consonant in ipa:
            ipa = ipa.replace(double_consonant, consonant)
    ipa = ipa.replace("ɛɛ", "i")
    ipa = ipa.replace("ɪɪ", "ɪ")
    ipa = ipa.replace("iɪ", "i")
    ipa = ipa.replace("ŋg", "ŋ")
    ipa = ipa.replace(",", "")
    if not ipa:
        ipa = '_'
    return ipa
