import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class GroqIntentClassifier:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "llama-3.3-70b-versatile"

    def classify(self, text: str) -> dict:
        """
        Use Groq to classify user intent and extract entities.

        Returns:
            dict with keys: intent, confidence, entities
        """

        system_prompt = """You are an intent classifier for Moonso Link, an agricultural marketplace platform.

Available intents:
1. greeting - User says hello or greets the bot
2. create_listing - User wants to sell/post a product
3. search_listings - User wants to find/browse products with specific criteria
4. get_my_listings - User wants to see their own listings
5. update_listing - User wants to update/edit/change an existing listing
6. delete_listing - User wants to remove/delete a listing
7. get_my_info - User wants to see their profile/account info
8. verify_account - User wants to verify their farmer account
9. change_role - User wants to become a farmer (upgrade from buyer)
10. update_profile - User wants to update their name or region
11. show_available_products - User asks what products are available/listed
12. product_locations - User asks where a specific product is being sold
13. show_interest - User expresses interest in a specific listing number
14. view_listing_interests - Farmer wants to see buyer interests on their listings
15. search_by_price - User searches for product at specific price
16. unknown - None of the above match

Extract entities:
- product: crop name (maize, cassava, tomato, onion, plantain, yam, etc.)
- quantity: amount in kg (numeric)
- price: price per kg in XAF/FCFA (numeric)
- location: town/city name
- region: region name (Littoral, Centre, Ouest, Nord, Sud, Adamaoua, Est, Extreme-Nord, Nord-Ouest, Sud-Ouest)
- name: person's name (for profile updates)
- listing_number: listing number user is interested in (numeric, from phrases like "listing 5", "#3", "number 2")

Respond ONLY with valid JSON in this exact format:
{
    "intent": "intent_name",
    "confidence": 0.95,
    "entities": {
        "product": "maize",
        "quantity": 50,
        "price": 300,
        "location": "Douala",
        "region": "Littoral",
        "name": null,
        "listing_number": null
    }
}

Rules:
- confidence should be between 0.0 and 1.0
- Only include entities that are present in the text
- Set missing entities to null
- For "change_role" intent, extract the region from phrases like "in Littoral" or "farmer in Centre"
- For "update_listing", look for keywords: update, change, edit, modify + listing/product
- For "change_role", look for: become farmer, switch to farmer, upgrade to farmer, change role
- For "show_available_products", look for: what products, available products, list products, what's available
- For "product_locations", look for: where is X, where can I find X, where to buy X
- For "search_listings", user specifies criteria (location, price, etc.) - differs from product_locations which asks general availability
- For "show_interest", extract listing_number from: "listing 5", "number 3", "#2", "the 4th one"
- For "search_by_price", user asks if anyone is selling product at specific price
- For "view_listing_interests", farmer asks to see buyer interests"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Classify this message: {text}"}
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            # Ensure required keys exist
            if "intent" not in result:
                result["intent"] = "unknown"
            if "confidence" not in result:
                result["confidence"] = 0.5
            if "entities" not in result:
                result["entities"] = {}

            # Add method indicator
            result["method"] = "groq"

            return result

        except Exception as e:
            print(f"GROQ CLASSIFICATION ERROR: {e}")
            # Fallback to unknown intent
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "method": "groq_error",
                "entities": {},
                "error": str(e)
            }

    def classify_with_fallback(self, text: str) -> dict:
        """
        Classify with fallback to keyword matching if Groq fails.
        """
        result = self.classify(text)

        # If Groq failed or confidence is very low, fallback
        if result["intent"] == "unknown" or result.get("confidence", 0) < 0.3:
            from intents.classifier import IntentClassifier
            fallback = IntentClassifier()
            fallback_result = fallback.classify(text)

            # Merge entities from Groq with fallback intent
            return {
                "intent": fallback_result["intent"],
                "confidence": fallback_result["confidence"],
                "method": f"fallback_{fallback_result['method']}",
                "entities": result.get("entities", {})
            }

        return result
