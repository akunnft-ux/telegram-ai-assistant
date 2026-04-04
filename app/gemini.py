from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.memory import format_memories_for_prompt
from app.tools import get_tvl_growth, format_tvl_result

client = genai.Client(api_key=GEMINI_API_KEY)

BASE_SYSTEM_PROMPT = """Kamu adalah asisten AI personal yang helpful dan ramah.
Jawab selalu dalam Bahasa Indonesia kecuali diminta bahasa lain.
Jawab dengan natural seperti teman ngobrol, tidak kaku.
Usahakan jawaban ringkas, jelas, dan tidak terlalu panjang kecuali diminta detail.
Kalau memberi daftar, batasi 3-5 poin saja.
Gunakan format teks biasa yang rapi untuk Telegram.
Hindari markdown seperti **bold**, *italic*, atau format aneh lainnya.
Kalau user meminta informasi real-time, lokasi terdekat, data terbaru, atau hasil pencarian aktual, jelaskan dengan jujur bahwa kamu tidak sedang mengakses internet, GPS, atau Google Maps secara langsung. Berikan saran umum saja.
Kamu punya akses ke data DeFi dari DefiLlama. Gunakan tool yang tersedia kalau user tanya soal TVL protokol."""

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
[/MEMORY]"""

# Definisi tool untuk Gemini
TVL_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="get_tvl_growth",
            description="Ambil data TVL dan growth 30 hari dari DefiLlama untuk protokol DeFi tertentu.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "protocol_name": types.Schema(
                        type=types.Type.STRING,
                        description="Nama protokol DeFi, contoh: aave, uniswap, lido"
                    )
                },
                required=["protocol_name"]
            )
        )
    ]
)


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

        # Call 1: Gemini putuskan pakai tool atau tidak
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=1500,
                tools=[TVL_TOOL]
            )
        )

        # Cek apakah Gemini mau panggil tool
        candidate = response.candidates[0]
        part = candidate.content.parts[0]

        if hasattr(part, "function_call") and part.function_call:
            function_call = part.function_call
            protocol_name = function_call.args.get("protocol_name", "")

            print(f"🔧 Tool dipanggil: get_tvl_growth({protocol_name})")

            # Eksekusi tool
            tool_result = await get_tvl_growth(protocol_name)
            formatted_result = format_tvl_result(tool_result)

            # Call 2: Gemini rangkum hasil tool
            contents.append({
                "role": "model",
                "parts": [{"function_call": {"name": "get_tvl_growth", "args": {"protocol_name": protocol_name}}}]
            })
            contents.append({
                "role": "user",
                "parts": [{"function_response": {"name": "get_tvl_growth", "response": {"result": formatted_result}}}]
            })

            response2 = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                    max_output_tokens=1500,
                )
            )

            return response2.text if response2.text else formatted_result

        # Tidak pakai tool, return response biasa
        if not response.text:
            print("⚠️ Gemini response kosong")
            return "Maaf, aku tidak bisa memproses pesanmu. Coba kirim ulang ya."

        return response.text

    except Exception as e:
        error_msg = str(e).lower()
        print(f"❌ Gemini error: {e}")

        if "quota" in error_msg or "429" in error_msg or "resource" in error_msg:
            return "Maaf, quota API aku lagi habis. Coba lagi dalam beberapa menit ya."
        if "timeout" in error_msg or "deadline" in error_msg:
            return "Maaf, server lagi lambat. Coba lagi sebentar ya."
        if "api key" in error_msg or "401" in error_msg or "403" in error_msg:
            return "Maaf, ada masalah autentikasi. Hubungi admin."
        if "model" in error_msg or "not found" in error_msg or "404" in error_msg:
            return "Maaf, model AI sedang tidak tersedia. Coba lagi nanti."

        return "Maaf, aku lagi ada gangguan. Coba lagi nanti ya."
