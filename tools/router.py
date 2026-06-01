import traceback
from core.pipeline import AssistantPipeline
from db.controller.userController import get_user_role
from db.controller.listingController import get_listings, create_listing, delete_listing, update_listing
from db.controller.stateController import get_state, set_state, clear_state
from utils.formatter import format_listing_item


class ToolRouter:
    def __init__(self):
        self.pipeline = AssistantPipeline()

    def handle(self, text: str, user_id: str, image_url: str = None) -> dict:
        try:
            return self._handle_inner(text, user_id, image_url)
        except Exception as e:
            print("=" * 60)
            print(f"UNHANDLED ERROR IN ROUTER: {e}")
            traceback.print_exc()
            print("=" * 60)
            from db.connect import conn
            try:
                conn.rollback()
                print("Transaction rolled back successfully")
            except:
                pass
            return {
                "status": "error",
                "message": "Sorry, an error occurred on our side. Please try again later."
            }

    def _check_new_intent(self, text: str):
        pipeline_result = self.pipeline.process(text)
        intent = pipeline_result["intent"]["intent"]
        confidence = pipeline_result["intent"]["confidence"]
        if intent not in ("unknown", "greeting") and confidence >= 0.5:
            return pipeline_result
        return None

    def _handle_inner(self, text: str, user_id: str, image_url: str = None) -> dict:
        state = get_state(user_id)

        if state:
            new_pipeline = self._check_new_intent(text)

            # ── awaiting_delete_choice ─────────────────────────────────
            if state["state"] == "awaiting_delete_choice":
                if text.strip().isdigit():
                    result = self._handle_delete_choice(text, user_id, state["context"])
                    result["language"] = "en"
                    return result
                if new_pipeline:
                    clear_state(user_id)
                else:
                    context = state.get("context", {})
                    listings = context.get("listings", [])
                    return {
                        "status": "error",
                        "message": f"Please reply with a number between 1 and {len(listings)}"
                    }

            # ── awaiting_update_choice ─────────────────────────────────
            if state["state"] == "awaiting_update_choice":
                if text.strip().isdigit():
                    result = self._handle_update_choice(text, user_id, state["context"])
                    result["language"] = "en"
                    return result
                if new_pipeline:
                    clear_state(user_id)
                else:
                    context = state.get("context", {})
                    listings = context.get("listings", [])
                    return {
                        "status": "error",
                        "message": f"Please reply with a number between 1 and {len(listings)}"
                    }

            # ── browsing_listings ──────────────────────────────────────
            if state["state"] == "browsing_listings":
                lower = text.strip().lower()
                if lower in ("next", "suivant"):
                    result = self._browse_page(user_id, state["context"], direction=1)
                    result["language"] = state["context"].get("language", "en")
                    return result
                if lower in ("previous", "prev", "précédent", "retour"):
                    result = self._browse_page(user_id, state["context"], direction=-1)
                    result["language"] = state["context"].get("language", "en")
                    return result
                if new_pipeline:
                    intent = new_pipeline["intent"]["intent"]
                    if intent in ("update_listing", "delete_listing", "show_interest", "view_listing_image"):
                        pass
                    else:
                        clear_state(user_id)
                elif not new_pipeline:
                    return {
                        "status": "error",
                        "message": "Reply 'next' or 'previous' to browse pages, or send a new request."
                    }

            # ── awaiting_verification_selfie ──────────────────────────
            if state["state"] == "awaiting_verification_selfie":
                if image_url:
                    result = self._handle_verification_selfie(user_id, image_url)
                    result["language"] = "en"
                    return result
                if new_pipeline:
                    clear_state(user_id)
                else:
                    return {
                        "status": "error",
                        "message": "📸 Please send a photo of yourself (selfie).\n\nJust send the image directly - no need to caption it.\n\nAccepted formats: JPEG, PNG, PDF (max 2MB)"
                    }

            # ── awaiting_verification_id ───────────────────────────────
            if state["state"] == "awaiting_verification_id":
                if image_url:
                    result = self._handle_verification_id(user_id, image_url)
                    result["language"] = "en"
                    return result
                if new_pipeline:
                    clear_state(user_id)
                else:
                    return {
                        "status": "error",
                        "message": "🆔 Please send a photo of your ID card.\n\nJust send the image directly.\n\nAccepted formats: JPEG, PNG, PDF (max 2MB)"
                    }

            # ── awaiting_location ──────────────────────────────────────
            if state["state"] == "awaiting_location":
                if new_pipeline and new_pipeline["intent"]["confidence"] > 0.7:
                    clear_state(user_id)
                else:
                    result = self._handle_location_input(text, user_id, state["context"])
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
            "show_available_products": self._show_available_products,
            "product_locations": self._product_locations,
            "show_interest": self._show_interest,
            "view_listing_interests": self._view_listing_interests,
            "get_my_interests": self._get_my_interests,
            "cancel_interest": self._cancel_interest,
            "reject_interest": self._reject_interest,
            "search_by_price": self._search_by_price,
            "view_listing_image": self._view_listing_image,
            "get_crop_price": self._get_crop_price,
            "get_all_crop_prices": self._get_all_crop_prices,
        }

        handler = routes.get(intent, self._unknown)
        result = handler(entities, user_id, image_url, text)
        result["language"] = language
        return result

    def _greeting(self, entities, user_id, image_url=None, text=""):
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

    def _create_listing(self, entities, user_id, image_url=None, text=""):
        from db.controller.userController import get_user_info
        from db.controller.productController import create_product

        user = get_user_info(user_id)
        if not user:
            return {"status": "error", "message": "User not found"}

        if not user.is_farmer():
            return {"status": "error", "message": "Only farmers can create listings. To become a farmer, send: 'change my role to farmer in [your region]'"}

        # Check if Groq rejected the product as non-agriculture
        if entities.get("valid") is False:
            reason = entities.get("rejection_reason", "This product is not supported on Moonso Link.")
            return {"status": "error", "message": reason}

        if not entities.get("product"):
            return {"status": "error", "message": "What product do you want to sell?"}
        if not entities.get("quantity"):
            return {"status": "error", "message": "How much do you want to sell?"}
        if not entities.get("price"):
            return {"status": "error", "message": "What is your price in XAF?"}

        product_name = entities.get("product")

        # Auto-create product if it's not in the DB yet
        if entities.get("auto_create"):
            product_type = entities.get("product_type", "crop")
            default_measurement = entities.get("default_measurement")
            new_id = create_product(product_name, product_type, default_measurement)
            if not new_id:
                return {"status": "error", "message": f"Could not create product '{product_name}'. Please try again later."}

        compressed_image_url = image_url
        if image_url:
            from utils.image_compressor import compress_image
            from utils.cloudinary_uploader import upload_to_cloudinary
            try:
                compressed_path = compress_image(image_url)
                compressed_image_url = upload_to_cloudinary(compressed_path, folder="moonso/listings")
            except Exception as e:
                print(f"Image compression/upload failed: {e}")
                compressed_image_url = image_url

        result = create_listing(
            user_id=user_id,
            product_name=product_name,
            quantity=entities.get("quantity"),
            measurement=entities.get("measurement"),
            price=entities.get("price"),
            town=entities.get("location"),
            region=entities.get("region"),
            origin=entities.get("region"),
            image_url=compressed_image_url,
        )

        if result["status"] == "error":
            return result

        measurement = result.get("measurement", "kg")
        message = f"✅ Listing created! Your {result['quantity']}{measurement} of {result['product_name'].capitalize()} at {result['price']} XAF/{measurement}"

        if entities.get("auto_create"):
            message = f"🆕 New product '{product_name.capitalize()}' added to our catalog!\n\n" + message

        if entities.get("location_valid") is False:
            reason = entities.get("location_rejection_reason", "We only support locations in Cameroon.")
            message += f"\n\n⚠️ *{reason}*"

        if result.get("missing_location"):
            message += (
                f"\n\n⚠️ Location not specified - Buyers prefer to know where products are sold.\n\n"
                f"Send the town name (e.g., 'Yaoundé', 'Douala') to add location, or send another command to skip."
            )
            set_state(user_id, "awaiting_location", {
                "listing_id": result["listing_id"],
                "product_name": result["product_name"],
                "quantity": result["quantity"],
                "measurement": measurement,
                "price": result["price"],
                "region": result["region"],
            })

        if not user.is_verified():
            message += (
                "\n\n⚠️ *Note:* Your listings won't be visible to buyers until you verify your account.\n\n"
                "To verify, send: 'verify my account'"
            )

        return {"status": "ok", "message": message}

    def _search_listings(self, entities, user_id, image_url=None, text=""):
        from db.controller.listingController import check_product_exists
        from db.controller.productPriceController import get_market_price_for_listing_search
        from utils.formatter import format_market_price_header

        filters = {
            "product_name": entities.get("product"),
            "town": entities.get("location"),
            "region": entities.get("region"),
            "max_price": entities.get("price"),
        }

        result = get_listings(page=1, **filters)

        market_price_header = None
        if entities.get("product"):
            market_price = get_market_price_for_listing_search(
                product_name=entities.get("product"),
                region=entities.get("region"),
            )
            if market_price:
                market_price_header = format_market_price_header(
                    market_price["product_name"],
                    market_price.get("avg_price") or market_price.get("overall_avg"),
                    "regional" if market_price.get("region") else "overall",
                    market_price.get("region"),
                )

        if result["total"] > 0:
            from datetime import datetime
            listing_ids = [str(listing[0]) for listing in result["listings"]]
            listings_details = []
            for listing in result["listings"]:
                serializable_listing = []
                for x in listing:
                    if hasattr(x, 'hex'):
                        serializable_listing.append(str(x))
                    elif isinstance(x, datetime):
                        serializable_listing.append(x.isoformat())
                    else:
                        serializable_listing.append(x)
                listings_details.append(serializable_listing)
            set_state(user_id, "browsing_listings", {
                "listing_ids": listing_ids,
                "listings_details": listings_details,
                "filters": filters,
                "page": 1,
                "show_seller": True,
            })

        if result["total"] == 0 and entities.get("product"):
            check_result = check_product_exists(
                product_name=entities.get("product"),
                region=entities.get("region"),
                max_price=entities.get("price"),
            )

            if not check_result["exists"]:
                if check_result["reason"] == "not_listed":
                    return {
                        "status": "ok",
                        "message": f"❌ No one is currently selling {entities.get('product')}.\n\nTo see available products, send: 'What products are available?'"
                    }

            elif not check_result.get("matches_criteria", True):
                feedback_parts = [f"⚠️ {entities.get('product').capitalize()} is listed but doesn't match your criteria:"]

                if "available_regions" in check_result:
                    regions_str = ", ".join(check_result["available_regions"])
                    feedback_parts.append(f"\n📍 You searched in: {check_result['searched_region']}")
                    feedback_parts.append(f"✅ Available in: {regions_str}")

                if "min_price" in check_result:
                    feedback_parts.append(f"\n💰 Your max price: {check_result['max_price_searched']} XAF")
                    feedback_parts.append(f"✅ Lowest price: {check_result['min_price']} XAF")

                feedback_parts.append(f"\n\nTo see all {entities.get('product')} listings, send: 'Find {entities.get('product')}'")

                return {"status": "ok", "message": "".join(feedback_parts)}

        return_data = {"status": "ok", "data": result, "show_seller": True}
        if market_price_header:
            return_data["market_price_header"] = market_price_header
        return return_data

    def _get_my_listings(self, entities, user_id, image_url=None, text=""):
        from datetime import datetime
        filters = {"product_name": entities.get("product"), "user_id": user_id, "include_unverified": True}
        result = get_listings(page=1, **filters)
        listing_ids = [str(listing[0]) for listing in result["listings"]] if result["total"] > 0 else []
        listings_details = []
        if result["total"] > 0:
            for listing in result["listings"]:
                serializable_listing = []
                for x in listing:
                    if hasattr(x, 'hex'):
                        serializable_listing.append(str(x))
                    elif isinstance(x, datetime):
                        serializable_listing.append(x.isoformat())
                    else:
                        serializable_listing.append(x)
                listings_details.append(serializable_listing)
        set_state(user_id, "browsing_listings", {
            "listing_ids": listing_ids,
            "listings_details": listings_details,
            "filters": filters,
            "page": 1,
            "show_seller": False,
        })
        return {"status": "ok", "data": result, "show_seller": False}

    def _browse_page(self, user_id: str, context: dict, direction: int) -> dict:
        page = context["page"] + direction

        if page < 1:
            return {"status": "error", "message": "You're already on the first page."}

        filters = context["filters"]
        result = get_listings(page=page, **filters)

        if page > result["total_pages"]:
            return {"status": "error", "message": f"No more pages. Total pages: {result['total_pages']}"}

        context["page"] = page
        set_state(user_id, "browsing_listings", context)
        return {"status": "ok", "data": result}

    def _delete_listing(self, entities, user_id, image_url=None, text=""):
        if not entities.get("product"):
            return {"status": "error", "message": "Which product listing do you want to delete?"}

        result = get_listings(product_name=entities.get("product"), user_id=user_id, include_unverified=True)
        listings = result["listings"]

        if not listings:
            return {"status": "error", "message": f"You have no {entities.get('product')} listings"}

        if len(listings) == 1:
            clear_state(user_id)
            return delete_listing(listing_id=listings[0][0], user_id=user_id)

        # l[3]=quantity, l[4]=measurement, l[5]=price
        options = "\n".join([
            f"{i+1}) {l[3]}{l[4] or 'kg'} at {l[5]} XAF"
            for i, l in enumerate(listings)
        ])
        set_state(user_id, "awaiting_delete_choice", {
            "listings": [[l[0], l[3], l[4], l[5]] for l in listings]
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

    def _update_listing(self, entities, user_id, image_url=None, text=""):
        state = get_state(user_id)

        if state and "listings_details" in state.get("context", {}):
            listings_details = state["context"]["listings_details"]

            from intents.groq_classifier import GroqIntentClassifier
            classifier = GroqIntentClassifier()

            resolution = classifier.resolve_with_context(text, listings_details)

            if resolution["status"] == "ok":
                listing_id = resolution["listing_id"]
                updates = resolution["updates"]

                if image_url:
                    updates["image_url"] = image_url

                if not updates:
                    return {"status": "error", "message": "What do you want to update? You can change the price, quantity, town, region, origin or image."}

                clear_state(user_id)
                update_result = update_listing(listing_id=listing_id, user_id=user_id, updates=updates)
                if update_result["status"] == "error":
                    return update_result
                return self._listing_preview(listing_id, user_id)

        if not entities.get("product"):
            return {"status": "error", "message": "Which product listing do you want to update?"}

        result = get_listings(product_name=entities.get("product"), user_id=user_id, include_unverified=True)
        listings = result["listings"]

        if not listings:
            return {"status": "error", "message": f"You have no {entities.get('product')} listings"}

        updates = {}
        if entities.get("price"):
            updates["price"] = entities.get("price")
        if entities.get("quantity"):
            updates["quantity"] = entities.get("quantity")
        if entities.get("measurement"):
            updates["measurement"] = entities.get("measurement")
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

        # l[3]=quantity, l[4]=measurement, l[5]=price
        options = "\n".join([
            f"{i+1}) {l[3]}{l[4] or 'kg'} at {l[5]} XAF"
            for i, l in enumerate(listings)
        ])
        set_state(user_id, "awaiting_update_choice", {
            "listings": [[l[0], l[3], l[4], l[5]] for l in listings],
            "updates": updates,
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

        try:
            selfie_response = requests.get(selfie_url)
            suffix_selfie = "." + selfie_url.rsplit(".", 1)[-1].split("?")[0]
            tmp_selfie = tempfile.NamedTemporaryFile(suffix=suffix_selfie, delete=False)
            tmp_selfie.write(selfie_response.content)
            tmp_selfie.close()

            selfie_upload = upload_verification_file(tmp_selfie.name, user_id, "selfie")
            import os
            os.unlink(tmp_selfie.name)

            if selfie_upload["status"] == "error":
                clear_state(user_id)
                return selfie_upload

            id_response = requests.get(image_url)
            suffix_id = "." + image_url.rsplit(".", 1)[-1].split("?")[0]
            tmp_id = tempfile.NamedTemporaryFile(suffix=suffix_id, delete=False)
            tmp_id.write(id_response.content)
            tmp_id.close()

            id_upload = upload_verification_file(tmp_id.name, user_id, "id")
            os.unlink(tmp_id.name)

            if id_upload["status"] == "error":
                clear_state(user_id)
                return id_upload

            clear_state(user_id)

            result = submit_verification_files(user_id, selfie_upload["url"], id_upload["url"])
            return result

        except Exception as e:
            clear_state(user_id)
            print(f"VERIFICATION FILE PROCESSING ERROR: {e}")
            return {"status": "error", "message": "Failed to process verification files. Please try again."}

    def _listing_preview(self, listing_id: int, user_id: str) -> dict:
        result = get_listings(page=1, limit=1, user_id=user_id)
        listing = next((l for l in result["listings"] if l[0] == listing_id), None)
        if listing:
            return {
                "status": "ok",
                "message": f"✅ Listing updated! Here is how it looks to buyers:\n\n{format_listing_item(listing, show_seller=False)}",
                "preview_image": listing[9],
            }
        return {"status": "ok", "message": "✅ Listing updated successfully"}

    def _get_my_info(self, entities, user_id, image_url=None, text=""):
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

    def _verify_account(self, entities, user_id, image_url=None, text=""):
        from db.controller.userController import get_user_info, check_verification_status

        user = get_user_info(user_id)
        if not user:
            return {"status": "error", "message": "User not found"}

        if not user.is_farmer():
            return {
                "status": "error",
                "message": "Verification is only required for farmers. To become a farmer, send: 'change my role to farmer in [your region]'"
            }

        status_result = check_verification_status(user_id)

        if user.is_verified():
            return status_result

        set_state(user_id, "awaiting_verification_selfie", {})
        return {
            "status": "ok",
            "message": "📸 *Verification Process*\n\nStep 1 of 2: Send a clear photo of yourself (selfie)\n\nAccepted formats: JPEG, PNG, PDF\nMax size: 2MB"
        }

    def _change_role(self, entities, user_id, image_url=None, text=""):
        from db.controller.userController import change_role_to_farmer, get_user_info

        user = get_user_info(user_id)
        if not user:
            return {"status": "error", "message": "User not found"}

        if user.is_farmer():
            return {"status": "error", "message": "You are already a farmer. To change your region, send: 'update my region to [region name]'"}

        region = entities.get("region")

        if not region:
            region = user.region if user.region else "General"

        if region == "General":
            set_state(user_id, "awaiting_region_for_role_change", {})
            return {
                "status": "ok",
                "message": (
                    "📍 *Region Required*\n\n"
                    "To become a farmer, please specify your primary region of operation.\n\n"
                    "This helps buyers find your products.\n\n"
                    "Send your region:\n"
                    "• Centre\n• Littoral\n• Nord\n• Sud\n• Ouest\n• Est\n"
                    "• Nord-Ouest\n• Sud-Ouest\n• Adamaoua\n• Extreme-Nord\n\n"
                    "Or send 'General' if you operate across all Cameroon."
                )
            }

        result = change_role_to_farmer(user_id, region)

        if result["status"] == "ok" and not user.is_verified():
            result["message"] += (
                "\n\n⚠️ *Verification Required*\n\n"
                "Your listings won't be visible to buyers until you verify your account.\n\n"
                "To get verified, send: 'verify my account'"
            )

        return result

    def _update_profile(self, entities, user_id, image_url=None, text=""):
        from db.controller.userController import update_user_info, change_role_to_farmer, get_user_info

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

        result = update_user_info(user_id, updates)

        state = get_state(user_id)
        if state and state["state"] == "awaiting_region_for_role_change" and updates.get("region"):
            clear_state(user_id)

            role_result = change_role_to_farmer(user_id, updates["region"])

            if role_result["status"] == "ok":
                user = get_user_info(user_id)
                result["message"] = (
                    f"✅ Profile updated! Region: {updates['region']}\n\n"
                    f"✅ Role changed to Farmer!"
                )

                if user and not user.is_verified():
                    result["message"] += (
                        "\n\n⚠️ *Verification Required*\n\n"
                        "Your listings won't be visible to buyers until you verify your account.\n\n"
                        "To get verified, send: 'verify my account'"
                    )

        return result

    def _show_available_products(self, entities, user_id, image_url=None, text=""):
        from db.controller.listingController import get_available_products

        products = get_available_products()

        if not products:
            return {
                "status": "ok",
                "message": "No products are currently available. Be the first to list a product!"
            }

        product_list = "\n".join([f"• {product.capitalize()}" for product in products])

        return {
            "status": "ok",
            "message": f"🌾 *Currently Available Products*\n\n{product_list}\n\nTo search for a specific product, send:\n'Find [product name]' or 'Find [product] in [location]'"
        }

    def _product_locations(self, entities, user_id, image_url=None, text=""):
        from db.controller.listingController import get_product_locations

        product = entities.get("product")
        if not product:
            return {
                "status": "error",
                "message": "Which product are you looking for?\n\nExample: 'Where is corn being sold?'"
            }

        result = get_product_locations(product)

        if result["status"] == "not_found":
            return {
                "status": "ok",
                "message": f"❌ No one is currently selling {product}.\n\nTo see what's available, send: 'What products are available?'"
            }

        if result["status"] == "error":
            return result

        regions_text = []
        for region, towns in result["regions"].items():
            if towns:
                towns_str = ", ".join(towns)
                regions_text.append(f"📍 *{region}*: {towns_str}")
            else:
                regions_text.append(f"📍 *{region}*")

        locations_formatted = "\n".join(regions_text)
        count_text = f"{result['count']} listing{'s' if result['count'] > 1 else ''}"

        return {
            "status": "ok",
            "message": f"🌾 *{product.capitalize()}* ({count_text})\n\nCurrently being sold in:\n\n{locations_formatted}\n\nTo see listings, send: 'Find {product}'"
        }

    def _show_interest(self, entities, user_id, image_url=None, text=""):
        from db.controller.listingInterestController import save_interest
        from db.controller.userController import get_user_info
        from utils.whatsapp import send_whatsapp_reply

        state = get_state(user_id)

        if not state or "listing_ids" not in state.get("context", {}):
            return {
                "status": "error",
                "message": "Please search for listings first.\n\nExample: 'Find corn in Douala'"
            }

        listing_ids = state["context"]["listing_ids"]

        listing_number = entities.get("listing_number")
        quantity = entities.get("quantity") or 1

        if not listing_number:
            return {
                "status": "error",
                "message": "Which listing are you interested in?\n\nExample: 'I'm interested in 40kg of listing #2'"
            }

        try:
            listing_index = int(listing_number) - 1
            if listing_index < 0 or listing_index >= len(listing_ids):
                return {
                    "status": "error",
                    "message": f"Invalid listing number. Please choose between 1 and {len(listing_ids)}."
                }
        except (ValueError, TypeError):
            return {
                "status": "error",
                "message": "Please provide a valid listing number.\n\nExample: 'interested in listing 2'"
            }

        listing_id = listing_ids[listing_index]

        result = save_interest(listing_id, user_id, quantity if quantity and quantity > 1 else None)

        if result["status"] == "error":
            return result

        listing = result["listing"]
        buyer = result["buyer"]
        seller_notif = result.get("seller_notification", {})

        clear_state(user_id)

        measurement_text = f"{listing.get('measurement', 'kg')}" if listing.get('measurement') else ""
        quantity_text = f"{quantity}{measurement_text} of " if quantity and quantity > 1 else ""
        buyer_message = (
            f"✅ Interest registered!\n\n"
            f"You're interested in {quantity_text}{listing['product_name'].capitalize()}\n"
            f"💰 Price: {listing['price']} XAF/{measurement_text if measurement_text else 'kg'}\n"
            f"👤 Farmer: {listing['seller_name']}\n\n"
            f"The farmer has been notified and will contact you at {buyer['phone']} if interested."
        )

        seller_notification = None
        if seller_notif.get("seller_whatsapp_chat_id") or seller_notif.get("seller_telegram_id"):
            quantity_text = f"📦 Quantity: {seller_notif['quantity']}{measurement_text}\n" if seller_notif.get('quantity') else ""
            seller_notification = {
                "whatsapp_chat_id": seller_notif.get("seller_whatsapp_chat_id"),
                "telegram_id": seller_notif.get("seller_telegram_id"),
                "message": (
                    f"🔔 *New Interest in Your Listing!*\n\n"
                    f"🌾 Product: {seller_notif['product_name'].capitalize()}\n"
                    f"{quantity_text}"
                    f"👤 Buyer: {seller_notif['buyer_name']}\n"
                    f"📞 Contact: {seller_notif['buyer_phone']}\n\n"
                    f"Contact them to complete the sale!"
                ),
            }

        return {
            "status": "ok",
            "message": buyer_message,
            "seller_notification": seller_notification,
        }

    def _view_listing_interests(self, entities, user_id, image_url=None, text=""):
        from db.controller.listingInterestController import get_listing_interests
        from db.controller.userController import get_user_info

        user = get_user_info(user_id)
        if not user or not user.is_farmer():
            return {
                "status": "error",
                "message": "Only farmers can view interests on their listings."
            }

        product_name = entities.get("product")
        result = get_listing_interests(user_id, product_name)

        if result["total"] == 0:
            return {"status": "ok", "message": result["message"]}

        lines = [f"👥 *Interests on Your Listings* ({result['total']} total)\n"]

        for listing_id, data in result["listings"].items():
            lines.append(f"🌾 *{data['product_name'].capitalize()}* - {data['quantity']}{data.get('measurement', 'kg')} at {data['price']} XAF")

            for interest in data["interests"]:
                lines.append(f"  • {interest['buyer_name']} ({interest['buyer_phone']})")
                if interest['quantity']:
                    lines.append(f"    Wants: {interest['quantity']}")
                if interest.get("message"):
                    lines.append(f"    Message: {interest['message']}")
                lines.append("")

        return {"status": "ok", "message": "\n".join(lines)}

    def _search_by_price(self, entities, user_id, image_url=None, text=""):
        from db.controller.listingController import search_by_price
        from db.controller.productPriceController import get_market_price_for_listing_search
        from utils.formatter import format_market_price_header

        product = entities.get("product")
        price = entities.get("price")

        if not product:
            return {
                "status": "error",
                "message": "Which product are you looking for?\n\nExample: 'Is anyone selling corn at 300 XAF?'"
            }

        if not price:
            return {
                "status": "error",
                "message": "What price are you looking for?\n\nExample: 'Find tomatoes at 200 XAF'"
            }

        result = search_by_price(product, price)

        if result["status"] == "not_found":
            return {"status": "ok", "message": result["message"]}

        if result["status"] == "ok":
            market_price_header = None
            market_price = get_market_price_for_listing_search(product_name=product)
            if market_price:
                market_price_header = format_market_price_header(
                    market_price["product_name"],
                    market_price.get("avg_price") or market_price.get("overall_avg"),
                    "overall",
                )

            listing_ids = [listing[0] for listing in result["listings"]]
            set_state(user_id, "viewing_listings", {
                "listing_ids": listing_ids,
                "page": 1,
                "show_seller": True,
            })

            listings_data = {
                "listings": result["listings"],
                "page": 1,
                "total_pages": 1,
                "total": len(result["listings"]),
            }

            min_p, max_p = result["price_range"]
            message_prefix = f"🔍 Showing listings near {price} XAF (±15% = {min_p}-{max_p})\n\n"
            if market_price_header:
                message_prefix = market_price_header + message_prefix

            result_data = {
                "status": "ok",
                "data": listings_data,
                "show_seller": True,
                "message_prefix": message_prefix,
            }
            return result_data

        if result["status"] == "alternatives":
            nearest_text = "\n".join([
                f"• {p['price']} XAF ({p['count']} listing{'s' if p['count'] > 1 else ''})"
                for p in result["nearest_prices"]
            ])

            return {
                "status": "ok",
                "message": (
                    f"⚠️ No listings at exactly {price} XAF for {product}\n\n"
                    f"Nearest available prices:\n{nearest_text}\n\n"
                    f"To see listings, send: 'Find {product}'"
                )
            }

    def _view_listing_image(self, entities, user_id, image_url=None, text=""):
        from db.connect import conn

        state = get_state(user_id)
        if not state or "listing_ids" not in state.get("context", {}):
            return {
                "status": "error",
                "message": "Please search for listings first.\n\nExample: 'Find corn in Douala'"
            }

        listing_ids = state["context"]["listing_ids"]
        listing_number = entities.get("listing_number")

        if not listing_number:
            return {
                "status": "error",
                "message": "Which listing photo would you like to see?\n\nExample: 'show image of listing #2'"
            }

        try:
            listing_index = int(listing_number) - 1
            if listing_index < 0 or listing_index >= len(listing_ids):
                return {
                    "status": "error",
                    "message": f"Invalid listing number. Please choose between 1 and {len(listing_ids)}."
                }
        except (ValueError, TypeError):
            return {
                "status": "error",
                "message": "Please provide a valid listing number.\n\nExample: 'show image of listing #2'"
            }

        listing_id = listing_ids[listing_index]

        cur = conn.cursor()
        cur.execute("""
            SELECT l.image_url, p.name
            FROM listings l
            JOIN products p ON l.product_id = p.id
            WHERE l.id = %s
        """, (listing_id,))
        row = cur.fetchone()
        cur.close()

        if not row:
            return {"status": "error", "message": "Listing not found."}

        image = row[0]
        if not image:
            return {
                "status": "ok",
                "message": f"No photo available for listing #{listing_number}."
            }

        product_name = row[1].capitalize()
        return {
            "status": "ok",
            "message": f"📸 #{listing_number} {product_name}",
            "preview_image": image,
        }

    def _get_my_interests(self, entities, user_id, image_url=None, text=""):
        """Show user's own interests (buyer view)."""
        from db.controller.listingInterestController import get_user_interests

        result = get_user_interests(user_id)

        if result["total"] == 0:
            return {"status": "ok", "message": result["message"]}

        lines = [f"💚 *Your Interests* ({result['total']} active)\n"]

        for idx, interest in enumerate(result["interests"], 1):
            quantity_text = f" - {interest['interested_quantity']}" if interest.get('interested_quantity') else ""
            lines.append(
                f"#{idx} 🌾 {interest['product_name'].capitalize()}{quantity_text}\n"
                f"   💰 {interest['price']} XAF\n"
                f"   👤 Farmer: {interest['seller_name']}\n"
                f"   🆔 Interest ID: {interest['interest_id']}\n"
            )

        lines.append("\n💡 To cancel an interest, send: 'cancel interest [ID]'")

        return {"status": "ok", "message": "\n".join(lines)}

    def _cancel_interest(self, entities, user_id, image_url=None, text=""):
        """Cancel an interest (buyer cancels)."""
        from db.controller.listingInterestController import cancel_interest

        interest_id = entities.get("interest_id")

        if not interest_id:
            return {
                "status": "error",
                "message": "Which interest do you want to cancel?\n\nExample: 'cancel interest 123'"
            }

        result = cancel_interest(interest_id, user_id)

        if result.get("farmer_notification") and result["farmer_notification"].get("farmer_chat_id"):
            farmer_notif = result["farmer_notification"]
            notification = {
                "chat_id": farmer_notif["farmer_chat_id"],
                "message": (
                    f"❌ Interest Cancelled\n\n"
                    f"🌾 Product: {farmer_notif['product_name'].capitalize()}\n"
                    f"👤 Buyer: {farmer_notif['buyer_name']}\n\n"
                    f"The buyer has cancelled their interest."
                ),
            }
            result["farmer_notification"] = notification

        return result

    def _reject_interest(self, entities, user_id, image_url=None, text=""):
        """Reject an interest (farmer rejects)."""
        from db.controller.listingInterestController import reject_interest
        from db.controller.userController import get_user_info

        user = get_user_info(user_id)
        if not user or not user.is_farmer():
            return {
                "status": "error",
                "message": "Only farmers can reject interests."
            }

        interest_id = entities.get("interest_id")

        if not interest_id:
            return {
                "status": "error",
                "message": "Which interest do you want to reject?\n\nExample: 'reject interest 123'"
            }

        result = reject_interest(interest_id, user_id)

        if result.get("buyer_notification") and result["buyer_notification"].get("buyer_chat_id"):
            buyer_notif = result["buyer_notification"]
            notification = {
                "chat_id": buyer_notif["buyer_chat_id"],
                "message": (
                    f"❌ Interest Declined\n\n"
                    f"🌾 Product: {buyer_notif['product_name'].capitalize()}\n"
                    f"👤 Farmer: {buyer_notif['farmer_name']}\n\n"
                    f"The farmer has declined your interest. Try contacting other sellers."
                ),
            }
            result["buyer_notification"] = notification

        return result

    def _get_crop_price(self, entities, user_id, image_url=None, text=""):
        """Show product price for specific region or all regions."""
        from db.controller.productPriceController import get_product_price
        from utils.formatter import format_crop_price_table

        product = entities.get("product")
        region = entities.get("region")

        if not product:
            return {
                "status": "error",
                "message": "Which product's price do you want to see?\n\nExample: 'What's the price of maize?'"
            }

        result = get_product_price(product, region)

        if result["status"] == "error":
            return result

        if result["status"] == "service_not_supported":
            return {"status": "ok", "message": result["message"]}

        if not result["prices"]:
            if region:
                return {
                    "status": "ok",
                    "message": (
                        f"📊 *No Price Data for {product.capitalize()} in {region}*\n\n"
                        f"Price information for this region hasn't been added yet.\n\n"
                        f"💡 Try: 'What's the price of {product}?' to see other regions"
                    )
                }
            else:
                return {
                    "status": "ok",
                    "message": (
                        f"📊 *No Price Data for {product.capitalize()}*\n\n"
                        f"Market price information for {product.capitalize()} hasn't been added yet. "
                        f"You can still search for listings!\n\n"
                        f"💡 To see listings, send: 'Find {product}'"
                    )
                }

        table = format_crop_price_table(
            result["product_name"],
            result["prices"],
            result["overall_avg"],
            region,
        )

        if region:
            tip = f"\n\n💡 To see listings in {region}, send: 'Find {product} in {region}'"
        else:
            tip = f"\n\n💡 To see listings, send: 'Find {product}'"

        return {"status": "ok", "message": table + tip}

    def _get_all_crop_prices(self, entities, user_id, image_url=None, text=""):
        """Show price overview for all products (excludes services)."""
        from db.controller.productPriceController import get_all_product_prices
        from utils.formatter import format_all_product_prices

        result = get_all_product_prices()

        if result["status"] == "error":
            return result

        formatted = format_all_product_prices(result["products"])

        return {"status": "ok", "message": formatted}

    def _handle_location_input(self, text: str, user_id: str, context: dict) -> dict:
        """Handle location input for listing after creation."""
        from db.controller.listingController import update_listing

        listing_id = context.get("listing_id")
        town = text.strip().title()

        if result["status"] == "error":
            return result

        clear_state(user_id)

        return {
            "status": "ok",
            "message": f"✅ Location updated! Your listing is now in {town}, {context['region']}"
        }

    def _unknown(self, entities, user_id, image_url=None, text=""):
        return {"status": "error", "message": "I didn't understand that. Try asking to sell, find, or delete a listing."}
