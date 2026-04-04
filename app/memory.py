import re
from app.database import upsert_memory, get_all_memories


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
                    print(f"Memory saved: {key} = {value}")

        clean_response = re.sub(pattern, "", response_text, flags=re.DOTALL | re.IGNORECASE).strip()
        return clean_response

    # Fallback sederhana tanpa regex kompleks
    if "MEMORY" in response_text.upper():
        lines = response_text.split("\n")
        clean_lines = []
        inside_memory = False

        for line in lines:
            upper_line = line.strip().upper()

            if "MEMORY" in upper_line and "/" not in upper_line:
                inside_memory = True
                continue
            elif "MEMORY" in upper_line and "/" in upper_line:
                inside_memory = False
                continue

            if inside_memory:
                line_stripped = line.strip()
                if ":" in line_stripped:
                    key, value = line_stripped.split(":", 1)
                    key = key.strip().lower().replace(" ", "_")
                    value = value.strip()
                    if key and value and len(key) < 30:
                        upsert_memory(user_id, key, value)
                        print(f"Memory saved (fallback): {key} = {value}")
            else:
                clean_lines.append(line)

        return "\n".join(clean_lines).strip()

    return response_text


def format_memories_for_prompt(user_id):
    memories = get_all_memories(user_id)

    if not memories:
        return ""

    lines = ["Berikut adalah hal-hal yang kamu ingat tentang user:"]
    for key, value in memories:
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: {value}")

    return "\n".join(lines)
