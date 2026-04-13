import re
import asyncio
from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.memory import format_memories_for_prompt
from app.tools import get_tvl_growth, format_tvl_result
from app.tools import web_search, format_search_results

client = genai.Client(api_key=GEMINI_API_KEY)

BASE_SYSTEM_PROMPT = """Kamu adalah asisten AI personal yang helpful dan ramah.
Jawab selalu dalam Bahasa Indonesia kecuali diminta bahasa lain.
Jawab dengan natural seperti teman ngobrol, tidak kaku.
Tidak usah terlalu sering panggil nama user, yang natural saja.
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

SEARCH_INSTRUCTION = """

## Kemampuan Web Search
Kamu memiliki kemampuan mencari informasi di internet. Jika kamu merasa perlu informasi terbaru atau tidak yakin dengan jawabanmu, kamu bisa meminta pencarian web dengan menulis tag:

[SEARCH]kata kunci pencarian[/SEARCH]

Aturan penggunaan search:
- Gunakan HANYA jika benar-benar perlu informasi terbaru/faktual yang kamu tidak yakin
- Jangan gunakan untuk pertanyaan opini, salam, atau obrolan biasa
- Jangan gunakan jika kamu sudah cukup yakin dengan jawabanmu
- Tulis query pencarian yang spesifik dan efektif
- Untuk topik global/internasional, tulis query dalam bahasa Inggris agar hasil lebih akurat
- Untuk topik lokal Indonesia, boleh pakai bahasa Indonesia
- HANYA tulis tag [SEARCH], jangan tulis jawaban lain bersamaan tag itu
- Setelah mendapat hasil pencarian, jawab berdasarkan informasi tersebut dengan menyertakan sumber
"""


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


# ============================================
# HELPER: EXTRACT FULL TEXT FROM RESPONSE
# ============================================

def extract_full_text(response):
    """
    Extract text dari response Gemma 4.
    Gemma 4 selalu pakai thinking mode.
    Strategi: ambil TEXT parts dulu, kalau kosong ambil THINKING parts.
    """
    try:
        if not response.candidates:
            print("⚠️ No candidates in response")
            return None

        candidate = response.candidates[0]
        print(f"📊 Finish reason: {candidate.finish_reason}")
        print(f"📊 Parts count: {len(candidate.content.parts)}")

        text_parts = []
        thinking_parts = []

        for i, part in enumerate(candidate.content.parts):
            if hasattr(part, 'thought') and part.thought:
                if hasattr(part, 'text') and part.text:
                    thinking_parts.append(part.text)
                    print(f"📊 Part {i}: thinking ({len(part.text)} chars)")
                continue

            if hasattr(part, 'function_call') and part.function_call:
                print(f"📊 Part {i}: function_call (skipped)")
                continue

            if hasattr(part, 'text') and part.text:
                text_parts.append(part.text)
                print(f"📊 Part {i}: text ({len(part.text)} chars)")

        if text_parts:
            full_text = "\n".join(text_parts)
            total_text_len = len(full_text.strip())
            total_think_len = sum(len(t) for t in thinking_parts)

            print(f"📊 Text parts total: {total_text_len} chars")
            print(f"📊 Thinking parts total: {total_think_len} chars")

            if total_text_len > 100:
                print(f"📊 Using text parts: {total_text_len} chars")
                return full_text

            if thinking_parts and total_think_len > total_text_len:
                print(f"📊 Text too short ({total_text_len}), using thinking parts ({total_think_len} chars)")
                return "\n".join(thinking_parts)

            print(f"📊 Using short text parts: {total_text_len} chars")
            return full_text

        if thinking_parts:
            full_thinking = "\n".join(thinking_parts)
            print(f"📊 No text parts, using thinking: {len(full_thinking)} chars")
            return full_thinking

        print("⚠️ No parts found, trying response.text fallback")
        try:
            if response.text:
                print(f"📊 Fallback response.text: {len(response.text)} chars")
                return response.text
        except:
            pass

        print("⚠️ Response completely empty")
        return None

    except Exception as e:
        print(f"⚠️ extract_full_text error: {e}")
        try:
            if response.text:
                return response.text
        except:
            pass
        return None


def extract_search_query(response_text: str):
    """
    Cek apakah response Gemini mengandung tag [SEARCH]...[/SEARCH].
    Return query string jika ada, None jika tidak.
    """
    pattern = r'$$SEARCH$$(.*?)$$/SEARCH$$'
    match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
    if match:
        query = match.group(1).strip()
        if query:
            return query
    return None


def build_system_prompt(user_id):
    """Build system prompt with memory context and search capability."""
    memory_context = format_memories_for_prompt(user_id)
    parts = [BASE_SYSTEM_PROMPT, SEARCH_INSTRUCTION]
    if memory_context:
        parts.append(f"## Informasi tentang user\n{memory_context}")
    parts.append(MEMORY_EXTRACTION_PROMPT)
    return "\n\n".join(parts)


async def get_response(user_id, user_message, recent_messages):
    try:
        system_prompt = build_system_prompt(user_id)

        contents = []
        for role, message in recent_messages:
            gemini_role = "user" if role == "user" else "model"
            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[types.Part(text=message)]
                )
            )

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part(text=user_message)]
            )
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=2048,
                tools=[TVL_TOOL],
            )
        )

        candidate = response.candidates[0]

        function_call_part = None
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                function_call_part = part
                break

        if function_call_part:
            function_call = function_call_part.function_call
            protocol_name = function_call.args.get("protocol_name", "")

            print(f"🔧 Tool dipanggil: get_tvl_growth({protocol_name})")

            tool_result = await get_tvl_growth(protocol_name)
            formatted_result = format_tvl_result(tool_result)

            contents.append(candidate.content)

            function_response_parts = []
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fr_part = types.Part(
                        function_response=types.FunctionResponse(
                            name=part.function_call.name,
                            response={"result": formatted_result}
                        ),
                    )
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

            response2 = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                    max_output_tokens=2048,
                    tools=[TVL_TOOL],
                )
            )

            result = extract_full_text(response2)
            return result if result else formatted_result

        result = extract_full_text(response)
        if not result:
            print("⚠️ Gemini response kosong")
            return "Maaf, aku tidak bisa memproses pesanmu. Coba kirim ulang ya."

        return result

    except Exception as e:
        error_msg = str(e).lower()
        print(f"❌ Gemini error: {e}")

        if "thought_signature" in error_msg:
            print("⚠️ Thought signature error, using direct tool result")
            try:
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


async def get_response_with_search(user_id, user_message, recent_messages):
    """
    Wrapper get_response yang handle auto web search.

    Flow:
    1. Panggil get_response() biasa — 1 API call
    2. Cek apakah response mengandung [SEARCH]query[/SEARCH]
    3. Jika ya:
       - Execute search lokal dengan multi-query otomatis (0 API call)
       - Kirim hasil search + pertanyaan asli ke Gemini — 1 API call lagi
       - Return jawaban final
    4. Jika tidak: return response biasa
    """
    # Call 1: response biasa
    response = await get_response(user_id, user_message, recent_messages)

    if not response:
        return response

    # Cek apakah Gemini minta search
    search_query = extract_search_query(response)

    if not search_query:
        return response

    # Gemini minta search — execute secara lokal (multi-query otomatis)
    print(f"🔍 [WebSearch] Gemini requested search: '{search_query}'")

    search_results = await asyncio.to_thread(web_search, search_query)

    if not search_results:
        search_context = (
            f"Pencarian web untuk '{search_query}' tidak menemukan hasil. "
            f"Jawab pertanyaan user sebaik mungkin berdasarkan pengetahuanmu. "
            f"Jujur katakan kalau kamu tidak menemukan info terbaru."
        )
    else:
        search_context = format_search_results(search_query, search_results)

    # Prompt cerdas dengan instruksi cek relevansi
    search_prompt = (
        f"Kamu tadi meminta pencarian web. Berikut hasilnya:\n\n"
        f"{search_context}\n\n"
        f"Pertanyaan user yang harus dijawab: {user_message}\n\n"
        f"Tugasmu:\n"
        f"- Cek dulu apakah hasil pencarian relevan dengan pertanyaan user\n"
        f"- Jika relevan, jawab berdasarkan informasi dari hasil pencarian\n"
        f"- Sertakan sumber jika relevan\n"
        f"- Jika hasil tidak relevan, jawab dari pengetahuanmu dan jujur katakan "
        f"bahwa hasil pencarian kurang membantu\n"
        f"- Tetap ringkas dan natural dalam bahasa Indonesia"
    )

    # Call 2: kirim hasil search ke Gemini
    print(f"🔍 [WebSearch] Sending search results to Gemini (Call 2)")
    response_with_search = await get_response(
        user_id, search_prompt, recent_messages
    )

    if response_with_search:
        return response_with_search
    else:
        return (
            f"🔍 Hasil pencarian untuk: {search_query}\n\n"
            f"{search_context}\n\n"
            f"(Maaf, saya tidak bisa merangkum hasilnya saat ini)"
        )


async def search_and_respond(user_id, query, recent_messages):
    """
    Untuk command /search manual.
    Langsung search tanpa minta Gemini decide dulu.
    Hanya 1 API call.
    """
    print(f"🔍 [WebSearch] Manual search: '{query}'")

    # Search lokal (multi-query otomatis)
    search_results = await asyncio.to_thread(web_search, query)

    if not search_results:
        return f"🔍 Pencarian untuk '{query}' tidak menemukan hasil. Coba kata kunci yang berbeda."

    search_context = format_search_results(query, search_results)

    # Prompt cerdas dengan instruksi cek relevansi
    search_prompt = (
        f"User mencari informasi tentang: {query}\n\n"
        f"Berikut hasil pencarian web:\n\n"
        f"{search_context}\n\n"
        f"Tugasmu:\n"
        f"- Cek dulu apakah hasil pencarian relevan dengan yang user tanyakan\n"
        f"- Jika relevan, rangkum dengan rapi dan natural dalam bahasa Indonesia\n"
        f"- Sertakan poin-poin penting dan sumber yang relevan\n"
        f"- Jika hasil pencarian tidak relevan atau tidak menjawab pertanyaan user, "
        f"katakan bahwa hasil kurang relevan dan berikan jawaban sebaik mungkin dari pengetahuanmu\n"
        f"- Jangan mengarang informasi yang tidak ada di hasil pencarian"
    )

    response = await get_response(user_id, search_prompt, recent_messages)

    if response:
        return response
    else:
        return f"🔍 Hasil pencarian untuk: '{query}'\n\n{search_context}"


# ============================================
# FARCASTER POST GENERATOR
# ============================================

FARCASTER_POST_PROMPT = """You are a sharp, honest crypto analyst who posts on Farcaster.
Your audience is crypto-native people who hate generic bot posts and shill content.
They value original thinking, honest takes, and specific data.

