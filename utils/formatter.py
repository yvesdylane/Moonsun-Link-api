def format_listing_item(listing: tuple) -> str:
    quantity = listing[3]
    price = listing[4]
    town = listing[5] or "location not set"
    region = listing[6]
    expires_at = listing[9].strftime("%d %b %Y")

    return (
        f"{quantity}kg at {price} XAF/kg\n"
        f"📍 {town}, {region}\n"
        f"⏳ Expires: {expires_at}"
    )

def format_listings(listings: list) -> str:
    if not listings:
        return "No listings found."
    lines = [f"{i+1}) {format_listing_item(l)}" for i, l in enumerate(listings)]
    return "\n\n".join(lines)

def get_listing_images(listings: list) -> list:
    """Returns list of (image_url, caption) pairs for listings with images."""
    return [
        (l[8], format_listing_item(l))
        for l in listings if l[8]
    ]