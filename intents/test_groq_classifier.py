from intents.groq_classifier import GroqIntentClassifier

def test_classifier():
    classifier = GroqIntentClassifier()

    test_cases = [
        "hello",
        "I want to sell 50kg of corn at 300 XAF",
        "find tomatoes in Douala",
        "show me my listings",
        "update my corn price to 400 XAF",
        "delete my maize listing",
        "show my profile",
        "verify my account",
        "I want to become a farmer in Littoral",
        "change my name to John Doe",
        "update my account to farmer",
    ]

    print("Testing Groq Intent Classifier\n" + "="*60)

    for text in test_cases:
        print(f"\nInput: {text}")
        result = classifier.classify_with_fallback(text)
        print(f"Intent: {result['intent']}")
        print(f"Confidence: {result['confidence']}")
        print(f"Method: {result['method']}")
        if result.get('entities'):
            print(f"Entities: {result['entities']}")
        print("-" * 60)

if __name__ == "__main__":
    test_classifier()
