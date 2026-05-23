def format_listing_item(listing: tuple) -> str:
    crop_name = listing[12].capitalize()
    quantity = listing[3]
    price = listing[4]
    town = listing[5] or "location not set"
    region = listing[6]
    expires_at = listing[9].strftime("%d %b %Y")

    return (
        f"🌾 {crop_name}\n"
        f"   📦 {quantity}kg at {price} XAF/kg\n"
        f"   📍 {town}, {region}\n"
        f"   ⏳ Expires: {expires_at}"
    )

def format_listings(result: dict) -> str:
    listings = result["listings"]
    page = result["page"]
    total_pages = result["total_pages"]
    total = result["total"]

    if not listings:
        return "No listings found."

    lines = [f"📄 Page {page}/{total_pages} — {total} listing(s) total\n"]
    lines += [f"{i+1}) {format_listing_item(l)}" for i, l in enumerate(listings)]

    if page < total_pages:
        lines.append(f"\nReply *next* to see page {page + 1}")

    return "\n\n".join(lines)

def get_listing_images(result: dict) -> list:
    return [
        (l[8], format_listing_item(l))
        for l in result["listings"] if l[8]
    ]