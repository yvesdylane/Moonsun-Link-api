from intents.classifier import IntentClassifier
from entities.extractor import EntityExtractor
from core.pipeline import AssistantPipeline

clf = IntentClassifier()

tests = [
    "i want to sell my maize",
    "who is selling corn in yaounde",
    "show me my current listings",
    "delete my tomato listing",
    "what is the weather today",   # should return unknown
]

for text in tests:
    result = clf.classify(text)
    print(f"{text!r:50} → {result}")

ex = EntityExtractor()

tests = [
    "find me corn in yaounde",
    "who is selling tomatoes in douala",
    "i want to sell my cassava",
    "what is the weather today",
]

for text in tests:
    print(f"{text!r:45} → {ex.extract(text)}")


pipeline = AssistantPipeline()

tests = [
    "find me corn in yaounde",
    "i want to sell my cassava",
    "delete my tomato listing",
    "what is the weather today",
]

for text in tests:
    print(pipeline.process(text))