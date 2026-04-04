

# Summary Lengkap Proyek Telegram AI Assistant

---

## Tujuan Proyek
Membangun **AI assistant personal di Telegram** berbasis **Gemini API**, dengan fokus:
- Hemat quota
- Bisa menyimpan percakapan
- Punya memory bertahap
- Makin lama makin kontekstual / "pintar"
- Self-learning

---

## 1. Use Case dan Constraint

### Use case
- Hanya untuk **personal use**
- Hanya **1 user**
- Bahasa default: **Bahasa Indonesia**
- Kalau diminta baru jawab bahasa Inggris

### Constraint
- Model: `gemini-3.1-flash-lite-preview`
- RPM 15, TPM 250K, RPD 500
- Target **1 API call per pesan**
- Memory extraction **dititipkan** di call yang sama
- Storage lokal pakai **SQLite**

---

## 2. Stack yang Dipakai

### Bahasa & Library
- **Python**
- **python-telegram-bot**
- **google-genai**
- **python-dotenv**
- **SQLite**

### Config (`.env`)
- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`

---

## 3. Struktur Proyek

```bash
telegram-ai-assistant/
├── .env
├── app/
│   ├── bot.py
│   ├── config.py
│   ├── gemini.py
│   ├── database.py
│   └── memory.py
└── venv/
```

Database: `/data/assistant.db` (Railway persistent volume)

---

## 4. Deployment

### Platform
- Kode di **GitHub**
- Deploy otomatis ke **Railway** setiap push

### Alur Update
```
edit kode di lokal → push ke GitHub → Railway otomatis redeploy
```

### Railway
- Biaya ~$0.01/bulan
- Persistent volume di `/data`

---

## 5. Database — SQLite

### Tabel `conversations`
```sql
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Tabel `memories`
```sql
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, key)
);
```

---

## 6. File Lengkap

### 6.1 `app/config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
```

---

### 6.2 `app/database.py`

```python
import sqlite3

DB_NAME = "/data/assistant.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, key)
    )
    """)

    conn.commit()
    conn.close()

    print("✅ DB initialized, tabel memories siap")


def save_message(user_id, role, message):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO conversations (user_id, role, message)
    VALUES (?, ?, ?)
    """, (str(user_id), role, message))

    conn.commit()
    conn.close()


def get_recent_messages(user_id, limit=20):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT role, message
    FROM conversations
    WHERE user_id = ?
    ORDER BY id DESC
    LIMIT ?
    """, (str(user_id), limit))

    rows = cursor.fetchall()
    conn.close()

    rows.reverse()
    return rows


def upsert_memory(user_id, key, value):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO memories (user_id, key, value)
    VALUES (?, ?, ?)
    ON CONFLICT(user_id, key)
    DO UPDATE SET value = excluded.value,
                  updated_at = CURRENT_TIMESTAMP
    """, (str(user_id), key, value))

    conn.commit()
    conn.close()


def get_all_memories(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT key, value
    FROM memories
    WHERE user_id = ?
    ORDER BY updated_at DESC
    """, (str(user_id),))

    rows = cursor.fetchall()
    conn.close()

    return rows


def delete_memory(user_id, key):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    DELETE FROM memories
    WHERE user_id = ? AND key = ?
    """, (str(user_id), key))

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted > 0
```

---

### 6.3 `app/memory.py`

```python
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
    pattern = r"\[MEMORY\](.*?)\[/MEMORY\]"
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

    if len(memories) <= 10:
        lines = ["Berikut adalah hal-hal yang kamu ingat tentang user:"]
        for key, value in memories:
            label = key.replace("_", " ").title()
            lines.append(f"- {label}: {value}")
        return "\n".join(lines)

    parts = []
    for key, value in memories:
        label = key.replace("_", " ")
        parts.append(f"{label} adalah {value}")

    summary = "Berikut ringkasan tentang user: " + ". ".join(parts) + "."

    return summary
```

---

### 6.4 `app/gemini.py`

```python
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
                "max_output_tokens": 1500,
            }
        )

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
```

---

### 6.5 `app/bot.py`

```python
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from app.config import TELEGRAM_BOT_TOKEN
from app.gemini import get_response
from app.database import init_db, save_message, get_recent_messages, get_all_memories, delete_memory
from app.memory import extract_memory_from_response


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Halo! Aku asisten AI kamu. Langsung aja ngobrol 😊")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_message = update.message.text

    save_message(user_id, "user", user_message)

    recent_messages = get_recent_messages(user_id, limit=20)

    await update.message.chat.send_action("typing")

    raw_response = await get_response(user_id, user_message, recent_messages)

    clean_response = extract_memory_from_response(user_id, raw_response)

    save_message(user_id, "assistant", clean_response)

    await update.message.reply_text(clean_response)


