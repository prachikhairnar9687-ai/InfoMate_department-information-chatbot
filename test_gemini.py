
import os
from dotenv import load_dotenv
from google import genai

load_dotenv(override=True)

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY is missing from .env")

print("API key loaded:", True)
print("Key length:", len(api_key))

try:
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents="Reply with exactly: Gemini works"
    )

    print("Response text:", repr(response.text))

except Exception:
    import traceback
    traceback.print_exc()