ANALYSIS RULES — apply these BEFORE writing:
- If 24h volume / market cap ratio > 2x → flag as suspicious (possible wash trading or manipulation)
- If coin is >80% below ATH → be cautious, frame as high-risk, don't spin it as "opportunity"
- If 24h change > +100% → question sustainability, look for pump-and-dump signals
- If 24h change is very negative but 7d/30d is positive → note the divergence, could be healthy pullback or trend reversal
- If 24h change is positive but 7d/30d is negative → likely dead cat bounce, be skeptical
- If market cap is very small (< \$10M) with huge volume → extra caution, likely manipulation
- Always consider: is this data telling a COHERENT story or are there contradictions?

WRITING RULES:
- Write exactly ONE post, ready to copy-paste to Farcaster
- No labels, headers, or prefixes like "Analysis:" or "Post:" — just the post itself
- Do NOT wrap the post in quotation marks
- Max 900 characters (Farcaster limit is 1024, leave room for safety)
- Include $TICKER with dollar sign
- Sound like a thoughtful human, NOT a bot — vary your sentence structure
- Be specific — use actual numbers from the data
- Have a clear stance: bullish, bearish, cautious, or worth-watching
- Tone: curious, analytical, honest. NEVER hype or shill
- Don't start with generic openers like "$X is exploding!" or "$X alert!"
- Start with an interesting observation, question, or pattern you noticed
- End with NFA/DYOR 🔍
- Write in English"""


async def generate_farcaster_post(data_text, post_type="daily_pick"):
    """Generate 1 Farcaster-ready post — 1 API call, no chat context"""
    try:
        if post_type == "daily_pick":
            user_prompt = f"""Here is today's market data. Pick the most interesting coin and write a post about it.
