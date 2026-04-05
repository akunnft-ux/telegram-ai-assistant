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
Kamu punya akses ke data DeFi dari DefiLlama. Gunakan tool yang tersedia kalau user tanya soal TVL protokol.
Kamu juga bisa membaca dokumen yang dikirim user (PDF, DOCX, TXT, CSV, XLSX, JSON, dan file teks lainnya). Kalau user kirim dokumen, baca isinya dan bantu sesuai permintaan user. Kalau tidak ada instruksi spesifik, rangkum isi dokumen tersebut."""

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


async def get_response(user_id, user_message, recent_messages):
    try:
        system_prompt = build_system_prompt(user_id)

        # Bangun contents pakai types.Content
        contents = []
        for role, message in recent_messages:
            gemini_role = "user" if role == "user" else "model"
            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[types.Part(text=message)]
                )
            )

        # Call 1: Gemini putuskan pakai tool atau tidak
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=1500,
                tools=[TVL_TOOL],
            )
        )

        candidate = response.candidates[0]

        # Cari function_call di semua parts
        function_call_part = None
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                function_call_part = part
                break

        if function_call_part:
            function_call = function_call_part.function_call
            protocol_name = function_call.args.get("protocol_name", "")

            print(f"🔧 Tool dipanggil: get_tvl_growth({protocol_name})")

            # Eksekusi tool
            tool_result = await get_tvl_growth(protocol_name)
            formatted_result = format_tvl_result(tool_result)

            # ✅ Pakai candidate.content ASLI (bawa thought_signature)
            contents.append(candidate.content)

            # ✅ Bangun function response dengan thought_signature dari part asli
            function_response_parts = []
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fr_part = types.Part(
                        function_response=types.FunctionResponse(
                            name=part.function_call.name,
                            response={"result": formatted_result}
                        ),
                    )
                    # Salin thought_signature jika ada
                    if hasattr(part, "thought_signature") and part.thought_signature:
                        fr_part.thought_signature = part.thought_signature
                    function_response_parts.append(fr_part)

            if function_response_parts:
                contents.append(
                    types.Content(
                        role="user",
                        parts=function_response_parts
                    )
                )

            # Call 2: Gemini rangkum hasil tool
            response2 = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                    max_output_tokens=1500,
                    tools=[TVL_TOOL],
                )
            )

            return response2.text if response2.text else formatted_result

        # Tidak pakai tool
        if not response.text:
            print("⚠️ Gemini response kosong")
            return "Maaf, aku tidak bisa memproses pesanmu. Coba kirim ulang ya."

        return response.text

    except Exception as e:
        error_msg = str(e).lower()
        print(f"❌ Gemini error: {e}")

        if "thought_signature" in error_msg:
            # Fallback: kalau masih error thought_signature, langsung return hasil tool
            print("⚠️ Thought signature error, using direct tool result")
            try:
                # Coba return formatted_result yang sudah ada
                return formatted_result
            except:
                pass

        if "quota" in error_msg or "429" in error_msg or "resource" in error_msg:
            return "Maaf, quota API aku lagi habis. Coba lagi dalam beberapa menit ya."
        if "timeout" in error_msg or "deadline" in error_msg:
            return "Maaf, server lagi lambat. Coba lagi sebentar ya."
        if "api key" in error_msg or "401" in error_msg or "403" in error_msg:
            return "Maaf, ada masalah autentikasi. Hubungi admin."
        if "model" in error_msg or "not found" in error_msg or "404" in error_msg:
            return "Maaf, model AI sedang tidak tersedia. Coba lagi nanti."

        return "Maaf, aku lagi ada gangguan. Coba lagi nanti ya."


async def summarize_chunk(chunk_text, chunk_number, total_chunks, file_name):
    """Rangkum 1 chunk dokumen — 1 API call"""
    try:
        prompt = f"""Kamu sedang membaca bagian {chunk_number} dari {total_chunks} bagian dokumen "{file_name}".

Tugas: Rangkum bagian ini dengan detail yang cukup. Pertahankan informasi penting, angka, nama, dan poin-poin utama. Jangan hilangkan data penting.

Isi dokumen bagian {chunk_number}:
{chunk_text}

