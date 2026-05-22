from core.pipeline import AssistantPipeline
from db.controller.userController import get_user_role
from db.controller.listingController import get_listings, create_listing, delete_listing, update_listing
from db.controller.stateController import get_state, set_state, clear_state

class ToolRouter:
    def __init__(self):
        self.pipeline = AssistantPipeline()

    def handle(self, text: str, user_id: str, image_url: str = None) -> dict:
        state = get_state(user_id)
        if state and state["state"] == "awaiting_delete_choice":
            result = self._handle_delete_choice(text, user_id, state["context"])
            result["language"] = "en"
            return result

        if state and state["state"] == "awaiting_update_choice":
            result = self._handle_update_choice(text, user_id, state["context"])
            result["language"] = "en"
            return result

        pipeline_result = self.pipeline.process(text)
        intent = pipeline_result["intent"]["intent"]
        entities = pipeline_result["entities"]
        language = pipeline_result["language"]

        routes = {
            "create_listing":  self._create_listing,
            "search_listings": self._search_listings,
            "get_my_listings": self._get_my_listings,
            "delete_listing":  self._delete_listing,
            "update_listing":  self._update_listing,
        }

        handler = routes.get(intent, self._unknown)
        result = handler(entities, user_id, image_url)
        result["language"] = language
        return result

    def _create_listing(self, entities, user_id, image_url=None):
        role = get_user_role(user_id)
        if role != "farmer":
            return {"status": "error", "message": "Only farmers can create listings"}
        if not entities.get("product"):
            return {"status": "error", "message": "What crop do you want to sell?"}
        if not entities.get("quantity"):
            return {"status": "error", "message": "How many kg do you want to sell?"}
        if not entities.get("price"):
            return {"status": "error", "message": "What is your price per kg in XAF?"}

        return create_listing(
            user_id=user_id,
            crop_name=entities.get("product"),
            quantity=entities.get("quantity"),
            price=entities.get("price"),
            town=entities.get("location"),
            region="General",
            image_url=image_url
        )

    def _search_listings(self, entities, user_id, image_url=None):
        listings = get_listings(
            crop_name=entities.get("product"),
            town=entities.get("location"),
        )
        return {"status": "ok", "data": listings, "filters": entities}

    def _get_my_listings(self, entities, user_id, image_url=None):
        listings = get_listings(
            crop_name=entities.get("product"),
            user_id=user_id
        )
        return {"status": "ok", "data": listings}

    def _delete_listing(self, entities, user_id, image_url=None):
        if not entities.get("product"):
            return {"status": "error", "message": "Which crop listing do you want to delete?"}

        listings = get_listings(crop_name=entities.get("product"), user_id=user_id)

        if not listings:
            return {"status": "error", "message": f"You have no {entities.get('product')} listings"}

        if len(listings) == 1:
            clear_state(user_id)
            return delete_listing(listing_id=listings[0][0], user_id=user_id)

        options = "\n".join([
            f"{i+1}) {l[3]}kg at {l[4]} XAF"
            for i, l in enumerate(listings)
        ])
        set_state(user_id, "awaiting_delete_choice", {
            "listings": [[l[0], l[3], l[4]] for l in listings]
        })
        return {"status": "ok", "message": f"Which listing do you want to delete?\n{options}"}

    def _handle_delete_choice(self, text: str, user_id: str, context: dict) -> dict:
        listings = context["listings"]
        try:
            choice = int(text.strip()) - 1
            if choice < 0 or choice >= len(listings):
                return {"status": "error", "message": f"Please reply with a number between 1 and {len(listings)}"}
            listing_id = listings[choice][0]
            clear_state(user_id)
            return delete_listing(listing_id=listing_id, user_id=user_id)
        except ValueError:
            return {"status": "error", "message": f"Please reply with a number between 1 and {len(listings)}"}

    def _update_listing(self, entities, user_id, image_url=None):
        if not entities.get("product"):
            return {"status": "error", "message": "Which crop listing do you want to update?"}

        listings = get_listings(crop_name=entities.get("product"), user_id=user_id)

        if not listings:
            return {"status": "error", "message": f"You have no {entities.get('product')} listings"}

        # build update fields from entities
        updates = {}
        if entities.get("price"):
            updates["price"] = entities.get("price")
        if entities.get("quantity"):
            updates["quantity_kg"] = entities.get("quantity")
        if entities.get("location"):
            updates["town"] = entities.get("location")
        if entities.get("region"):
            updates["region"] = entities.get("region")
        if entities.get("origin"):
            updates["origin"] = entities.get("origin")
        if image_url:
            updates["image_url"] = image_url

        if not updates:
            return {"status": "error",
                    "message": "What do you want to update? You can change the price, quantity, town, region, origin or image."}

        if len(listings) == 1:
            clear_state(user_id)
            return update_listing(listing_id=listings[0][0], user_id=user_id, updates=updates)

        # multiple listings — ask which one
        options = "\n".join([
            f"{i + 1}) {l[3]}kg at {l[4]} XAF"
            for i, l in enumerate(listings)
        ])
        set_state(user_id, "awaiting_update_choice", {
            "listings": [[l[0], l[3], l[4]] for l in listings],
            "updates": updates
        })
        return {"status": "ok", "message": f"Which listing do you want to update?\n{options}"}

    def _handle_update_choice(self, text: str, user_id: str, context: dict) -> dict:
        listings = context["listings"]
        updates = context["updates"]
        try:
            choice = int(text.strip()) - 1
            if choice < 0 or choice >= len(listings):
                return {"status": "error", "message": f"Please reply with a number between 1 and {len(listings)}"}
            listing_id = listings[choice][0]
            clear_state(user_id)
            return update_listing(listing_id=listing_id, user_id=user_id, updates=updates)
        except ValueError:
            return {"status": "error", "message": f"Please reply with a number between 1 and {len(listings)}"}

    def _unknown(self, entities, user_id, image_url=None):
        return {"status": "error", "message": "I didn't understand that. Try asking to sell, find, or delete a listing."}