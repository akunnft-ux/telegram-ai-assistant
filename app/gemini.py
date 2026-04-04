from google import genai
from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.memory import format_memories_for_prompt

client = genai.Client(api_key=GEMINI_API_KEY)

BASE_SYSTEM_PROMPT = """Kamu adalah asisten AI personal yang helpful dan ramah.
Jawab selalu dalam Bahasa Indonesia kecuali diminta bahasa lain.
Jawab dengan natural seperti teman ngobrol, tidak kaku.
Usahakan jawaban ringkas, jelas, dan tidak terlalu panjang kecuali diminta detail.
Kalau memberi daftar, batasi 3-5 poin saja.
Gunakan format teks biasa yang rapi untuk Telegram.
Hindari markdown seperti **bold**, *italic*, atau format aneh lainnya.
Kalau user meminta informasi real-time, lokasi terdekat, data terbaru, atau hasil pencarian aktual, jelaskan dengan jujur bahwa kamu tidak sedang mengakses internet, GPS, atau Google Maps secara langsung. Berikan saran umum saja."""

MEMORY_EXTRACTION_PROMPT = """
Kamu juga punya tugas tambahan: ekstrak informasi personal dari pesan user.

Kategori utama yang bisa kamu simpan:
- nama_user, kota_tinggal, pekerjaan, hobi, status, makanan_favorit, musik_favorit, bahasa_preferensi, gaya_komunikasi

Tapi kamu juga BOLEH membuat kategori baru yang relevan jika menemukan info penting.
Gunakan format key snake_case.

Aturan:
- Hanya ekstrak kalau user BENAR-BENAR menyebutkan info tentang dirinya
- Jangan mengarang atau mengasumsikan
- Jangan ekstrak dari pertanyaan user (misal "kamu suka apa?" bukan info tentang user)
- Kalau tidak ada info baru, JANGAN tulis block [MEMORY]

Kalau ada info baru, tambahkan di AKHIR jawabanmu dengan format:
[MEMORY]
key: value
[/MEMORY]

Contoh:
User: "Aku tinggal di Bandung dan kerja sebagai desainer"
Jawaban: "Oh keren, Bandung emang enak buat kerja kreatif!"
[MEMORY]
kota_tinggal: Bandung
pekerjaan: desainer
[/MEMORY]"""


def build_system_prompt(user_id):
    memory_context = format_memories_for_prompt(user_id)

    parts = [BASE_SYSTEM_PROMPT]

    if memory_context:
        parts.append(memory_context)

    parts.append(MEMORY_EXTRACTION_PROMPT)

    return "\n\n".join(parts)


def build_contents_from_history(recent_messages):
    contents = []
    for role, message in recent_messages:
        gemini_role = "user" if role == "user" else "model"
        contents.append({
            "role": gemini_role,
            "parts": [{"text": message}]
        })
    return contents


async def get_response(user_id, user_message, recent_messages):
    try:
        system_prompt = build_system_prompt(user_id)

        contents = build_contents_from_history(recent_messages)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config={
                "system_instruction": system_prompt,
                "temperature": 0.7,
                "max_output_tokens": 2048,
            }
        )

        return response.text

    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return "Maaf, aku lagi ada gangguan. Coba lagi nanti ya."
