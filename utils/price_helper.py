def calculate_price_range(target_price: int, tolerance_percent: float = 15.0) -> tuple:
    """
    Calculate price range with percentage tolerance.

    Args:
        target_price: Target price in XAF
        tolerance_percent: Percentage tolerance (default 15%)

    Returns:
        (min_price, max_price)

    Example:
        calculate_price_range(200, 15) → (170, 230)
        calculate_price_range(100, 15) → (85, 115)
    """
    tolerance = target_price * (tolerance_percent / 100)
    min_price = int(target_price - tolerance)
    max_price = int(target_price + tolerance)
    return (min_price, max_price)


def get_price_indicator(listing_price: float, market_avg: float) -> str:
    """
    Return emoji indicator for listing price vs market average.

    Args:
        listing_price: Price of the listing
        market_avg: Market average price

    Returns:
        "💚 (Below market)" - more than 5% below average
        "📊 (Near market)" - within ±5% of average
        "🔴 (Above market)" - more than 5% above average

    Example:
        get_price_indicator(150, 180) → "💚 (Below market)"
        get_price_indicator(175, 180) → "📊 (Near market)"
        get_price_indicator(210, 180) → "🔴 (Above market)"
    """
    if not market_avg or market_avg <= 0:
        return ""

    difference_percent = ((listing_price - market_avg) / market_avg) * 100

    if difference_percent < -5:
        return "💚 (Below market)"
    elif difference_percent > 5:
        return "🔴 (Above market)"
    else:
        return "📊 (Near market)"
