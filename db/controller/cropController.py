from db.connect import conn
from rapidfuzz import process, fuzz
from entities.vocabulary import CROP_SYNONYMS

def get_crop_id(crop_name: str) -> int | None:
    # resolve synonym first
    crop_name = CROP_SYNONYMS.get(crop_name.lower(), crop_name)

    cur = conn.cursor()
    cur.execute("SELECT id, name FROM crops")
    crops = cur.fetchall()
    cur.close()

    names = [row[1] for row in crops]
    match = process.extractOne(crop_name, names, scorer=fuzz.ratio)

    if match and match[1] >= 70:
        matched_name = match[0]
        for row in crops:
            if row[1] == matched_name:
                return row[0]

    return None