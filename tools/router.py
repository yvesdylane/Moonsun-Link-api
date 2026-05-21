from core.pipeline import AssistantPipeline
from db.controller.listingController import get_listings

class ToolRouter:
    def __init__(self):
        self.pipeline = AssistantPipeline()

    def handle(self, text: str) -> dict:
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
        return handler(entities)

    def _create_listing(self, entities):
        print(f"creating listing for {entities}")
        return {"status": "ok", "message": f"creating listings for {entities}"}

    def _search_listings(self, entities):
        listings = get_listings(
            crop_name=entities.get("product"),
            town=entities.get("location"),
        )
        return {"status": "ok", "data": listings, "filters": entities}

    def _get_my_listings(self, entities):
        # user_id will come from the API layer later
        listings = get_listings(crop_name=entities.get("product"))
        return {"status": "ok", "data": listings}
    def _delete_listing(self, entities):
        print(f"delete listing {entities}")
        return {"status": "ok", "message": f"delete listings for {entities}"}
    def _update_listing(self, entities):
        print(f"updating listing f{entities}")
        return {"status": "ok", "message": f"updating listings for {entities}"}
    def _unknown(self, entities):
        print(f"we don't know what is happening here f{entities}")
        return {"status": "ok", "message": f"can't find what you want for {entities}"}