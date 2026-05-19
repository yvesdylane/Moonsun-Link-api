from core.pipeline import AssistantPipeline

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
        return {}
    def _search_listings(self, entities): ...
    def _get_my_listings(self, entities): ...
    def _delete_listing(self, entities): ...
    def _update_listing(self, entities): ...
    def _unknown(self, entities): ...