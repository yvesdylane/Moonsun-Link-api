from intents.groq_classifier import GroqIntentClassifier
from entities.extractor import EntityExtractor
from db.controller.logController import log_message
from utils.translator import translate_to_english


class AssistantPipeline:
    def __init__(self):
        self.classifier = GroqIntentClassifier()
        self.extractor = EntityExtractor()

    def process(self, text: str) -> dict:
        translated_text, detected_lang = translate_to_english(text)

        # Use Groq for intent classification and entity extraction
        groq_result = self.classifier.classify_with_fallback(translated_text)

        # Extract entities from Groq response
        groq_entities = groq_result.get("entities", {})

        # Fallback entity extraction using regex patterns if Groq missed something
        regex_entities = self.extractor.extract(translated_text)

        # Merge entities:
        # - Product: trust Groq exclusively (handles whitelist, auto-create, rejection)
        # - Location/region/origin: trust Groq exclusively (handles whitelist, auto-create, rejection)
        # - Numeric/measurement: Groq first, regex fallback
        entities = {
            "product": groq_entities.get("product"),
            "quantity": groq_entities.get("quantity") or regex_entities.get("quantity"),
            "measurement": groq_entities.get("measurement") or regex_entities.get("measurement"),
            "price": groq_entities.get("price") or regex_entities.get("price"),
            "location": groq_entities.get("location"),
            "region": groq_entities.get("region"),
            "origin": groq_entities.get("origin"),
            "name": groq_entities.get("name"),
            "listing_number": groq_entities.get("listing_number"),
            "auto_create": groq_entities.get("auto_create", False),
            "valid": groq_entities.get("valid", True),
            "rejection_reason": groq_entities.get("rejection_reason"),
            "product_type": groq_entities.get("product_type"),
            "default_measurement": groq_entities.get("default_measurement"),
            "location_valid": groq_entities.get("location_valid", True),
            "location_rejection_reason": groq_entities.get("location_rejection_reason"),
            "location_auto_create": groq_entities.get("location_auto_create", False),
            "report_type": groq_entities.get("report_type"),
            "report_title": groq_entities.get("report_title"),
            "report_description": groq_entities.get("report_description"),
            "issue_title": groq_entities.get("issue_title"),
            "issue_description": groq_entities.get("issue_description"),
            "issue_type": groq_entities.get("issue_type"),
            "advice_content": groq_entities.get("advice_content"),
        }

        intent = {
            "intent": groq_result["intent"],
            "confidence": groq_result["confidence"],
            "method": groq_result["method"]
        }

        log_message(text, intent, entities)

        return {
            "input": text,
            "translated": translated_text,
            "language": detected_lang,
            "intent": intent,
            "entities": entities
        }