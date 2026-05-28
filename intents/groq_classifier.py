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
3. search_listings - User wants to find/browse products with specific criteria OR see all marketplace listings (e.g., "show all listings", "show listings on the market", "market listings", "product propositions")
4. get_my_listings - User wants to see their own listings
5. update_listing - User wants to update/edit/change an existing listing
6. delete_listing - User wants to remove/delete a listing
7. get_my_info - User wants to see their profile/account info
8. verify_account - User wants to verify their farmer account
9. change_role - User wants to become a farmer (upgrade from buyer)
10. update_profile - User wants to update their name or region
11. show_available_products - User asks what products/crops are available (product NAMES only, not full listings) - e.g., "what products are available?", "what crops can I find?"
12. product_locations - User asks where a specific product is being sold
13. show_interest - User expresses interest in a specific listing number
14. view_listing_interests - Farmer wants to see buyer interests on their listings
15. get_my_interests - Buyer wants to see their own interests/inquiries
16. cancel_interest - User wants to cancel their interest
17. reject_interest - Farmer wants to reject a buyer's interest
18. search_by_price - User searches for product at specific price
19. view_listing_image - User wants to see the photo/image of a specific listing number
20. get_crop_price - User asks for crop price in specific region or all regions (e.g., "what's the price of maize?", "how much is cassava in Centre?")
21. get_all_crop_prices - User wants overview of all crop prices (e.g., "show all crop prices", "market overview")
22. unknown - None of the above match

