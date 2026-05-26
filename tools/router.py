from core.pipeline import AssistantPipeline
from db.controller.userController import get_user_role
from db.controller.listingController import get_listings, create_listing, delete_listing, update_listing
from db.controller.stateController import get_state, set_state, clear_state
from utils.formatter import format_listing_item


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

        if state and state["state"] == "browsing_listings":
            if text.strip().lower() in ("next", "suivant"):
                result = self._browse_page(user_id, state["context"], direction=1)
                result["language"] = state["context"].get("language", "en")
                return result
            elif text.strip().lower() in ("previous", "prev", "précédent", "retour"):
                result = self._browse_page(user_id, state["context"], direction=-1)
                result["language"] = state["context"].get("language", "en")
                return result

        if state and state["state"] == "awaiting_verification_selfie":
            result = self._handle_verification_selfie(user_id, image_url)
            result["language"] = "en"
            return result

        if state and state["state"] == "awaiting_verification_id":
            result = self._handle_verification_id(user_id, image_url)
            result["language"] = "en"
            return result

        pipeline_result = self.pipeline.process(text)
        intent = pipeline_result["intent"]["intent"]
        entities = pipeline_result["entities"]
        language = pipeline_result["language"]

        routes = {
            "create_listing": self._create_listing,
            "search_listings": self._search_listings,
            "get_my_listings": self._get_my_listings,
            "delete_listing": self._delete_listing,
            "update_listing": self._update_listing,
            "greeting": self._greeting,
            "get_my_info": self._get_my_info,
            "verify_account": self._verify_account,
            "change_role": self._change_role,
            "update_profile": self._update_profile,
        }

        handler = routes.get(intent, self._unknown)
        result = handler(entities, user_id, image_url)
        result["language"] = language
        return result

    def _greeting(self, entities, user_id, image_url=None):
        from db.controller.userController import get_user_info

        user = get_user_info(user_id)

        if user and user.is_buyer():
            return {
                "status": "ok",
                "message": (
                    "👋 Hello! Welcome to Moonso Link.\n\n"
                    "Here's what I can help you with:\n"
                    "🔍 *Find products* — 'Find tomatoes in Douala'\n"
                    "👤 *View profile* — 'Show my info'\n"
                    "🌾 *Become a farmer* — 'Change my role to farmer in [Region]'\n\n"
                    "Just send a message or voice note 🎙️"
                )
            }

        return {
            "status": "ok",
            "message": (
                "👋 Hello! Welcome to Moonso Link.\n\n"
                "Here's what I can help you with:\n"
                "🌾 *Sell a product* — 'I want to sell 50kg of corn at 200 XAF'\n"
                "🔍 *Find products* — 'Find tomatoes in Douala'\n"
                "📋 *My listings* — 'Show me my listings'\n"
                "🗑️ *Delete listing* — 'Delete my corn listing'\n"
                "✏️ *Update listing* — 'Update my corn price to 300 XAF'\n"
                "👤 *View profile* — 'Show my info'\n"
                "✅ *Get verified* — 'Verify my account'\n\n"
                "Just send a message or voice note 🎙️"
            )
        }

    def _create_listing(self, entities, user_id, image_url=None):
        from db.controller.userController import get_user_info

        user = get_user_info(user_id)
        if not user:
            return {"status": "error", "message": "User not found"}

        if not user.is_farmer():
            return {"status": "error", "message": "Only farmers can create listings. To become a farmer, send: 'change my role to farmer in [your region]'"}

        if not user.is_verified():
            return {
                "status": "error",
                "message": "⚠️ Only verified farmers can create listings.\n\nYour listings won't be visible to buyers until you verify your account.\n\nTo verify, send: 'verify my account'"
            }

        if not entities.get("product"):
            return {"status": "error", "message": "What crop do you want to sell?"}
        if not entities.get("quantity"):
            return {"status": "error", "message": "How many kg do you want to sell?"}
        if not entities.get("price"):
            return {"status": "error", "message": "What is your price per kg in XAF?"}

        result = create_listing(
            user_id=user_id,
            crop_name=entities.get("product"),
            quantity=entities.get("quantity"),
            price=entities.get("price"),
            town=entities.get("location"),
            region="General",
            image_url=image_url
        )

        if result["status"] == "error":
            return result

        return self._listing_preview(result["listing_id"], user_id)

    def _search_listings(self, entities, user_id, image_url=None):
        filters = {
            "crop_name": entities.get("product"),
            "town": entities.get("location"),
        }
        result = get_listings(page=1, **filters)
        if result["total_pages"] > 1:
            set_state(user_id, "browsing_listings", {
                "filters": filters,
                "page": 1,
                "show_seller": True
            })
        return {"status": "ok", "data": result, "show_seller": True}

    def _get_my_listings(self, entities, user_id, image_url=None):
        filters = {"crop_name": entities.get("product"), "user_id": user_id, "include_unverified": True}
        result = get_listings(page=1, **filters)
        if result["total_pages"] > 1:
            set_state(user_id, "browsing_listings", {
                "filters": filters,
                "page": 1,
                "show_seller": False
            })
        return {"status": "ok", "data": result, "show_seller": False}

    def _browse_page(self, user_id: str, context: dict, direction: int) -> dict:
        page = context["page"] + direction
        filters = context["filters"]
        result = get_listings(page=page, **filters)
        if page >= result["total_pages"]:
            clear_state(user_id)
        else:
            context["page"] = page
            set_state(user_id, "browsing_listings", context)
        return {"status": "ok", "data": result}

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

        result = get_listings(crop_name=entities.get("product"), user_id=user_id)
        listings = result["listings"]

        if not listings:
            return {"status": "error", "message": f"You have no {entities.get('product')} listings"}

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
            update_result = update_listing(listing_id=listings[0][0], user_id=user_id, updates=updates)
            if update_result["status"] == "error":
                return update_result
            return self._listing_preview(listings[0][0], user_id)

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
            update_result = update_listing(listing_id=listing_id, user_id=user_id, updates=updates)
            if update_result["status"] == "error":
                return update_result
            return self._listing_preview(listing_id, user_id)
        except ValueError:
            return {"status": "error", "message": f"Please reply with a number between 1 and {len(listings)}"}

    def _handle_verification_selfie(self, user_id: str, image_url: str) -> dict:
        if not image_url:
            return {
                "status": "error",
                "message": "📸 Please send a photo of yourself (selfie).\n\nJust send the image directly - no need to caption it.\n\nAccepted formats: JPEG, PNG, PDF (max 2MB)"
            }

        # Store selfie URL in state context (will overwrite if resent)
        state = get_state(user_id)
        context = state.get("context", {}) if state else {}
        context["selfie_url"] = image_url

        set_state(user_id, "awaiting_verification_id", context)

        return {
            "status": "ok",
            "message": "✅ Selfie received!\n\nStep 2 of 2: Send a photo of your ID card\n\nJust send the image directly.\n\nAccepted formats: JPEG, PNG, PDF\nMax size: 2MB"
        }

    def _handle_verification_id(self, user_id: str, image_url: str) -> dict:
        from db.controller.userController import submit_verification_files
        from utils.verification_uploader import upload_verification_file
        from utils.audio_downloader import download_attachment
        import tempfile
        import requests

        state = get_state(user_id)
        if not state or "selfie_url" not in state["context"]:
            clear_state(user_id)
            return {"status": "error", "message": "Verification session expired. Please start again by sending 'verify my account'"}

        if not image_url:
            return {
                "status": "error",
                "message": "🆔 Please send a photo of your ID card.\n\nJust send the image directly.\n\nAccepted formats: JPEG, PNG, PDF (max 2MB)"
            }

        selfie_url = state["context"]["selfie_url"]

        # Download and upload selfie to correct location
        try:
            # Download selfie from Cloudinary (currently in wrong location)
            selfie_response = requests.get(selfie_url)
            suffix_selfie = "." + selfie_url.rsplit(".", 1)[-1].split("?")[0]
            tmp_selfie = tempfile.NamedTemporaryFile(suffix=suffix_selfie, delete=False)
            tmp_selfie.write(selfie_response.content)
            tmp_selfie.close()

            # Upload to correct location
            selfie_upload = upload_verification_file(tmp_selfie.name, user_id, "selfie")
            import os
            os.unlink(tmp_selfie.name)

            if selfie_upload["status"] == "error":
                clear_state(user_id)
                return selfie_upload

            # Download and upload ID
            id_response = requests.get(image_url)
            suffix_id = "." + image_url.rsplit(".", 1)[-1].split("?")[0]
            tmp_id = tempfile.NamedTemporaryFile(suffix=suffix_id, delete=False)
            tmp_id.write(id_response.content)
            tmp_id.close()

            # Upload ID to correct location
            id_upload = upload_verification_file(tmp_id.name, user_id, "id")
            os.unlink(tmp_id.name)

            if id_upload["status"] == "error":
                clear_state(user_id)
                return id_upload

            clear_state(user_id)

            # Submit both files for verification (sets status to pending)
            result = submit_verification_files(user_id, selfie_upload["url"], id_upload["url"])
            return result

        except Exception as e:
            clear_state(user_id)
            print(f"VERIFICATION FILE PROCESSING ERROR: {e}")
            return {
                "status": "error",
                "message": "Failed to process verification files. Please try again."
            }

    def _listing_preview(self, listing_id: int, user_id: str) -> dict:
        result = get_listings(page=1, limit=1, user_id=user_id)
        # find the specific listing by id
        listing = next((l for l in result["listings"] if l[0] == listing_id), None)
        if listing:
            return {
                "status": "ok",
                "message": f"✅ Listing updated! Here is how it looks to buyers:\n\n{format_listing_item(listing, show_seller=False)}",
                "preview_image": listing[8],
            }
        return {"status": "ok", "message": "✅ Listing updated successfully"}

    def _get_my_info(self, entities, user_id, image_url=None):
        from db.controller.userController import get_user_info

        user = get_user_info(user_id)
        if not user:
            return {"status": "error", "message": "User not found"}

        info = (
            f"👤 *Your Profile*\n\n"
            f"Name: {user.name}\n"
            f"Phone: {user.phone or 'Not set'}\n"
            f"Role: {user.role.capitalize()}\n"
            f"Region: {user.region}\n"
            f"Language: {user.get_lang_display()}\n"
            f"Status: {user.get_verification_status_display()}\n"
        )

        if user.is_farmer() and not user.is_verified():
            info += f"\n⚠️ To make your listings visible, send: 'verify my account'"

        return {"status": "ok", "message": info}

    def _verify_account(self, entities, user_id, image_url=None):
        from db.controller.userController import get_user_info, check_verification_status

        user = get_user_info(user_id)
        if not user:
            return {"status": "error", "message": "User not found"}

        if not user.is_farmer():
            return {
                "status": "error",
                "message": "Verification is only required for farmers. To become a farmer, send: 'change my role to farmer in [your region]'"
            }

        # Check current verification status
        status_result = check_verification_status(user_id)

        if user.is_verified():
            return status_result

        # Start verification process
        set_state(user_id, "awaiting_verification_selfie", {})
        return {
            "status": "ok",
            "message": "📸 *Verification Process*\n\nStep 1 of 2: Send a clear photo of yourself (selfie)\n\nAccepted formats: JPEG, PNG, PDF\nMax size: 2MB"
        }

    def _change_role(self, entities, user_id, image_url=None):
        from db.controller.userController import change_role_to_farmer, get_user_info

        user = get_user_info(user_id)
        if not user:
            return {"status": "error", "message": "User not found"}

        if user.is_farmer():
            return {"status": "error", "message": "You are already a farmer. To change your region, send: 'update my region to [region name]'"}

        region = entities.get("region")
        if not region:
            return {
                "status": "error",
                "message": "Please specify your primary region of activity.\n\nExample: 'change my role to farmer in Littoral'\n\nAvailable regions: Littoral, Centre, Ouest, Nord, Sud, etc."
            }

        return change_role_to_farmer(user_id, region)

    def _update_profile(self, entities, user_id, image_url=None):
        from db.controller.userController import update_user_info

        updates = {}

        if entities.get("name"):
            updates["name"] = entities.get("name")
        if entities.get("region"):
            updates["region"] = entities.get("region")

        if not updates:
            return {
                "status": "error",
                "message": "What would you like to update?\n\nYou can update:\n- Your name\n- Your region"
            }

        return update_user_info(user_id, updates)

    def _unknown(self, entities, user_id, image_url=None):
        return {"status": "error", "message": "I didn't understand that. Try asking to sell, find, or delete a listing."}