"Most interesting" does NOT mean "highest gainer" — it means the coin with the most compelling or unusual data story.

DATA:
{data_text}

Write the post now:"""

        elif post_type == "analyze":
            user_prompt = f"""Here is the data for this coin. Analyze it critically and write a Farcaster post.

DATA:
{data_text}

Write the post now:"""

        else:
            user_prompt = f"""Based on the data below, write a Farcaster post.

DATA:
{data_text}

Write the post now:"""

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
            config=types.GenerateContentConfig(
                system_instruction=FARCASTER_POST_PROMPT,
                temperature=0.85,
                max_output_tokens=400,
            )
        )

        text = extract_full_text(response)

        if text:
            text = text.strip()

            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1].strip()
            if text.startswith("'") and text.endswith("'"):
                text = text[1:-1].strip()

            unwanted_prefixes = [
                "Farcaster Post:", "Farcaster post:",
                "Post:", "post:",
                "Draft:", "draft:",
                "Here's the post:", "Here is the post:",
            ]
            for prefix in unwanted_prefixes:
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()

            if "NFA" not in text and "DYOR" not in text:
                text += "\n\nNFA/DYOR 🔍"

            if len(text) > 1000:
                cut = text[:950].rsplit(". ", 1)[0]
                text = cut + ".\n\nNFA/DYOR 🔍"

            return text

        print("⚠️ Farcaster post: Gemini response kosong")
        return None

    except Exception as e:
        error_msg = str(e).lower()
        print(f"❌ Error generate farcaster post: {e}")

        if "quota" in error_msg or "429" in error_msg:
            return "⚠️ Quota API habis. Coba lagi nanti."

        return None


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
            config=types.GenerateContentConfig(
                system_instruction="Kamu adalah asisten yang merangkum dokumen. Rangkum dengan detail, pertahankan semua informasi penting.",
                temperature=0.3,
                max_output_tokens=2048,
            )
        )

        result = extract_full_text(response)
        if result:
            return result
        return f"[Gagal merangkum bagian {chunk_number}]"

    except Exception as e:
        print(f"❌ Error summarize chunk {chunk_number}: {e}")
        return f"[Error merangkum bagian {chunk_number}: {e}]"


async def process_long_document(user_id, chunks, file_name, user_caption, recent_messages):
    """Proses dokumen panjang: rangkum per chunk, lalu jawab final"""
    try:
        print(f"📄 Processing {len(chunks)} chunks for {file_name}")

        summaries = []
        for i, chunk in enumerate(chunks, 1):
            print(f"  📝 Summarizing chunk {i}/{len(chunks)}...")
            summary = await summarize_chunk(chunk, i, len(chunks), file_name)
            summaries.append(f"[Bagian {i}]\n{summary}")

        combined_summary = "\n\n".join(summaries)

        if user_caption:
            final_prompt = f"""Berikut adalah rangkuman dari dokumen "{file_name}" yang dikirim user:

