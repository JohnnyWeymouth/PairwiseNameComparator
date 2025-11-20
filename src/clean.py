import re
from unidecode import unidecode

def clean_name(name: str) -> str:
    """Cleans a singular name to get rid of extra or unhelpful data, and to standardize surnames.

    Args:
        name: the name being cleaned

    Returns:
        the cleaned-up name
    """        
    # Deal with blank names
    if (name == "") or (not isinstance(name, str)):
        return "_"

    # Deal with whitespace
    name = re.sub(r'[^\S ]', ' ', name)
    name = re.sub(r" +", " ", name)
    name = name.strip()

    # Standardize name into ascii
    name = unidecode(name)
    name = name.lower()

    # Deal with blank names again
    if name == "":
        return "_"

    # Remove Punctiation
    name = re.sub(r"[.,?;\"*()]", "", name)

    # Remove spaces after apostrophe
    name = re.sub("' +", "'", name)

    # Remove jr and sr
    name = re.sub(r"\bjr\b", "", name).replace(r"\bjunior\b", "")
    name = re.sub(r"\bsr\b", "", name).replace(r"\bsenior\b", "")

    # Remove titles
    name = re.sub(r"\bprof\b", "", name).replace(r"\bprofessor\b", "")
    name = re.sub(r"\bmr\b", "", name).replace(r"\bmister\b", "")
    name = re.sub(r"\bmrs\b", "", name).replace(r"\bmissus\b", "")
    name = re.sub(r"\bms\b", "", name).replace(r"\bmiss\b", "")
    name = re.sub(r"\bdr\b", "", name).replace(r"\bdoctor\b", "")
    name = re.sub(r"\bstudent\b", "", name)
    name = re.sub(r"\brev\b", "", name)
    name = name.replace("reverend", "")

    # Remove family relations
    name = re.sub(r"\bsister\b", "", name)
    name = re.sub(r"\bbrother\b", "", name)
    name = re.sub(r"\bmother\b", "", name)
    name = re.sub(r"\bfather\b", "", name)
    name = re.sub(r" in law", " ", name)

    # Removes "head of household"
    name = name.replace("head of household", "")

    # Remove Common Abbreviations
    common_abreviations = {
        'wm': 'william',
        'geo': 'george',
        'chas': 'charles',
        'thos': 'thomas',
        'jas': 'james',
        'jno': 'john',
        'robt': 'robert',
        'jos': 'joseph',
        'benj': 'benjamin'
    }
    name_as_list = []
    for word in name.split():
        name_as_list.append(common_abreviations.get(word, word))
    name = ' '.join(name_as_list)

    # Remove stuff like 'the 3rd'
    name = re.sub(r"[1-9][a-z]2,6", "", name).replace(" the ", "")

    # Remove Roman numerals
    name = ' '.join(re.sub(r'\b(ii|iii|iv)\b', '', word) for word in name.split())
    name = re.sub(r" +", " ", name)
    name = name.strip()

    # Remove 'no suffix'
    name = name.replace("no suffix", "")

    # Deal with Dutch names
    name = re.sub(r"\bvan de", "vande", name)
    name = re.sub(r"\bvan den", "vanden", name)
    name = re.sub(r"\bvan der", "vander", name)

    # Deal with whitespace one last time, then return
    name = re.sub(r" +", " ", name)
    name = name.strip()
    if not name:
        name = '_'
    return name