import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def transcribe_audio(file_path: str) -> str:
    """
    Transcribe audio using Groq's Whisper API.
    Supports multiple languages, defaults to auto-detect.
    """
    try:
        with open(file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3-turbo",
                response_format="verbose_json",  # includes language detection
                temperature=0.0
            )

        detected_lang = transcription.language if hasattr(transcription, 'language') else 'unknown'
        print(f"GROQ WHISPER DETECTED LANGUAGE: {detected_lang}")

        return transcription.text.strip()

    except Exception as e:
        print(f"GROQ WHISPER ERROR: {e}")
        raise