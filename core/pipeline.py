from intents.classifier import IntentClassifier
from entities.extractor import EntityExtractor

class AssistantPipeline:
    def __init__(self):
        self.classifier = IntentClassifier()
        self.extractor = EntityExtractor()

    def process(self, text: str) -> dict:
        intent = self.classifier.classify(text)
        entities = self.extractor.extract(text)
        return {
            "input": text,
            "intent": intent,
            "entities": entities
        }