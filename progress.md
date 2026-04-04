# Summary diskusi kita

### Tujuan proyek
Membangun **AI assistant personal di Telegram** berbasis **Gemini API**, dengan fokus:
- hemat quota
- bisa menyimpan percakapan
- punya memory bertahap
- makin lama makin kontekstual / "pintar"

---

# 1. Use case dan constraint

## Use case
- hanya untuk **personal use**
- hanya **1 user**
- bahasa default: **Bahasa Indonesia**
- kalau diminta baru jawab bahasa Inggris

## Constraint awal
Awalnya model yang dipakai punya quota kecil:
- **RPM 5**
- **TPM 250K**
- **RPD 20**

Karena itu arsitektur awal dibuat sangat hemat:
- target **1 API call per pesan**
- jangan boros API call tambahan
- memory extraction direncanakan **lokal / rule-based**
- storage chat dan memory dilakukan **lokal**

---

# 2. Stack yang dipakai

## Bahasa & library
- **Python**
- **python-telegram-bot**
- **google-genai**
- **python-dotenv**
- **SQLite**

## Config
Pakai `.env` untuk:
- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`

---

# 3. Struktur proyek yang sekarang

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

Catatan:
- `assistant.db` sekarang disimpan di `/data/assistant.db` (Railway persistent volume)
- tidak lagi di root project

---

# 4. Deployment

## Platform
- Kode disimpan di **GitHub**
- Deploy otomatis ke **Railway** setiap push ke GitHub

## Alur update
```
edit kode di lokal → push ke GitHub → Railway otomatis redeploy
```

## Railway usage
- Biaya sangat murah, estimasi **$0.01 / bulan**
- $5 credit one-time cukup untuk berbulan-bulan

---

# 5. Persistent storage — Railway Volume

## Masalah sebelumnya
File `assistant.db` hilang setiap kali Railway redeploy karena container di-build ulang dari nol.

## Solusi
Pakai **Railway Volume** — storage persisten yang tidak ikut hilang saat redeploy.

## Cara setup yang sudah dilakukan
1. Buka service bot di Railway dashboard
2. Masuk ke tab **Settings**
3. Scroll ke bagian **Volumes**
4. Set mount path ke `/data`
5. Klik **Attach volume to service**
6. Deploy

## Perubahan kode
Di `app/database.py`, ubah:
```python
DB_NAME = "assistant.db"
```
menjadi:
```python
DB_NAME = "/data/assistant.db"
```

## Status
- ✅ Volume terpasang dan aktif
- ✅ Muncul di Railway usage
- ✅ Database tidak hilang saat redeploy

---

# 6. Perubahan penting yang sudah dilakukan

## 6.1 SQLite berhasil ditambahkan
Tujuan:
- menyimpan riwayat chat permanen
- agar data tidak hilang saat restart

### Tabel yang sudah dibuat
#### `conversations`
```sql
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `memories`
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

## 6.2 File `app/database.py`

Isi lengkap file sekarang:

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


def get_recent_messages(user_id, limit=10):
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
```

---

# 7. Integrasi ke bot Telegram

## 7.1 Import di `app/bot.py`
```python
from app.config import TELEGRAM_BOT_TOKEN
from app.gemini import get_response
from app.database import init_db, save_message, get_recent_messages
```

## 7.2 Handler `handle_message()`
```python
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_message = update.message.text

    save_message(user_id, "user", user_message)

    recent_messages = get_recent_messages(user_id, limit=10)

    await update.message.chat.send_action("typing")

    response = await get_response(user_id, user_message, recent_messages)

    save_message(user_id, "assistant", response)

    await update.message.reply_text(response)
```

## 7.3 `main()` di `app/bot.py`
- `init_db()` dipanggil sebelum bot start
- Builder pakai timeout lebih besar:

```python
Application.builder() \
    .token(TELEGRAM_BOT_TOKEN) \
    .connect_timeout(30) \
    .read_timeout(30) \
    .write_timeout(30) \
    .build()
