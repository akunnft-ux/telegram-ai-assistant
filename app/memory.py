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

        clean_response = re.sub(pattern, "", response_text, flags=re.DOTALL | re.IGNORECASE).strip()
        return clean_response

    # Fallback: hapus sisa-sisa MEMORY tag yang tidak rapi
    fallback_pattern = r"(?:$$?\s*/?MEMORY\s*$$?\s*)+"
    remaining = re.sub(fallback_pattern, "", response_text, flags=re.IGNORECASE).strip()

    if remaining != response_text.strip():
        for line in response_text.split("\n"):
            line = line.strip()
            if ":" in line and "MEMORY" not in line.upper() and not line.endswith("?"):
                key, value = line.split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                value = value.strip()
                if key and value and len(key) < 30:
                    upsert_memory(user_id, key, value)
                    print(f"💾 Memory saved (fallback): {key} = {value}")
        return remaining

    return response_text
