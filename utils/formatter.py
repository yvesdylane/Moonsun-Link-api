def format_listing_item(listing: tuple, show_seller: bool = False, listing_number: int = None, market_avg: float = None) -> str:
    # Column indices: id=0, user_id=1, product_id=2, quantity=3, measurement=4,
    #                   price=5, town=6, region=7, origin=8, image_url=9,
    #                   expires_at=10, created_at=11, updated_at=12
    #                   product_name=13, seller_name=14 (if joined)
    product_name = listing[13].capitalize()
    quantity = listing[3]
    measurement = listing[4] or "kg"
    price = listing[5]
    town = listing[6]
    region = listing[7]
    origin = listing[8]
    image_url = listing[9]
    expires_at = listing[10].strftime("%d %b %Y")

    if listing_number:
        lines = [f"#{listing_number} 🌾 {product_name} from {origin}"]
    else:
        lines = [f"🌾 {product_name} from {origin}"]

    if show_seller and len(listing) > 13:
        seller = listing[14]
        lines.append(f"👤 Sold by {seller}")

    price_line = f"📦 {quantity}{measurement} available at {price} XAF/{measurement}"
    if market_avg:
        from utils.price_helper import get_price_indicator
        indicator = get_price_indicator(price, market_avg)
        if indicator:
            price_line += f" {indicator}"
    lines.append(price_line)

    if town:
        if region == "General":
            location = f"📍 {town} (Available nationwide)"
        else:
            location = f"📍 {town}, {region}"
    else:
        if region == "General":
            location = f"📍 Available nationwide (General)"
        else:
            location = f"📍 Not specified, {region}"
    lines.append(location)

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
        lines.append(f"\n💡 To show interest, send: 'I'm interested in [quantity] of listing #[number]'")

    has_images = any(l[9] for l in listings)
    if has_images:
        lines.append(f"\n📸 To see photos, send: 'show image of listing #[number]'")

    return "\n\n".join(lines)


def get_listing_images(result: dict, show_seller: bool = False) -> list:
    return [
        (l[9], format_listing_item(l, show_seller=show_seller, listing_number=i+1))
        for i, l in enumerate(result["listings"]) if l[9]
    ]


def format_crop_price_table(product_name: str, prices: list, overall_avg: float = None, region: str = None) -> str:
    if not prices:
        return f"📊 No price data available for {product_name.capitalize()}."

    if region:
        price = prices[0]
        lines = [
            f"📊 *{product_name.capitalize()} Price in {region}*\n",
            f"Regional Average: {price['avg']} XAF\n",
            f"Min: {price['min']} XAF",
            f"Max: {price['max']} XAF",
            f"Avg: {price['avg']} XAF",
        ]
        return "\n".join(lines)

    lines = [f"📊 *{product_name.capitalize()} Market Prices*\n"]

    if overall_avg:
        lines.append(f"Overall Average: {overall_avg} XAF\n")

    lines.append("Region          | Min    | Max    | Avg")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    cheapest = min(prices, key=lambda x: x['avg'])
    most_expensive = max(prices, key=lambda x: x['avg'])

    all_regions = [
        'Adamaoua', 'Centre', 'Est', 'Extreme-Nord',
        'Littoral', 'Nord', 'Nord-Ouest', 'Ouest', 'Sud', 'Sud-Ouest',
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


def format_all_product_prices(products: list) -> str:
    if not products:
        return (
            "📊 *No Market Price Data Available*\n\n"
            "Price information has not been added yet. "
            "Please check back later or contact support for assistance."
        )

    lines = ["📊 *Market Prices Overview*\n"]

    for product in products:
        product_name = product['product_name'].capitalize()

        lines.append(f"{product_name}")
        lines.append(f"  Overall Avg: {product['overall_avg']} XAF")
        lines.append(f"  Range: {product['min_across_regions']}-{product['max_across_regions']} XAF")
        lines.append(f"  💚 Cheapest: {product['cheapest_region']} ({product['cheapest_avg']})")
        lines.append(f"  🔴 Most expensive: {product['most_expensive_region']} ({product['most_expensive_avg']})\n")

    return "\n".join(lines)


def format_market_price_header(product_name: str, avg_price: float, scope: str, region: str = None) -> str:
    if scope == "regional" and region:
        return f"📊 {region} Average: {avg_price} XAF\n"
    else:
        return f"📊 Market Average: {avg_price} XAF\n"