Extract entities:
- product: crop name (maize, cassava, tomato, onion, plantain, yam, rice, etc.) — CRITICAL: ONLY extract if the user EXPLICITLY names a specific crop. NEVER set product when user says "price" (that's a different entity!). NEVER set product when user refers to listing by number (e.g. "number 2", "the fourth"). If no crop name is mentioned, set product to null.
- quantity: amount in kg (numeric) — also recognize "quality" as a misspelling of quantity
- price: price per kg in XAF/FCFA (numeric) — extract from phrases like "price of 200", "at 300 XAF", "for 150". DO NOT confuse with "rice" crop.
- location: town/city name
- region: region name (Littoral, Centre, Ouest, Nord, Sud, Adamaoua, Est, Extreme-Nord, Nord-Ouest, Sud-Ouest)
- name: person's name (for profile updates)
- listing_number: the listing number as a DIGIT (1, 2, 3, etc.) extracted from phrases like "listing 5", "#3", "number 2", "number 4", "number 1", "the 4th one", "the number 4", "listing number 4", "no 3", "first", "second", "third", "fourth", "fifth", "the 1st", "the first one", "the second", "the third", "the fourth of", "the 1st one" — convert ordinals to digits (first→1, second→2, third→3, fourth→4, fifth→5, etc.). Extract for ANY intent (update_listing, show_interest, view_listing_image, delete_listing, etc.)
- interest_id: numeric ID for interests (for cancel_interest, reject_interest intents) - extract from "cancel interest 123", "reject interest 45"

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

EXAMPLES:
"Update number 1 to have a price of 200" → {"intent": "update_listing", "entities": {"listing_number": 1, "price": 200, "product": null}}
"Update the fourth one to have a quantity of 200kg" → {"intent": "update_listing", "entities": {"listing_number": 4, "quantity": 200, "product": null}}
"Update the first one to have a price of 200 and quantity to 200" → {"intent": "update_listing", "entities": {"listing_number": 1, "price": 200, "quantity": 200, "product": null}}
"The price to 200" → {"intent": "update_listing", "entities": {"price": 200, "product": null}}
"Show all listings on the market" → {"intent": "search_listings", "entities": {}}
"What products are available" → {"intent": "show_available_products", "entities": {}}

Rules:
- confidence should be between 0.0 and 1.0
- Only include entities that are present in the text
- Set missing entities to null
- NEVER confuse "price" with "rice" — "price" is a numeric entity, "rice" is a crop name (product)
- For "update_listing", ALWAYS check if listing_number is present first before extracting product
- For "change_role" intent, extract the region from phrases like "in Littoral" or "farmer in Centre"
- For "update_listing", look for keywords: update, change, edit, modify + listing/product
- For "change_role", look for: become farmer, switch to farmer, upgrade to farmer, change role
- For "show_available_products", look for: what products, available products, list products, what's available, what crops - returns PRODUCT NAMES ONLY
- For "search_listings", look for: show all listings, market listings, show listings, product propositions on the market, browse listings, find [product], search - returns FULL LISTING DETAILS
- For "product_locations", look for: where is X, where can I find X, where to buy X
- For "search_by_price", user asks if anyone is selling product at specific price
- For "view_listing_interests", farmer asks to see buyer interests
- For "view_listing_image", user asks to see photo/image of a listing number
- For "get_crop_price", user asks about market price of a crop (can include region)
- For "get_all_crop_prices", user asks for price overview of all crops
- CRITICAL: When user says "update number X" or "the first one", extract listing_number and DO NOT extract product
- CRITICAL DISTINCTION: "what products are available?" = show_available_products (names only), "show all listings" = search_listings (full details)
- CRITICAL DISTINCTION: "what's the price of maize?" = get_crop_price (market prices), "find maize at 200 XAF" = search_by_price (listings at price)
"""

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

    def resolve_with_context(self, text: str, listings: list) -> dict:
        """
        Resolve user intent with listing context.
        Used when user references listings they've already viewed.

        Args:
            text: User message (e.g., "update the fourth one to price 200")
            listings: List of listings user has viewed, each with:
                [id, user_id, crop_id, quantity_kg, price, town, region, origin, image_url, created_at, crop_name]

        Returns:
            dict with keys: listing_id, updates
        """
        print(f"=== RESOLVE_WITH_CONTEXT ===")
        print(f"User text: {text}")
        print(f"Listings count: {len(listings)}")

        # Format listings for Groq
        listings_context = []
        for idx, listing in enumerate(listings, 1):
            listings_context.append({
                "number": idx,
                "listing_id": listing[0],
                "crop": listing[10] if len(listing) > 10 else "Unknown",
                "quantity_kg": listing[3],
                "price_per_kg": listing[4],
                "location": f"{listing[5] or 'Not specified'}, {listing[6]}"
            })

        context_str = json.dumps(listings_context, indent=2)
        print(f"Listings context:\n{context_str}")

        prompt = f"""The user has viewed these listings:
{context_str}

User message: "{text}"

Determine:
1. Which listing number (1-{len(listings)}) the user is referring to
2. What updates they want to make (price, quantity, location, region, origin)

Respond with JSON:
{{
    "listing_number": <number 1-{len(listings)}>,
    "updates": {{
        "price": <numeric value or null>,
        "quantity": <numeric value in kg or null>,
        "location": <town name or null>,
        "region": <region name or null>,
        "origin": <origin or null>
    }}
}}

Rules:
- For "the fourth", "number 4", "4th one", "#4" → listing_number: 4
- For "first", "the first one", "#1" → listing_number: 1
- Extract price from: "price of 200", "at 300", "to 150 XAF"
- Extract quantity from: "200kg", "quantity 200", "quality 200"
- If user doesn't specify which listing and there's only one, use listing_number: 1
- DO NOT confuse "price" with "rice" crop
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a context-aware assistant that resolves user references to listings."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=200,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            # Validate listing_number
            listing_number = result.get("listing_number")
            if not listing_number or listing_number < 1 or listing_number > len(listings):
                return {"status": "error", "message": f"Invalid listing number. Please choose between 1 and {len(listings)}."}

            # Get actual listing_id
            listing_id = listings[listing_number - 1][0]

            # Clean up updates
            updates = result.get("updates", {})
            cleaned_updates = {}
            if updates.get("price"):
                cleaned_updates["price"] = updates["price"]
            if updates.get("quantity"):
                cleaned_updates["quantity_kg"] = updates["quantity"]
            if updates.get("location"):
                cleaned_updates["town"] = updates["location"]
            if updates.get("region"):
                cleaned_updates["region"] = updates["region"]
            if updates.get("origin"):
                cleaned_updates["origin"] = updates["origin"]

            return {
                "status": "ok",
                "listing_id": listing_id,
                "listing_number": listing_number,
                "updates": cleaned_updates
            }

        except Exception as e:
            print(f"GROQ CONTEXT RESOLUTION ERROR: {e}")
            return {
                "status": "error",
                "message": "Failed to understand which listing you're referring to. Please be more specific."
            }