Rangkum dalam Bahasa Indonesia:"""

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            config={
                "system_instruction": "Kamu adalah asisten yang merangkum dokumen. Rangkum dengan detail, pertahankan semua informasi penting.",
                "temperature": 0.3,
                "max_output_tokens": 2000,
            }
        )

        if response.text:
            return response.text
        return f"[Gagal merangkum bagian {chunk_number}]"

    except Exception as e:
        print(f"❌ Error summarize chunk {chunk_number}: {e}")
        return f"[Error merangkum bagian {chunk_number}: {e}]"


async def process_long_document(user_id, chunks, file_name, user_caption, recent_messages):
    """Proses dokumen panjang: rangkum per chunk, lalu jawab final"""
    try:
        print(f"📄 Processing {len(chunks)} chunks for {file_name}")

        # Step 1: Rangkum setiap chunk
        summaries = []
        for i, chunk in enumerate(chunks, 1):
            print(f"  📝 Summarizing chunk {i}/{len(chunks)}...")
            summary = await summarize_chunk(chunk, i, len(chunks), file_name)
            summaries.append(f"[Bagian {i}]\n{summary}")

        combined_summary = "\n\n".join(summaries)

        # Step 2: Bangun final prompt
        if user_caption:
            final_prompt = f"""Berikut adalah rangkuman dari dokumen "{file_name}" yang dikirim user:

{combined_summary}

Perintah user: {user_caption}

Jawab sesuai permintaan user berdasarkan isi dokumen di atas."""
        else:
            final_prompt = f"""Berikut adalah rangkuman dari dokumen "{file_name}" yang dikirim user:

{combined_summary}

Tolong berikan rangkuman lengkap dan poin-poin penting dari dokumen ini."""

        # Step 3: Simpan final_prompt ke DB agar masuk recent_messages
        from app.database import save_message, get_recent_messages
        save_message(user_id, "user", final_prompt)

        # Step 4: Ambil recent_messages BARU (sudah termasuk final_prompt)
        fresh_messages = get_recent_messages(user_id, limit=20)

        # Step 5: Kirim ke Gemini — sekarang Gemini bisa baca summary-nya
        raw_response = await get_response(user_id, final_prompt, fresh_messages)

        print(f"  ✅ Document processing done. Total API calls: {len(chunks) + 1}")
        return raw_response

    except Exception as e:
        print(f"❌ Error process_long_document: {e}")
        return "Maaf, gagal memproses dokumen panjang ini. Coba kirim ulang ya."


async def generate_document_content(user_id, instruction, recent_messages):
    """Generate konten terstruktur untuk dokumen PDF/DOCX"""
    try:
        # Bangun konteks dari percakapan terakhir
        context_lines = []
        for role, message in recent_messages[-10:]:
            speaker = "User" if role == "user" else "Asisten"
            msg = message[:500] + "..." if len(message) > 500 else message
            context_lines.append(f"{speaker}: {msg}")

        context = "\n".join(context_lines) if context_lines else "Tidak ada percakapan sebelumnya."

        prompt = f"""Konteks percakapan terakhir:
{context}

Instruksi user: {instruction}

Buatkan konten dokumen berdasarkan instruksi di atas.

Format yang WAJIB diikuti:
- Baris pertama HARUS judul dokumen, diawali # (contoh: # Judul Dokumen)
- Sub-bagian diawali ## (contoh: ## Pendahuluan)
- Sub-sub-bagian diawali ### (contoh: ### Detail)
- Poin-poin diawali - (contoh: - Poin pertama)
- Paragraf biasa tanpa awalan apapun
- JANGAN pakai **bold**, *italic*, atau format markdown lain selain # ## ### dan -
- Tulis dalam Bahasa Indonesia
- Tulis lengkap, detail, dan informatif
- Minimal 500 kata"""

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            config={
                "system_instruction": "Kamu adalah penulis dokumen profesional. Tulis konten yang terstruktur, lengkap, informatif, dan rapi. Ikuti format yang diminta dengan tepat.",
                "temperature": 0.7,
                "max_output_tokens": 4000,
            }
        )

        if response.text:
            return response.text
        return None

    except Exception as e:
        print(f"❌ Error generate document content: {e}")
        return None

async def analyze_image(user_id, image_bytes, caption, recent_messages, mime_type="image/jpeg"):
    """Analisis gambar yang dikirim user — 1 API call"""
    try:
        system_prompt = build_system_prompt(user_id)

        if caption:
            text_prompt = caption
        else:
            text_prompt = "Analisis gambar ini. Jelaskan apa yang kamu lihat secara detail."

        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=mime_type
        )

        text_part = types.Part(text=text_prompt)

        contents = [
            types.Content(
                role="user",
                parts=[image_part, text_part]
            )
        ]

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=1500,
            )
        )

        if response.text:
            return response.text

        return "Maaf, aku tidak bisa menganalisis gambar ini. Coba kirim ulang ya."

    except Exception as e:
        error_msg = str(e).lower()
        print(f"❌ Error analyze image: {e}")

        if "quota" in error_msg or "429" in error_msg:
            return "Maaf, quota API lagi habis. Coba lagi nanti ya."

        if "not supported" in error_msg or "invalid" in error_msg:
            return "Maaf, model ini belum bisa analisis gambar. Coba kirim ulang nanti ya."

        return "Maaf, gagal menganalisis gambar. Coba kirim ulang ya."
