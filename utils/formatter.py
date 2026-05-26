def format_listing_item(listing: tuple, show_seller: bool = False, listing_number: int = None) -> str:
    crop_name = listing[12].capitalize()
    quantity = listing[3]
    price = listing[4]
    town = listing[5] or "Not specified"
    region = listing[6]
    origin = listing[7]
    image_url = listing[8]
    expires_at = listing[9].strftime("%d %b %Y")

    # index 13 = seller_name (only present when show_seller=True)
    if listing_number:
        lines = [f"#{listing_number} 🌾 {crop_name} from {origin}"]
    else:
        lines = [f"🌾 {crop_name} from {origin}"]

    if show_seller and len(listing) > 13:
        seller = listing[13]
        lines.append(f"👤 Sold by {seller}")

    lines.append(f"📦 {quantity}kg available at {price} XAF/kg")
    lines.append(f"📍 {town}, {region}")
    lines.append(f"⏳ Expires: {expires_at}")

    return "\n".join(lines)

def format_listings(result: dict, show_seller: bool = False) -> str:
    listings = result["listings"]
    page = result["page"]
    total_pages = result["total_pages"]
    total = result["total"]

    if not listings:
        if show_seller:
            return (
                "😕 No listings found for that search.\n\n"
                "Try a different product or location, or check back later!"
            )
        else:
            return (
                "📭 You don't have any listings yet.\n\n"
                "Send me a message like:\n"
                "'I want to sell 50kg of corn at 200 XAF'"
            )

    lines = [f"📄 Page {page}/{total_pages} — {total} listing(s)\n"]
    lines += [format_listing_item(l, show_seller=show_seller, listing_number=i+1) for i, l in enumerate(listings)]

    if page < total_pages:
        lines.append(f"\nReply *next* to see page {page + 1}")

    if show_seller and listings:
        lines.append(f"\n💡 To show interest, send: 'I'm interested in [quantity]kg of listing #[number]'")

    return "\n\n".join(lines)

def get_listing_images(result: dict, show_seller: bool = False) -> list:
    return [
        (l[8], format_listing_item(l, show_seller=show_seller, listing_number=i+1))
        for i, l in enumerate(result["listings"]) if l[8]
    ]