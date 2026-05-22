import re
from rapidfuzz import process, fuzz
from entities.vocabulary import PRODUCTS, LOCATIONS
from utils.region_resolver import resolve_region

class EntityExtractor:
    def extract(self, text: str) -> dict:
        text_lower = text.lower()
        return {
            "product": self._match(text_lower, PRODUCTS),
            "location": self._match(text_lower, LOCATIONS),
            "quantity": self._extract_quantity(text_lower),
            "price": self._extract_price(text_lower),
            "region": self._extract_region(text),
            "origin": self._extract_origin(text),
        }

    def _extract_region(self, text: str) -> str | None:
        # look for "in [region]" or "selling in [region]"
        import re
        match = re.search(r"\b(selling in|in|au|dans)\s+([a-zA-Z\-]+)", text, re.IGNORECASE)
        if match:
            return resolve_region(match.group(2))
        return None

    def _extract_origin(self, text: str) -> str | None:
        # look for "from [region]" or "origine [region]"
        import re
        match = re.search(r"\b(from|de|depuis|origin|origine)\s+([a-zA-Z\-]+)", text, re.IGNORECASE)
        if match:
            return resolve_region(match.group(2))
        return None

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