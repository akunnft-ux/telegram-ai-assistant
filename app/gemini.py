from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY, GEMINI_MODEL

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """Kamu adalah asisten AI personal yang helpful dan ramah.
Jawab selalu dalam Bahasa Indonesia kecuali diminta bahasa lain.
Jawab dengan natural seperti teman ngobrol, tidak kaku.
Usahakan jawaban ringkas, jelas, dan tidak terlalu panjang kecuali diminta detail.
Kalau memberi daftar, batasi 3-5 poin saja.
Gunakan format teks biasa yang rapi untuk Telegram.
Hindari markdown seperti **bold**, *italic*, atau format aneh lainnya.
Kalau user meminta informasi real-time, lokasi terdekat, data terbaru, atau hasil pencarian aktual, jelaskan dengan jujur bahwa kamu tidak sedang mengakses internet, GPS, atau Google Maps secara langsung. Berikan saran umum saja."""


def build_contents_from_history(recent_messages):
    contents = []

    for role, message in recent_messages:
        gemini_role = "user" if role == "user" else "model"
        contents.append(
            types.Content(
                role=gemini_role,
                parts=[types.Part.from_text(text=message)]
            )
        )

    return contents


async def get_response(user_id: str, user_message: str, recent_messages) -> str:
    contents = build_contents_from_history(recent_messages)

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=2048,
        )
    )

    return response.text
