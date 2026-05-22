from rapidfuzz import process, fuzz
from entities.vocabulary import REGIONS

def resolve_region(text: str) -> str | None:
    match = process.extractOne(text, REGIONS, scorer=fuzz.partial_ratio)
    if match and match[1] >= 60:
        return match[0]
    return None