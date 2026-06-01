import os
import json
from groq import Groq
from dotenv import load_dotenv
from db.connect import conn

load_dotenv()


class GroqIntentClassifier:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "llama-3.3-70b-versatile"
        self.product_whitelist_str = self._load_product_whitelist()
        self.location_whitelist_str = self._load_location_whitelist()

    def _load_product_whitelist(self) -> str:
        """Build a formatted string of all approved products from the DB."""
        from entities.vocabulary import PRODUCT_SYNONYMS
        cur = conn.cursor()
        cur.execute("SELECT name, type, default_measurement FROM products ORDER BY type, name")
        rows = cur.fetchall()
        cur.close()

        groups = {"crop": [], "animal": [], "tool": [], "service": []}
        for name, ptype, meas in rows:
            syns = PRODUCT_SYNONYMS.get(name)
            entry = name
            if syns:
                entry += f" (a.k.a. {syns})"
            groups[ptype].append(entry)

        lines = []
        for ptype in ["crop", "animal", "tool", "service"]:
            if groups[ptype]:
                lines.append(f"{ptype}s: {', '.join(groups[ptype])}")

        return "\n".join(lines)

    def _load_location_whitelist(self) -> str:
        """Build a formatted string of towns with regions from the DB."""
        cur = conn.cursor()
        cur.execute("SELECT town, region FROM locations ORDER BY region, town")
        rows = cur.fetchall()
        cur.close()

        groups = {}
        for town, region in rows:
            groups.setdefault(region, []).append(town)

        lines = []
        for region in ["Adamaoua", "Centre", "Est", "Extreme-Nord", "Littoral", "Nord", "Nord-Ouest", "Ouest", "Sud", "Sud-Ouest"]:
            towns = groups.get(region, [])
            if towns:
                lines.append(f"{region}: {', '.join(towns)}")

        return "\n".join(lines)

    def classify(self, text: str) -> dict:
        """
        Use Groq to classify user intent and extract entities.

        Returns:
            dict with keys: intent, confidence, entities
        """

        system_prompt = f"""You are an intent classifier for Moonso Link, an agricultural marketplace platform.

Available intents:
1. greeting - User says hello or greets the bot
2. create_listing - User wants to sell/post a product
3. search_listings - User wants to find/browse products with specific criteria OR see all marketplace listings
4. get_my_listings - User wants to see their own listings
5. update_listing - User wants to update/edit/change an existing listing
6. delete_listing - User wants to remove/delete a listing
7. get_my_info - User wants to see their profile/account info
8. verify_account - User wants to verify their farmer account
9. change_role - User wants to become a farmer (upgrade from buyer)
10. update_profile - User wants to update their name or region
11. show_available_products - User asks what products are available (NAMES only)
12. product_locations - User asks where a specific product is being sold
13. show_interest - User expresses interest in a specific listing number
14. view_listing_interests - Farmer wants to see buyer interests on their listings
15. get_my_interests - Buyer wants to see their own interests/inquiries
16. cancel_interest - User wants to cancel their interest
17. reject_interest - Farmer wants to reject a buyer's interest
18. search_by_price - User searches for product at specific price
19. view_listing_image - User wants to see the photo of a specific listing number
20. get_crop_price - User asks for market price of a product (optionally in a region)
21. get_all_crop_prices - User wants price overview of all products
22. unknown - None of the above match

PRODUCT WHITELIST — Only these products are accepted:
{self.product_whitelist_str}

PRODUCT VALIDATION RULES (CRITICAL):
- If the user wants to sell/search for a product, FIRST check if it matches an item in the whitelist above (including synonyms).
  - If found: set product to the EXACT whitelist name. Set auto_create to false.
- If NOT in the whitelist, decide:
  - Is it clearly an AGRICULTURE-RELATED product? (fruits, vegetables, livestock, farming tools, agricultural services, crops, seeds, fertilizers, etc.)
    - If YES: set product to the name, auto_create to true, product_type to the correct type (crop/animal/tool/service), and default_measurement to the appropriate unit.
    - If NO (e.g., dresses, watches, phones, electronics, furniture, clothes, shoes, bags that aren't agricultural): set product to null, auto_create to false, valid to false, and rejection_reason to a helpful message saying we only support agriculture-related products.

LOCATION WHITELIST — Cameroonian towns (town → region):
{self.location_whitelist_str}

LOCATION VALIDATION RULES (CRITICAL):
- If the user mentions a location (town/city):
  - Check if it matches an entry in the whitelist above (case-insensitive, handle accents like é, è, etc.).
    - If found: set location to the EXACT whitelist name, set region to the corresponding region, set location_valid to true, location_auto_create to false.
  - If NOT in the whitelist, decide:
    - Is it a REAL Cameroonian town? (something that actually exists in Cameroon, even if not in our database yet)
      - If YES: set location to the town name the user provided, set region to the correct Cameroonian region, set location_valid to true, set location_auto_create to true.
      - If NO (clearly not a Cameroonian town — Paris, Berlin, New York, London, Dubai, Lagos, Nairobi, Kigali, Abidjan, Accra, etc.): set location to null, region to null, location_valid to false, and location_rejection_reason to a message saying "We only support locations in Cameroon. Please specify a Cameroonian town."
  - If no location is mentioned, leave all location fields as null.

IMPORTANT: town and region must ALWAYS be consistent. If you set a location, derive the correct region from it. Do NOT set contradictory location/region pairs.

Extract entities:
- product: the exact product name from the whitelist, or a new agriculture product name if auto-creating
- quantity: numeric amount — also recognize "quality" as misspelling of quantity
- measurement: unit (kg, bag, gallon, hour, head, piece, task, etc.)
- price: numeric price in XAF/FCFA
- location: town/city name
- region: region name (Littoral, Centre, Ouest, Nord, Sud, Adamaoua, Est, Extreme-Nord, Nord-Ouest, Sud-Ouest)
- name: person's name (for profile updates)
- listing_number: converted from ordinals (first→1, second→2, etc.)
- interest_id: numeric ID for interests
- auto_create: true/false — set to true if product is not in whitelist but IS agriculture-related
- valid: true/false — set to false ONLY for non-agriculture product rejections
- rejection_reason: string explaining why product was rejected
- product_type: crop/animal/tool/service — only needed when auto_create is true
- default_measurement: kg/head/piece/task — only needed when auto_create is true
- location_valid: true/false — set to false ONLY for non-Cameroonian locations
- location_rejection_reason: string — explain why location was rejected; only when location_valid is false
- location_auto_create: true/false — set to true if real CM town not in whitelist

Respond ONLY with valid JSON in this exact format:
{{
    "intent": "intent_name",
    "confidence": 0.95,
    "entities": {{
        "product": "maize",
        "quantity": 50,
        "measurement": "kg",
        "price": 300,
        "location": "Douala",
        "region": "Littoral",
        "name": null,
        "listing_number": null,
        "interest_id": null,
        "auto_create": false,
        "valid": true,
        "rejection_reason": null,
        "product_type": null,
        "default_measurement": null,
        "location_valid": true,
        "location_rejection_reason": null,
        "location_auto_create": false
    }}
}}

EXAMPLES:
"I want to sell 50kg of mangoes at 300 XAF" → product not in whitelist but IS agriculture (fruit) → auto_create:true, product_type:"crop"
"I want to sell my dresses" → not agriculture → product:null, valid:false, rejection_reason:"Dresses are not an agricultural product. We only support agriculture-related products such as crops, livestock, farming tools, and agricultural services."
"I want to sell a bag of rice" → "rice" is in whitelist → product:"rice", auto_create:false
"I want to sell my tractor" → "tractor" is in whitelist under tools → product:"tractor", auto_create:false
"I offer mechanic services" → "mechanic" is in whitelist under services → product:"mechanic", auto_create:false
"I want to sell compost" → not in whitelist but clearly agriculture (fertilizer) → auto_create:true, product_type:"crop"
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Classify this message: {text}"}
                ],
                temperature=0.1,
                max_tokens=400,
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

            # Ensure new fields have defaults
            entities = result["entities"]
            entities.setdefault("auto_create", False)
            entities.setdefault("valid", True)
            entities.setdefault("rejection_reason", None)
            entities.setdefault("product_type", None)
            entities.setdefault("default_measurement", None)
            entities.setdefault("location_valid", True)
            entities.setdefault("location_rejection_reason", None)
            entities.setdefault("location_auto_create", False)

            result["method"] = "groq"

            return result

        except Exception as e:
            print(f"GROQ CLASSIFICATION ERROR: {e}")
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "method": "groq_error",
                "entities": {
                    "auto_create": False,
                    "valid": True,
                    "rejection_reason": None,
                    "product_type": None,
                    "default_measurement": None,
                },
                "error": str(e),
            }

    def classify_with_fallback(self, text: str) -> dict:
        result = self.classify(text)

        if result["intent"] == "unknown" or result.get("confidence", 0) < 0.3:
            from intents.classifier import IntentClassifier
            fallback = IntentClassifier()
            fallback_result = fallback.classify(text)

            # Merge: take entities from Groq (rejected products still respected)
            groq_entities = result.get("entities", {})
            return {
                "intent": fallback_result["intent"],
                "confidence": fallback_result["confidence"],
                "method": f"fallback_{fallback_result['method']}",
                "entities": {
                    **groq_entities,
                    "auto_create": False,
                    "valid": True,
                    "rejection_reason": None,
                    "product_type": None,
                    "default_measurement": None,
                    "location_valid": True,
                    "location_rejection_reason": None,
                    "location_auto_create": False,
                },
            }

        return result

    def resolve_with_context(self, text: str, listings: list) -> dict:
        """
        Resolve user intent with listing context.
        Used when user references listings they've already viewed.

        Args:
            text: User message (e.g., "update the fourth one to price 200")
            listings: List of listings user has viewed, each with:
                [id, user_id, product_id, quantity, measurement, price, town, region, origin, image_url, expires_at, created_at, updated_at, product_name]

        Returns:
            dict with keys: listing_id, updates
        """
        print(f"=== RESOLVE_WITH_CONTEXT ===")
        print(f"User text: {text}")
        print(f"Listings count: {len(listings)}")

        listings_context = []
        for idx, listing in enumerate(listings, 1):
            listings_context.append({
                "number": idx,
                "listing_id": listing[0],
                "product": listing[13] if len(listing) > 13 else "Unknown",
                "quantity": listing[3],
                "measurement": listing[4],
                "price": listing[5],
                "location": f"{listing[6] or 'Not specified'}, {listing[7]}",
            })

        context_str = json.dumps(listings_context, indent=2)

        prompt = f"""The user has viewed these listings:
{context_str}

