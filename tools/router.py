from core.pipeline import AssistantPipeline
from db.controller.userController import get_user_role
from db.controller.listingController import get_listings, create_listing

class ToolRouter:
    def __init__(self):
        self.pipeline = AssistantPipeline()

    def handle(self, text: str, user_id: str) -> dict:
        result = self.pipeline.process(text)
        intent = result["intent"]["intent"]
        entities = result["entities"]

        routes = {
            "create_listing":  self._create_listing,
            "search_listings": self._search_listings,
            "get_my_listings": self._get_my_listings,
            "delete_listing":  self._delete_listing,
            "update_listing":  self._update_listing,
        }

        handler = routes.get(intent, self._unknown)
        return handler(entities, user_id)

    def _create_listing(self, entities, user_id):
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
            region="General"
        )

    def _search_listings(self, entities, user_id):
        listings = get_listings(
            crop_name=entities.get("product"),
            town=entities.get("location"),
        )
        return {"status": "ok", "data": listings, "filters": entities}

    def _get_my_listings(self, entities, user_id):
        # user_id will come from the API layer later
        listings = get_listings(crop_name=entities.get("product"))
        return {"status": "ok", "data": listings}
    def _delete_listing(self, entities, user_id):
        print(f"delete listing {entities}")
        return {"status": "ok", "message": f"delete listings for {entities}"}
    def _update_listing(self, entities, user_id):
        print(f"updating listing f{entities}")
        return {"status": "ok", "message": f"updating listings for {entities}"}
    def _unknown(self, entities, user_id):
        print(f"we don't know what is happening here f{entities}")
        return {"status": "ok", "message": f"can't find what you want for {entities}"}