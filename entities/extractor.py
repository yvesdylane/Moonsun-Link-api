import re


class EntityExtractor:
    def extract(self, text: str) -> dict:
        text_lower = text.lower()
        return {
            "quantity": self._extract_quantity(text_lower),
            "measurement": self._extract_measurement(text_lower),
            "price": self._extract_price(text_lower),
        }

    def _extract_quantity(self, text: str) -> int | None:
        match = re.search(r"(\d+)\s*(kg|kilo|k)\b", text)
        if match:
            return int(match.group(1))
        match = re.search(r"(\d+)\s*(bag|bags|gallon|gallons|liter|liters|litre|litres|hour|hours|day|days|piece|pieces|head|heads|bunch|bunches|crate|crates|sack|sacks|tin|tins|bottle|bottles|carton|cartons|ton|tonnes|dozen|dozens|session|sessions|unit|units|pair|pairs|box|boxes|basket|baskets|task|tasks|job|jobs)\b", text)
        if match:
            return int(match.group(1))
        return None

    def _extract_measurement(self, text: str) -> str | None:
        match = re.search(r"(\d+)\s*(kg|kilo|k)\b", text)
        if match:
            return "kg"
        match = re.search(r"(\d+)\s*(bag|bags|gallon|gallons|liter|liters|litre|litres|hour|hours|day|days|piece|pieces|head|heads|bunch|bunches|crate|crates|sack|sacks|tin|tins|bottle|bottles|carton|cartons|ton|tonnes|dozen|dozens|session|sessions|unit|units|pair|pairs|box|boxes|basket|baskets|task|tasks|job|jobs)\b", text)
        if match:
            raw = match.group(2).lower()
            singular_map = {
                "bags": "bag", "gallons": "gallon", "liters": "liter", "litres": "liter",
                "hours": "hour", "days": "day", "pieces": "piece", "heads": "head",
                "bunches": "bunch", "crates": "crate", "sacks": "sack", "tins": "tin",
                "bottles": "bottle", "cartons": "carton", "tonnes": "ton",
                "dozens": "dozen", "sessions": "session", "units": "unit",
                "pairs": "pair", "boxes": "box", "baskets": "basket",
                "tasks": "task", "jobs": "job",
            }
            return singular_map.get(raw, raw)
        service_keywords = [
            "mecanicien", "mechanic", "veterinary", "vet", "ploughing", "plowing",
            "tilling", "harvesting", "spraying", "irrigation", "transport",
            "delivery", "consulting", "training", "land clearing", "pruning",
            "grafting", "sowing", "weeding", "fencing", "installation",
        ]
        if any(kw in text for kw in service_keywords):
            return "task"
        return None

    def _extract_price(self, text: str) -> int | None:
        match = re.search(r"(\d+)\s*(fcfa|xaf|fcf|cfa)\b", text)
        if match:
            return int(match.group(1))
        return None
