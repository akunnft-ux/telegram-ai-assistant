import re
from app.database import upsert_memory, get_all_memories


# Kategori utama sebagai panduan (Gemini boleh tambah di luar ini)
CORE_CATEGORIES = [
    "nama_user",
    "kota_tinggal",
    "pekerjaan",
    "hobi",
    "status",
    "makanan_favorit",
    "musik_favorit",
    "bahasa_preferensi",
    "gaya_komunikasi",
]


def extract_memory_from_response(user_id, response_text):
    """
    Parse [MEMORY] block dari jawaban Gemini.
    Simpan ke SQLite, lalu return jawaban bersih tanpa block.
    """
    pattern = r"$$MEMORY$$(.*?)$$/MEMORY$$"
    match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)

    if match:
        memory_block = match.group(1).strip()

        for line in memory_block.split("\n"):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                value = value.strip()

                if key and value:
                    upsert_memory(user_id, key, value)
                    print(f"💾 Memory saved: {key} = {value}")

        # Hapus [MEMORY] block dari jawaban
        clean_response = re.sub(pattern, "", response_text, flags=re.DOTALL | re.IGNORECASE).strip()
        return clean_response

    # Fallback: coba deteksi format tanpa bracket yang rapi
    fallback_pattern = r"$$?\s*MEMORY\s*$$?(.*?)$$?\s*/\s*MEMORY\s*$$?"
    match2 = re.search(fallback_pattern, response_text, re.DOTALL | re.IGNORECASE)

    if match2:
        memory_block = match2.group(1).strip()

        for line in memory_block.split("\n"):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                value = value.strip()

                if key and value:
                    upsert_memory(user_id, key, value)
                    print(f"💾 Memory saved (fallback): {key} = {value}")

        clean_response = re.sub(fallback_pattern, "", response_text, flags=re.DOTALL | re.IGNORECASE).strip()
        return clean_response

    return response_text


def format_memories_for_prompt(user_id):
    """
    Ambil semua memories dari DB, format jadi teks untuk system prompt.
    """
    memories = get_all_memories(user_id)

    if not memories:
        return ""

    lines = ["Berikut adalah hal-hal yang kamu ingat tentang user:"]
    for key, value in memories:
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: {value}")

    return "\n".join(lines)