User message: "{text}"

Determine:
1. Which listing number (1-{len(listings)}) the user is referring to
2. What updates they want to make (price, quantity, measurement, location, region, origin)

Respond with JSON:
{{
    "listing_number": <number 1-{len(listings)}>,
    "updates": {{
        "price": <numeric value or null>,
        "quantity": <numeric value or null>,
        "measurement": <measurement unit or null>,
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
- Extract measurement from: "200kg" → "kg", "5 bags" → "bag", "2 hours" → "hour"
- If user doesn't specify which listing and there's only one, use listing_number: 1
- DO NOT confuse "price" with "rice" product
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

            listing_number = result.get("listing_number")
            if not listing_number or listing_number < 1 or listing_number > len(listings):
                return {"status": "error", "message": f"Invalid listing number. Please choose between 1 and {len(listings)}."}

            listing_id = listings[listing_number - 1][0]

            updates = result.get("updates", {})
            cleaned_updates = {}
            if updates.get("price"):
                cleaned_updates["price"] = updates["price"]
            if updates.get("quantity"):
                cleaned_updates["quantity"] = updates["quantity"]
            if updates.get("measurement"):
                cleaned_updates["measurement"] = updates["measurement"]
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
                "updates": cleaned_updates,
            }

        except Exception as e:
            print(f"GROQ CONTEXT RESOLUTION ERROR: {e}")
            return {
                "status": "error",
                "message": "Failed to understand which listing you're referring to. Please be more specific."
            }