{combined_summary}

Perintah user: {user_caption}

Jawab sesuai permintaan user berdasarkan isi dokumen di atas."""
        else:
            final_prompt = f"""Berikut adalah rangkuman dari dokumen "{file_name}" yang dikirim user:

{combined_summary}

Tolong berikan rangkuman lengkap dan poin-poin penting dari dokumen ini."""

        from app.database import save_message, get_recent_messages
        save_message(user_id, "user", final_prompt)

        fresh_messages = get_recent_messages(user_id, limit=20)

        raw_response = await get_response(user_id, final_prompt, fresh_messages)

        print(f"  ✅ Document processing done. Total API calls: {len(chunks) + 1}")
        return raw_response

    except Exception as e:
        print(f"❌ Error process_long_document: {e}")
        return "Maaf, gagal memproses dokumen panjang ini. Coba kirim ulang ya."


async def generate_document_content(user_id, instruction, recent_messages):
    """Generate konten terstruktur untuk dokumen PDF/DOCX"""
    try:
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
            config=types.GenerateContentConfig(
                system_instruction="Kamu adalah penulis dokumen profesional. Tulis konten yang terstruktur, lengkap, informatif, dan rapi. Ikuti format yang diminta dengan tepat.",
                temperature=0.7,
                max_output_tokens=4096,
            )
        )

        result = extract_full_text(response)
        if result:
            return result
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
                max_output_tokens=2048,
            )
        )

        result = extract_full_text(response)
        if result:
            return result

        return "Maaf, aku tidak bisa menganalisis gambar ini. Coba kirim ulang ya."

    except Exception as e:
        error_msg = str(e).lower()
        print(f"❌ Error analyze image: {e}")

        if "quota" in error_msg or "429" in error_msg:
            return "Maaf, quota API lagi habis. Coba lagi nanti ya."

        if "not supported" in error_msg or "invalid" in error_msg:
            return "Maaf, model ini belum bisa analisis gambar. Coba kirim ulang nanti ya."

        return "Maaf, gagal menganalisis gambar. Coba kirim ulang ya."
