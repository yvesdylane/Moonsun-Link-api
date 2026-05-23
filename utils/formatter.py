def format_listing_item(listing: tuple, show_seller: bool = False) -> str:
    crop_name = listing[12].capitalize()
    quantity = listing[3]
    price = listing[4]
    town = listing[5] or "Not specified"
    region = listing[6]
    origin = listing[7]
    image_url = listing[8]
    expires_at = listing[9].strftime("%d %b %Y")

    # index 13 = seller_name (only present when show_seller=True)
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
        return "No listings found."

    lines = [f"📄 Page {page}/{total_pages} — {total} listing(s)\n"]
    lines += [f"{i+1}) {format_listing_item(l, show_seller=show_seller)}" for i, l in enumerate(listings)]

    if page < total_pages:
        lines.append(f"\nReply *next* to see page {page + 1}")

    return "\n\n".join(lines)

def get_listing_images(result: dict, show_seller: bool = False) -> list:
    return [
        (l[8], format_listing_item(l, show_seller=show_seller))
        for l in result["listings"] if l[8]
    ]