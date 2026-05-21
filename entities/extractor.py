import re
from rapidfuzz import process, fuzz
from entities.vocabulary import PRODUCTS, LOCATIONS

class EntityExtractor:
    def extract(self, text: str) -> dict:
        text = text.lower()
        return {
            "product": self._match(text, PRODUCTS),
            "location": self._match(text, LOCATIONS),
            "quantity": self._extract_quantity(text),
            "price": self._extract_price(text),
        }

    def _match(self, text: str, vocabulary: list) -> str | None:
        match = process.extractOne(text, vocabulary, scorer=fuzz.partial_ratio)
        if match and match[1] >= 80:
            return match[0]
        return None

    def _extract_quantity(self, text: str) -> int | None:
        # matches "200kg", "200 kg", "200k", "200 kilo"
        match = re.search(r"(\d+)\s*(kg|kilo|k)\b", text)
        if match:
            return int(match.group(1))
        return None

    def _extract_price(self, text: str) -> int | None:
        # matches "200fcfa", "200 xaf", "200fcf", "200 cfa"
        match = re.search(r"(\d+)\s*(fcfa|xaf|fcf|cfa)\b", text)
        if match:
            return int(match.group(1))
        return None