from langdetect import detect
from deep_translator import GoogleTranslator


def translate_to_english(text: str) -> tuple[str, str]:
    """
    Returns (translated_text, detected_language)
    If already English, returns original text unchanged.
    """
    try:
        lang = detect(text)
        if lang == "en":
            return text, "en"

        translated = GoogleTranslator(source="auto", target="en").translate(text)
        return translated, lang
    except Exception:
        # if detection fails, just return original
        return text, "unknown"

def translate_reply(text: str, target_lang: str) -> str:
    """
    Translates bot reply to target language.
    If target is English, returns as is.
    """
    try:
        if target_lang == "en" or target_lang == "unknown":
            return text
        return GoogleTranslator(source="en", target=target_lang).translate(text)
    except Exception:
        return text