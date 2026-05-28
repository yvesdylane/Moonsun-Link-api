def format_listing_item(listing: tuple, show_seller: bool = False, listing_number: int = None, market_avg: float = None) -> str:
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

    # Add price with indicator if market average provided
    price_line = f"📦 {quantity}kg available at {price} XAF/kg"
    if market_avg:
        from utils.price_helper import get_price_indicator
        indicator = get_price_indicator(price, market_avg)
        if indicator:
            price_line += f" {indicator}"
    lines.append(price_line)

    lines.append(f"📍 {town}, {region}")
    lines.append(f"⏳ Expires: {expires_at}")

    return "\n".join(lines)

def format_listings(result: dict, show_seller: bool = False, market_avg: float = None) -> str:
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
    lines += [format_listing_item(l, show_seller=show_seller, listing_number=i+1, market_avg=market_avg) for i, l in enumerate(listings)]

    if page < total_pages:
        lines.append(f"\nReply *next* to see page {page + 1}")

    if show_seller and listings:
        lines.append(f"\n💡 To show interest, send: 'I'm interested in [quantity]kg of listing #[number]'")

    # Check if any listing has an image
    has_images = any(l[8] for l in listings)
    if has_images:
        lines.append(f"\n📸 To see photos, send: 'show image of listing #[number]'")

    return "\n\n".join(lines)

def get_listing_images(result: dict, show_seller: bool = False) -> list:
    return [
        (l[8], format_listing_item(l, show_seller=show_seller, listing_number=i+1))
        for i, l in enumerate(result["listings"]) if l[8]
    ]


def format_crop_price_table(crop_name: str, prices: list, overall_avg: float = None, region: str = None) -> str:
    """
    Format crop price data as table with emojis.
    Highlights cheapest (💚) and most expensive (🔴) regions.

    Args:
        crop_name: Name of the crop
        prices: List of price dicts with region, min, max, avg
        overall_avg: Overall average across regions
        region: If specified, this is a single-region query

    Returns:
        Formatted string with price table
    """
    if not prices:
        return f"📊 No price data available for {crop_name.capitalize()}."

    # Single region view
    if region:
        price = prices[0]
        lines = [
            f"📊 *{crop_name.capitalize()} Price in {region}*\n",
            f"Regional Average: {price['avg']} XAF/kg\n",
            f"Min: {price['min']} XAF/kg",
            f"Max: {price['max']} XAF/kg",
            f"Avg: {price['avg']} XAF/kg"
        ]
        return "\n".join(lines)

    # Multi-region view
    lines = [f"📊 *{crop_name.capitalize()} Market Prices*\n"]

    if overall_avg:
        lines.append(f"Overall Average: {overall_avg} XAF/kg\n")

    # Table header
    lines.append("Region          | Min    | Max    | Avg")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Find cheapest and most expensive
    cheapest = min(prices, key=lambda x: x['avg'])
    most_expensive = max(prices, key=lambda x: x['avg'])

    # All regions (fill missing with ---)
    all_regions = [
        'Adamaoua', 'Centre', 'Est', 'Extreme-Nord',
        'Littoral', 'Nord', 'Nord-Ouest', 'Ouest', 'Sud', 'Sud-Ouest'
    ]

    price_map = {p['region']: p for p in prices}

    for region_name in all_regions:
        if region_name in price_map:
            p = price_map[region_name]
            emoji = ""
            if p['avg'] == cheapest['avg']:
                emoji = "💚 "
            elif p['avg'] == most_expensive['avg']:
                emoji = "🔴 "

            lines.append(f"{emoji}{region_name:<15} | {p['min']:<6} | {p['max']:<6} | {p['avg']}")
        else:
            lines.append(f"{region_name:<15} | ---    | ---    | ---")

    return "\n".join(lines)


def format_all_crop_prices(crops: list) -> str:
    """
    Format overview of all crop prices.
    Compact format showing key stats per crop.
    Only shows crops WITH data.

    Args:
        crops: List of crop dicts with price info

    Returns:
        Formatted string with all crop prices
    """
    if not crops:
        return (
            "📊 *No Market Price Data Available*\n\n"
            "Price information has not been added yet. "
            "Please check back later or contact support for assistance."
        )

    lines = ["📊 *Market Prices Overview*\n"]

    for crop in crops:
        crop_name = crop['crop_name'].capitalize()

        lines.append(f"{crop_name}")
        lines.append(f"  Overall Avg: {crop['overall_avg']} XAF/kg")
        lines.append(f"  Range: {crop['min_across_regions']}-{crop['max_across_regions']} XAF/kg")
        lines.append(f"  💚 Cheapest: {crop['cheapest_region']} ({crop['cheapest_avg']})")
        lines.append(f"  🔴 Most expensive: {crop['most_expensive_region']} ({crop['most_expensive_avg']})\n")

    return "\n".join(lines)


def format_market_price_header(crop_name: str, avg_price: float, scope: str, region: str = None) -> str:
    """
    Format market price header for listing searches.

    Args:
        crop_name: Name of the crop
        avg_price: Average price
        scope: "overall" or "regional"
        region: Region name (only if scope is regional)

    Returns:
        Formatted header string
    """
    if scope == "regional" and region:
        return f"📊 {region} Average: {avg_price} XAF/kg\n"
    else:
        return f"📊 Market Average: {avg_price} XAF/kg\n"