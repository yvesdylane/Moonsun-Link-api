from db.connect import conn
from db.controller.cropController import get_crop_id


def get_crop_price(crop_name: str, region: str = None) -> dict:
    """
    Get price data for a crop in specific region or all regions.

    Args:
        crop_name: Name of the crop (e.g., "maize", "cassava")
        region: Optional specific region (e.g., "Centre", "Littoral")

    Returns:
        {
            "status": "ok",
            "crop_name": "maize",
            "overall_avg": 180,  # None if no data
            "prices": [
                {
                    "region": "Adamaoua",
                    "min": 120,
                    "max": 180,
                    "avg": 150
                },
                ...
            ]
        }
    """
    crop_id = get_crop_id(crop_name)
    if not crop_id:
        return {
            "status": "error",
            "message": f"Crop '{crop_name}' not found."
        }

    cur = conn.cursor()

    if region:
        # Get price for specific region
        cur.execute("""
            SELECT region, min_price, max_price, avg_price
            FROM crop_prices
            WHERE crop_id = %s AND region = %s
        """, (crop_id, region))

        result = cur.fetchone()
        cur.close()

        if not result:
            return {
                "status": "ok",
                "crop_name": crop_name,
                "region": region,
                "overall_avg": None,
                "prices": []
            }

        return {
            "status": "ok",
            "crop_name": crop_name,
            "region": region,
            "overall_avg": result[3],  # Regional avg is the overall for single region
            "prices": [{
                "region": result[0],
                "min": result[1],
                "max": result[2],
                "avg": result[3]
            }]
        }
    else:
        # Get prices for all regions
        cur.execute("""
            SELECT region, min_price, max_price, avg_price
            FROM crop_prices
            WHERE crop_id = %s
            ORDER BY avg_price ASC
        """, (crop_id,))

        results = cur.fetchall()
        cur.close()

        if not results:
            return {
                "status": "ok",
                "crop_name": crop_name,
                "overall_avg": None,
                "prices": []
            }

        # Calculate overall average from regional averages
        regional_avgs = [row[3] for row in results]
        overall_avg = sum(regional_avgs) / len(regional_avgs)

        prices = [{
            "region": row[0],
            "min": row[1],
            "max": row[2],
            "avg": row[3]
        } for row in results]

        return {
            "status": "ok",
            "crop_name": crop_name,
            "overall_avg": round(overall_avg),
            "prices": prices
        }


def get_all_crop_prices() -> dict:
    """
    Get price overview for all crops.

    Returns:
        {
            "status": "ok",
            "crops": [
                {
                    "crop_name": "maize",
                    "overall_avg": 180,
                    "min_across_regions": 120,
                    "max_across_regions": 250,
                    "cheapest_region": "Adamaoua",
                    "cheapest_avg": 150,
                    "most_expensive_region": "Littoral",
                    "most_expensive_avg": 215,
                    "has_data": True
                },
                ...
            ]
        }
    """
    cur = conn.cursor()

    # Get all crops
    cur.execute("SELECT id, name FROM crops ORDER BY name")
    crops = cur.fetchall()

    result_crops = []

    for crop_id, crop_name in crops:
        # Get price data for this crop
        cur.execute("""
            SELECT region, min_price, max_price, avg_price
            FROM crop_prices
            WHERE crop_id = %s
            ORDER BY avg_price ASC
        """, (crop_id,))

        prices = cur.fetchall()

        # Skip crops with no price data (only show crops WITH data)
        if not prices:
            continue

        # Calculate stats
        regional_avgs = [p[3] for p in prices]
        overall_avg = sum(regional_avgs) / len(regional_avgs)

        all_mins = [p[1] for p in prices]
        all_maxs = [p[2] for p in prices]

        # Cheapest and most expensive by average price
        cheapest = prices[0]  # Already sorted ASC
        most_expensive = prices[-1]

        result_crops.append({
            "crop_name": crop_name,
            "has_data": True,
            "overall_avg": round(overall_avg),
            "min_across_regions": min(all_mins),
            "max_across_regions": max(all_maxs),
            "cheapest_region": cheapest[0],
            "cheapest_avg": cheapest[3],
            "most_expensive_region": most_expensive[0],
            "most_expensive_avg": most_expensive[3]
        })

    cur.close()

    return {
        "status": "ok",
        "crops": result_crops
    }


def get_market_price_for_listing_search(crop_name: str = None, region: str = None) -> dict:
    """
    Get market price context for listing searches.
    Used at top of search results.

    Args:
        crop_name: Optional crop name
        region: Optional region name

    Returns:
        {
            "has_data": True,
            "avg_price": 180,
            "scope": "overall" | "regional",
            "crop_name": "maize",
            "region": "Centre"  # Only if scope is regional
        }
    """
    if not crop_name:
        return {"has_data": False}

    crop_id = get_crop_id(crop_name)
    if not crop_id:
        return {"has_data": False}

    cur = conn.cursor()

    if region:
        # Get regional average
        cur.execute("""
            SELECT avg_price
            FROM crop_prices
            WHERE crop_id = %s AND region = %s
        """, (crop_id, region))

        result = cur.fetchone()
        cur.close()

        if not result:
            return {"has_data": False}

        return {
            "has_data": True,
            "avg_price": result[0],
            "scope": "regional",
            "crop_name": crop_name,
            "region": region
        }
    else:
        # Get overall average
        cur.execute("""
            SELECT AVG(avg_price)
            FROM crop_prices
            WHERE crop_id = %s
        """, (crop_id,))

        result = cur.fetchone()
        cur.close()

        if not result or result[0] is None:
            return {"has_data": False}

        return {
            "has_data": True,
            "avg_price": round(result[0]),
            "scope": "overall",
            "crop_name": crop_name
        }


def calculate_overall_avg(crop_id: int) -> float:
    """
    Calculate overall average from all regional averages (exclude None).

    Args:
        crop_id: ID of the crop

    Returns:
        Average price across regions, or None if no data
    """
    cur = conn.cursor()

    cur.execute("""
        SELECT AVG(avg_price)
        FROM crop_prices
        WHERE crop_id = %s
    """, (crop_id,))

    result = cur.fetchone()
    cur.close()

    if result and result[0]:
        return round(result[0])
    return None
