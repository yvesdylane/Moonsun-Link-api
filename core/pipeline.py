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

        # Merge entities: prioritize Groq, fallback to regex
        entities = {
            "product": groq_entities.get("product") or regex_entities.get("product"),
            "quantity": groq_entities.get("quantity") or regex_entities.get("quantity"),
            "price": groq_entities.get("price") or regex_entities.get("price"),
            "location": groq_entities.get("location") or regex_entities.get("location"),
            "region": groq_entities.get("region") or regex_entities.get("region"),
            "origin": groq_entities.get("origin") or regex_entities.get("origin"),
            "name": groq_entities.get("name"),
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