```

---

# 8. Evolusi memory

## Tahap awal
Memory pakai RAM di `app/gemini.py`:
- `chat_histories = {}`
- `MAX_HISTORY = 10`
- hilang saat restart

## Tahap kedua
Memory dipindah ke SQLite-backed recent history:
- pesan disimpan ke DB
- diambil saat ada pesan baru
- restart tidak menghapus konteks

## Tahap ketiga (sekarang)
Tabel `memories` sudah dibuat untuk long-term memory.
File `app/memory.py` sudah dibuat untuk rule-based extraction.

---

# 9. `app/gemini.py`

## Variabel penting
```python
client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """Kamu adalah asisten AI personal yang helpful dan ramah.
Jawab selalu dalam Bahasa Indonesia kecuali diminta bahasa lain.
Jawab dengan natural seperti teman ngobrol, tidak kaku.
Usahakan jawaban ringkas, jelas, dan tidak terlalu panjang kecuali diminta detail.
Kalau memberi daftar, batasi 3-5 poin saja.
Gunakan format teks biasa yang rapi untuk Telegram.
Hindari markdown seperti **bold**, *italic*, atau format aneh lainnya.
Kalau user meminta informasi real-time, lokasi terdekat, data terbaru, atau hasil pencarian aktual, jelaskan dengan jujur bahwa kamu tidak sedang mengakses internet, GPS, atau Google Maps secara langsung. Berikan saran umum saja."""
```

## Parameter generation
```python
temperature = 0.7
max_output_tokens = 1500
```

## Fungsi penting
- `build_contents_from_history(recent_messages)`
- `get_response(user_id, user_message, recent_messages)`

---

# 10. `app/config.py`

```python
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
```

---

# 11. Model Gemini yang dipakai

## Model sekarang
```python
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
```

## Limit
- **RPM 15**
- **TPM 250K**
- **RPD 500**

## Catatan
- Model ini masih berlabel `preview`
- Bottleneck terbesar sebelumnya adalah RPD — sekarang sudah jauh lebih longgar

---

# 12. File `app/memory.py` — sudah dibuat, belum diintegrasikan

```python
import re
from app.database import upsert_memory

PATTERNS = [
    ("nama_user", [
        r"nama(?:ku| saya| gue| aku)?\s+(?:adalah\s+)?(\w+)",
        r"(?:panggil|biasa dipanggil)\s+(?:aku|saya|gue)?\s*(\w+)",
        r"aku\s+(\w+)\s*$",
    ]),
    ("hobi_user", [
        r"hobi(?:ku| saya| gue| aku)?\s+(?:adalah\s+)?(.+)",
        r"aku\s+suka\s+(.+)",
        r"saya\s+suka\s+(.+)",
        r"gue\s+suka\s+(.+)",
    ]),
    ("pekerjaan_user", [
        r"pekerjaan(?:ku| saya| gue| aku)?\s+(?:adalah\s+)?(.+)",
        r"kerja(?:ku| saya| gue| aku)?\s+(?:sebagai\s+)?(.+)",
        r"aku\s+(?:adalah\s+)?(?:seorang\s+)?(.+?)(?:\s+di\s+.+)?$",
        r"saya\s+(?:adalah\s+)?(?:seorang\s+)?(.+?)(?:\s+di\s+.+)?$",
    ]),
]

def extract_and_save_memory(user_id, user_message):
    message = user_message.lower().strip()

    for key, patterns in PATTERNS:
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                value = match.group(1).strip()
                if value:
                    upsert_memory(user_id, key, value)
                break
```

---

# 13. Status proyek saat ini

## Sudah jadi
- ✅ Telegram bot aktif dan polling
- ✅ Gemini API terhubung
- ✅ Model baru dengan quota lebih besar
- ✅ Chat tersimpan di SQLite
- ✅ Recent history diambil dari DB
- ✅ Context percakapan jalan setelah restart
- ✅ Database persisten via Railway Volume
- ✅ Tabel `memories` sudah dibuat
- ✅ File `app/memory.py` sudah dibuat

## Belum jadi
- ❌ `extract_and_save_memory()` belum dipanggil di `bot.py`
- ❌ Memory belum diinject ke prompt Gemini
- ❌ `get_all_memories()` belum dipakai
- ❌ Semantic search / vector retrieval
- ❌ Fallback multi-model

---

# 14. Rekomendasi next step untuk agent berikutnya

## Urutan yang harus dilanjutkan:

### Step 1 — Integrasi `memory.py` ke `bot.py`
Tambahkan di `handle_message()`:
```python
from app.memory import extract_and_save_memory

# panggil setelah dapat user_message
extract_and_save_memory(user_id, user_message)
```

### Step 2 — Inject memory ke prompt Gemini
Di `app/gemini.py`, ambil memories dan inject ke system prompt:
```python
from app.database import get_all_memories

memories = get_all_memories(user_id)
# format jadi string dan tambahkan ke SYSTEM_PROMPT
```

### Step 3 — Test end-to-end
- Kirim pesan yang mengandung nama / hobi / pekerjaan
- Cek apakah masuk ke tabel `memories`
- Cek apakah bot mengingat di percakapan berikutnya

---

# 15. Prinsip arsitektur yang harus dijaga

- tetap hemat request
- **1 API call per user message**
- gunakan local logic / SQLite sebanyak mungkin
- jangan buru-buru menambah fitur yang boros API
- default bahasa Indonesia
- pembahasan **pelan-pelan** dan praktis
- jangan langsung lempar full code besar