async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    memories = get_all_memories(user_id)

    if not memories:
        await update.message.reply_text("Aku belum punya catatan apa-apa tentang kamu.")
        return

    lines = ["Ini yang aku ingat tentang kamu:\n"]
    for key, value in memories:
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: {value}")

    await update.message.reply_text("\n".join(lines))


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not context.args:
        await update.message.reply_text("Tulis key yang mau dihapus.\nContoh: /forget nama_kucing")
        return

    key = "_".join(context.args).lower()
    deleted = delete_memory(user_id, key)

    if deleted:
        await update.message.reply_text(f"Oke, aku sudah lupa tentang '{key}'.")
    else:
        await update.message.reply_text(f"Aku tidak punya catatan '{key}'.")


def main():
    init_db()

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("memory", memory_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
```

---

## 7. Arsitektur Memory System

### Hybrid: Gemini + Lokal

| Layer | Fungsi | API call? |
|-------|--------|-----------|
| Gemini extraction | Ekstrak info dari pesan user, titipkan di 1 API call | Tidak tambahan |
| `[MEMORY]` block parsing | Parse output Gemini, simpan ke DB | Tidak |
| Fallback parsing | Kalau format tidak rapi, tetap bisa di-parse | Tidak |
| Memory injection | Inject memories ke system prompt setiap pesan | Tidak |
| Memory summary | Kalau >10 memories, ringkas jadi paragraf | Tidak |

### Kategori: Semi-bebas
- Ada daftar kategori utama sebagai panduan
- Gemini boleh buat kategori baru yang relevan
- Key format `snake_case`

### Alur per pesan
```
User kirim pesan
    │
    ▼
bot.py: save_message() ke DB
    │
    ▼
bot.py: ambil recent_messages (20) + memories dari DB
    │
    ▼
gemini.py: bangun system prompt dinamis (base + memories + extraction instruction)
    │
    ▼
gemini.py: kirim ke Gemini (1 API call)
    │
    ▼
Gemini jawab + [MEMORY] block (kalau ada info baru)
    │
    ▼
memory.py: parse [MEMORY] block → simpan ke DB → return jawaban bersih
    │
    ▼
bot.py: simpan jawaban bersih ke DB → kirim ke user
```

---

## 8. Commands yang Tersedia

| Command | Fungsi |
|---------|--------|
| `/start` | Salam pembuka |
| `/memory` | Lihat semua memory yang tersimpan |
| `/forget [key]` | Hapus memory tertentu |

---

## 9. Error Handling

| Kondisi | Pesan ke user |
|---------|---------------|
| Response kosong | "tidak bisa memproses, coba kirim ulang" |
| Quota habis (429) | "quota habis, tunggu beberapa menit" |
| Timeout | "server lambat, coba lagi" |
| API key salah (401/403) | "masalah autentikasi, hubungi admin" |
| Model tidak ada (404) | "model tidak tersedia" |
| Error lain | "ada gangguan, coba lagi nanti" |

---

## 10. Status Proyek

### Sudah Jadi
- ✅ Telegram bot aktif dan polling
- ✅ Gemini API terhubung
- ✅ Chat tersimpan di SQLite
- ✅ Recent history 20 pesan dari DB
- ✅ Database persisten via Railway Volume
- ✅ Memory system hybrid (Gemini + lokal parsing)
- ✅ Semi-bebas kategori (self-learning)
- ✅ Memory injection ke system prompt
- ✅ Memory summary untuk hemat token
- ✅ `[MEMORY]` block tersembunyi dari user
- ✅ Command `/memory` dan `/forget`
- ✅ Error handling informatif

### Belum Jadi / Opsi Selanjutnya
- ❌ Command `/clearmemory` — hapus semua memory sekaligus
- ❌ Command `/clearhistory` — hapus chat history
- ❌ Semantic search / vector retrieval
- ❌ Fallback multi-model (kalau Gemini down, pakai model lain)
- ❌ Rate limiting per user
- ❌ Image / voice message handling
- ❌ Scheduled memory cleanup

---

## 11. Prinsip Arsitektur

- Tetap hemat request — **1 API call per user message**
- Gunakan local logic / SQLite sebanyak mungkin
- Jangan buru-buru menambah fitur yang boros API
- Default bahasa Indonesia
- Pembahasan **pelan-pelan** dan praktis
- Jangan langsung lempar full code besar
