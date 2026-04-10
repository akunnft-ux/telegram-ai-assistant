Berikut summary detail proyek saat ini, disusun agar AI agent berikutnya bisa langsung melanjutkan tanpa salah konteks.

---

# Summary Lengkap Proyek Telegram AI Assistant

## 1. Tujuan Proyek

Membangun AI assistant personal di Telegram berbasis Gemini API dengan karakteristik:

- Personal use
- Hanya 1 user
- Bahasa default Indonesia
- Hemat quota
- Menyimpan percakapan
- Memiliki memory bertahap
- Semakin kontekstual dari waktu ke waktu
- Bisa membaca dokumen
- Bisa menganalisis gambar
- Bisa membuat file PDF dan DOCX

Prinsip utama:

- 1 API call per pesan normal
- Max 2+ hanya jika fitur memang butuh multi-step, misalnya dokumen panjang dengan chunking
- Local logic dan SQLite dipakai semaksimal mungkin
- Jangan menambah fitur boros API tanpa alasan jelas
- Pembahasan dan perubahan dilakukan pelan-pelan, praktis, tidak lompat ke arsitektur besar

---

## 2. Constraint Sistem

### Model utama
- `gemini-3.1-flash-lite-preview`

### Quota / limit
- RPM: 15
- TPM: 250K
- RPD: 500

### Prinsip request
- Chat biasa: 1 API call
- Tool DeFi TVL: idealnya 2 call, tapi saat ini di-bypass jadi 1 call final karena issue `thought_signature`
- Dokumen pendek: 1 API call
- Dokumen panjang: N chunk summaries + 1 final call
- Analisis gambar: 1 API call
- Generate PDF/DOCX: 1 API call untuk generate content, lalu file dibuat lokal di Python

---

## 3. Stack yang Dipakai

### Bahasa
- Python

### Library utama
- `python-telegram-bot`
- `google-genai`
- `python-dotenv`
- `sqlite3` bawaan Python
- `httpx`

### Library dokumen
- `PyPDF2`
- `python-docx`
- `openpyxl`
- `fpdf2`

### Env variables
Di `.env`:

- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`

---

## 4. Struktur Proyek

Struktur saat ini:

```bash
telegram-ai-assistant/
├── .env
├── requirements.txt
├── app/
│   ├── bot.py
│   ├── config.py
│   ├── gemini.py
│   ├── database.py
│   ├── memory.py
│   └── tools.py
└── venv/
```

Database SQLite disimpan di Railway persistent volume:

```bash
/data/assistant.db
```

---

## 5. Deployment

### Platform
- Source code di GitHub
- Deploy otomatis ke Railway setiap push

### Alur deploy
```text
edit lokal → git add/commit → push GitHub → Railway auto redeploy
```

### Storage persisten
- Railway volume di `/data`

---

## 6. Database Schema

## Tabel `conversations`

Dipakai untuk menyimpan history chat.

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Kolom
- `id`: auto increment
- `user_id`: Telegram user id dalam string
- `role`: `"user"` atau `"assistant"`
- `message`: isi pesan
- `created_at`: timestamp otomatis

---

## Tabel `memories`

Dipakai untuk menyimpan memory/fakta tentang user.

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

### Kolom
- `id`: auto increment
- `user_id`: Telegram user id dalam string
- `key`: nama memory dalam snake_case
- `value`: isi memory
- `created_at`
- `updated_at`

### Constraint
- `UNIQUE(user_id, key)` agar 1 key per user selalu di-update, bukan diduplikasi

---

## 7. File dan Fungsinya

# 7.1 `app/config.py`

Fungsi:
- Load environment variables
- Menyediakan konstanta model

Isi penting:
- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`
- `GEMINI_MODEL = "gemini-3.1-flash-lite-preview"`

---

# 7.2 `app/database.py`

Fungsi utama:

- `get_connection()`
  - buka koneksi SQLite ke `/data/assistant.db`

- `init_db()`
  - buat tabel `conversations` dan `memories` jika belum ada

- `save_message(user_id, role, message)`
  - simpan pesan ke `conversations`

- `get_recent_messages(user_id, limit=20)`
  - ambil history terbaru
  - query DESC lalu di-reverse agar urut kronologis

- `upsert_memory(user_id, key, value)`
  - insert/update memory berdasarkan `(user_id, key)`

- `get_all_memories(user_id)`
  - ambil semua memories user
  - urut `updated_at DESC`

- `delete_memory(user_id, key)`
  - hapus satu memory tertentu

- `clear_history(user_id)`
  - hapus semua percakapan di tabel `conversations` untuk user itu
  - dipakai oleh command `/clearhistory`

Catatan:
- Semua `user_id` disimpan sebagai string

---

# 7.3 `app/memory.py`

Fungsi:
- Parse memory dari output Gemini
- Inject memory ke system prompt
- Ringkas memory jika terlalu banyak

### Variabel penting

#### `CORE_CATEGORIES`
Daftar kategori utama memory:

```python
[
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
```

### Fungsi utama

#### `extract_memory_from_response(user_id, response_text)`
Mencari block:

```text
[MEMORY]
key: value
[/MEMORY]
```

Lalu:
- parse per baris
- ubah key jadi snake_case lowercase
- simpan ke DB via `upsert_memory`
- hapus block memory dari jawaban user-visible

Ada fallback parser jika format block tidak rapi.

Return:
- response bersih tanpa `[MEMORY]`

#### `format_memories_for_prompt(user_id)`
Mengambil semua memory user dan mengubah jadi konteks prompt.

Aturan:
- jika tidak ada memory → return string kosong
- jika <= 10 memory → tampilkan dalam bullet list
- jika > 10 → ringkas jadi paragraf hemat token

---

# 7.4 `app/tools.py`

File ini sekarang memegang 3 kelompok logic:

1. Tool DeFiLlama
2. Document reader
3. Document creator
4. Chunking utility

---

## Bagian A — DefiLlama Tool

### Konstanta
- `DEFILLAMA_BASE_URL = "https://api.llama.fi"`

### Fungsi

#### `get_tvl_growth(protocol_name: str) -> dict`
Async function.

Fungsi:
- fetch endpoint `https://api.llama.fi/protocol/{protocol_name.lower()}`
- ambil TVL sekarang
- cari TVL sekitar 30 hari lalu
- hitung growth %

Return dict:
- success:
  - `protocol`
  - `current_tvl`
  - `current_date`
  - `past_tvl`
  - `past_date`
  - `growth_percent`
- gagal:
  - `{"error": "..."}`
  
#### `format_tvl_result(result: dict) -> str`
Format hasil TVL agar jadi teks rapi untuk user.

Termasuk:
- formatting USD ke B / M / raw
- arrow hijau/merah berdasar growth

---

## Bagian B — Document Reader

### Konstanta penting

#### `CHUNK_SIZE = 8000`
Ukuran chunk dokumen panjang, dalam karakter.

#### `CHUNK_OVERLAP = 500`
Overlap antar chunk agar konteks tidak putus.

### Reader functions

#### `read_txt(file_path)`
- baca file teks
- fallback encoding `utf-8` lalu `latin-1`

#### `read_pdf(file_path)`
- pakai `PyPDF2.PdfReader`
- ekstrak teks semua halaman
- return string gabungan

#### `read_docx(file_path)`
- pakai `python-docx`
- baca paragraf
- baca tabel juga

#### `read_csv_file(file_path)`
- baca CSV
- dibatasi 100 baris

#### `read_json_file(file_path)`
- load JSON
- dump pretty string
- saat ini masih ada limit 5000 chars internal pada JSON

#### `read_xlsx(file_path)`
- pakai `openpyxl`
- baca semua sheet
- dibatasi 100 baris per sheet

### Mapping

#### `DOCUMENT_READERS`
Mapping ekstensi ke fungsi pembaca:

Support saat ini:
- `.txt`
- `.pdf`
- `.docx`
- `.csv`
- `.json`
- `.xlsx`
- `.xls`
- `.log`
- `.md`
- `.py`
- `.js`
- `.html`
- `.xml`
- `.yaml`
- `.yml`
- `.env`
- `.ini`
- `.cfg`
- `.sql`

#### `SUPPORTED_EXTENSIONS`
List dari semua key `DOCUMENT_READERS`

### Utility

#### `split_text_into_chunks(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)`
Pecah teks panjang menjadi beberapa chunk.

Logika:
- jika teks <= chunk_size → satu chunk
- jika lebih panjang → potong di newline terdekat
- jika tidak ada newline cocok → potong di `. `
- pakai overlap 500 karakter
- ada safety agar loop tidak macet

#### `extract_text_from_file(file_path)`
- deteksi extension
- panggil reader yang sesuai
- return `(text, error)`
- jika unsupported → return `(None, "error message")`
- jika kosong → return `(None, "Dokumen kosong...")`

Catatan:
- Tidak ada lagi global max chars limit di sini
- Dokumen panjang diproses lewat chunking di layer bot/gemini

---

## Bagian C — Document Creator

Dipakai oleh command `/pdf` dan `/docx`.

### Helper

#### `safe_text_for_pdf(text)`
Membersihkan karakter unicode tertentu agar aman untuk font default PDF (`latin-1`).

#### `parse_title_from_content(content)`
Mengambil judul dari baris pertama dengan prefix:

```text
# Judul
```

Return:
- `title`
- `body`

### Creator functions

#### `create_pdf_file(content, file_path)`
- pakai `fpdf2`
- buat PDF lokal
- format sederhana:
  - title center
  - timestamp
  - separator
  - heading/subheading/list/paragraph

Return:
- `title`

#### `create_docx_file(content, file_path)`
- pakai `python-docx`
- buat DOCX lokal
- title center
- timestamp abu-abu
- heading/list/paragraph

Return:
- `title`

---

# 7.5 `app/gemini.py`

Ini file inti AI logic.

## Import penting
- `from google import genai`
- `from google.genai import types`

## Client
- `client = genai.Client(api_key=GEMINI_API_KEY)`

---

## Prompt utama

### `BASE_SYSTEM_PROMPT`
Karakter bot:
- helpful
- ramah
- natural
- default bahasa Indonesia
- ringkas kecuali diminta detail
- hindari markdown aneh
- jujur kalau tidak punya internet/GPS live
- punya akses DefiLlama untuk TVL
- bisa membaca dokumen
- bisa membantu dari isi dokumen

### `MEMORY_EXTRACTION_PROMPT`
Instruksi ke model agar:
- ekstrak info personal user
- pakai `[MEMORY] ... [/MEMORY]`
- hanya jika benar-benar ada info baru
- boleh buat kategori baru
- key harus snake_case

---

## Tool declaration

### `TVL_TOOL`
Tool Gemini function calling untuk:

- name: `get_tvl_growth`
- parameter:
  - `protocol_name: string`

---

## Fungsi utama

### `build_system_prompt(user_id)`
Menggabungkan:
1. `BASE_SYSTEM_PROMPT`
2. memory context hasil `format_memories_for_prompt(user_id)` jika ada
3. `MEMORY_EXTRACTION_PROMPT`

Return:
- string system prompt final

---

### `get_response(user_id, user_message, recent_messages)`
Fungsi utama chat.

#### Input
- `user_id`
- `user_message`
- `recent_messages`: list `(role, message)`

#### Cara kerja
1. build system prompt
2. build `contents` dari recent_messages pakai `types.Content`
3. call Gemini
4. cek apakah ada `function_call`
5. jika tool dipanggil:
   - ambil `protocol_name`
   - execute `get_tvl_growth`
   - format hasil
   - saat ini masih ada logic Call 2, tetapi historis proyek menyebut fix stabil adalah bypass Call 2
   - agent berikutnya harus hati-hati di sini karena model ini sensitif terhadap `thought_signature`

#### Catatan sangat penting
Ada bug / constraint model:
- `gemini-3.1-flash-lite-preview` sempat error:
  - `"Function call is missing a thought_signature in functionCall parts"`

Solusi yang paling stabil sebelumnya:
- bypass call 2
- setelah tool dieksekusi, return hasil tool langsung tanpa kirim function response lagi ke Gemini

Namun isi `gemini.py` terakhir yang terlihat masih memiliki logic Call 2 dengan attempt menyalin `thought_signature`, plus fallback jika error. Ini area sensitif dan perlu diperlakukan hati-hati kalau diubah lagi.

#### Error handling
Menangani:
- quota / 429
- timeout
- auth error
- model not found
- thought_signature fallback

---

### `summarize_chunk(chunk_text, chunk_number, total_chunks, file_name)`
Dipakai untuk dokumen panjang.

#### Fungsi
- kirim 1 chunk ke Gemini
- minta ringkasan detail
- menjaga angka/nama/poin penting

#### Output
- summary text per chunk

---

### `process_long_document(user_id, chunks, file_name, user_caption, recent_messages)`
Dipakai untuk dokumen panjang.

#### Alur ideal saat ini
1. loop semua chunk
2. panggil `summarize_chunk()` per chunk
3. gabungkan hasil jadi `combined_summary`
4. bangun `final_prompt` berisi rangkuman semua bagian + instruksi user/caption
5. kirim ke Gemini untuk jawaban final

#### Catatan bug yang pernah terjadi
Sempat ada bug:
- final prompt tidak masuk ke recent_messages
- Gemini hanya melihat metadata dokumen panjang, bukan summary isi

Fix yang benar:
- simpan `final_prompt` ke DB sebagai message user
- ambil ulang `fresh_messages`
- baru panggil `get_response(...)`

Agent selanjutnya perlu memastikan implementasi final di file benar-benar mengikuti fix ini.

---

### `generate_document_content(user_id, instruction, recent_messages)`
Dipakai oleh `/pdf` dan `/docx`.

#### Fungsi
- ambil konteks dari sekitar 10 pesan terakhir
- buat prompt khusus pembuatan dokumen
- minta Gemini menulis konten terstruktur dengan format:

```text
# Judul
## Subbagian
### Subsubbagian
- bullet
paragraf biasa
```

#### Aturan prompt
- jangan pakai bold/italic markdown
- Bahasa Indonesia
- lengkap dan informatif
- minimal sekitar 500 kata

#### Return
- string content dokumen
- atau `None` jika gagal

---

### `analyze_image(user_id, image_bytes, caption, recent_messages, mime_type="image/jpeg")`
Dipakai untuk analisis gambar.

#### Input
- `user_id`
- `image_bytes`
- `caption`
- `recent_messages`
- `mime_type`

#### Default mime type
- `"image/jpeg"`

#### Cara kerja
- build system prompt
- buat `types.Part.from_bytes(...)`
- gabungkan dengan teks prompt/caption
- kirim ke Gemini
- return hasil analisis

#### Support nyata
- foto Telegram biasa
- file gambar sebagai document:
  - jpg
  - jpeg
  - png
  - webp
  - gif
  - bmp

---

# 7.6 `app/bot.py`

Ini entry point aplikasi Telegram bot.

## Import penting

Dari `app.gemini`:
- `get_response`
- `process_long_document`
- `generate_document_content`
- `analyze_image`

Dari `app.database`:
- `init_db`
- `save_message`
- `get_recent_messages`
- `get_all_memories`
- `delete_memory`
- `clear_history`

Dari `app.tools`:
- `extract_text_from_file`
- `split_text_into_chunks`
- `SUPPORTED_EXTENSIONS`
- `CHUNK_SIZE`
- `create_pdf_file`
- `create_docx_file`

---

## Konstanta lokal penting

### `IMAGE_EXTENSIONS`
```python
{".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
```

### `IMAGE_MIME_MAP`
```python
{
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}
```

---

## Handler yang ada

### `start(update, context)`
Reply salam pembuka.

---

### `handle_message(update, context)`
Flow chat biasa:
1. ambil `user_id`
2. ambil `user_message`
3. save ke DB
4. ambil recent 20 messages
5. typing action
6. panggil `get_response`
7. parse memory via `extract_memory_from_response`
8. save jawaban assistant
9. reply ke user

---

### `handle_photo(update, context)`
Untuk foto Telegram.

Flow:
1. ambil foto resolusi tertinggi `update.message.photo[-1]`
2. ambil caption jika ada
3. download as bytearray
4. simpan info "[User mengirim gambar]" ke conversations
5. ambil recent_messages
6. panggil `analyze_image(...)`
7. parse memory
8. simpan jawaban
9. reply ke user
10. jika >4096 chars, split reply

---

### `handle_document(update, context)`
Menangani:
- file gambar yang dikirim sebagai document
- dokumen teks/pdf/docx/dll

#### Flow bagian gambar
Jika extension termasuk `IMAGE_EXTENSIONS`:
1. download bytes
2. tentukan mime type dari `IMAGE_MIME_MAP`
3. simpan info ke DB
4. panggil `analyze_image(...)`
5. simpan dan reply

#### Flow bagian dokumen biasa
Jika extension termasuk `SUPPORTED_EXTENSIONS`:
1. download ke `/tmp/{user_id}_{file_name}`
2. ekstrak teks via `extract_text_from_file`
3. hapus file temp
4. jika teks <= `CHUNK_SIZE`
   - buat `user_message` berisi nama file, caption, isi dokumen
   - simpan ke DB
   - panggil `get_response(...)`
5. jika teks > `CHUNK_SIZE`
   - split via `split_text_into_chunks`
   - kirim pesan info progress ke user
   - simpan metadata dokumen panjang ke DB
   - ambil recent_messages
   - panggil `process_long_document(...)`
6. parse memory
7. simpan response assistant
8. reply ke user
9. split message jika >4096 chars

#### File size limit
- max 20 MB

---

### `create_document_handler(update, context, doc_type)`
Dipakai oleh `/pdf` dan `/docx`.

#### Parameter
- `doc_type`: `"pdf"` atau `"docx"`

#### Flow
1. cek `context.args`
2. gabungkan jadi `instruction`
3. kirim status "sedang membuat dokumen"
4. ambil recent_messages
5. panggil `generate_document_content(...)`
6. simpan file ke `/tmp/{user_id}_document.{doc_type}`
7. buat file via:
   - `create_pdf_file(...)`
   - atau `create_docx_file(...)`
8. sanitize judul jadi filename
9. kirim file ke user dengan caption judul
10. simpan log ke DB:
   - user: `/{doc_type} ...`
   - assistant: `[Dokumen PDF/DOCX dibuat: title]`
11. hapus file temp

---

### `pdf_command(update, context)`
Wrapper:
- panggil `create_document_handler(..., "pdf")`

### `docx_command(update, context)`
Wrapper:
- panggil `create_document_handler(..., "docx")`

---

### `memory_command(update, context)`
Menampilkan semua memories.

---

### `forget_command(update, context)`
Menghapus 1 memory key.

Format:
```text
/forget nama_kucing
```

---

### `clearmemory_command(update, context)`
Menghapus semua memories user.

Catatan:
- saat ini implementasi memakai direct SQL delete di dalam bot.py, bukan helper function di database.py
- ini bisa dirapikan nanti, tapi sekarang berfungsi

---

### `clearhistory_command(update, context)`
Menghapus semua conversation history user melalui `clear_history(user_id)`.

Efek:
- percakapan di-reset
- memory personal tetap ada

---

### `post_init(application)`
Dipakai untuk register command menu ke Telegram agar saat user mengetik `/`, daftar command muncul.

Command yang diregister:
- `/start`
- `/memory`
- `/forget`
- `/clearmemory`
- `/clearhistory`
- `/pdf`
- `/docx`

Catatan:
- jika nanti ada command baru, fungsi ini harus ikut diupdate

---

### `main()`
Flow:
1. `init_db()`
2. build `ApplicationBuilder`
3. set timeout
4. set `.post_init(post_init)`
5. register handlers
6. `run_polling()`

Urutan handler penting:
1. command handlers
2. `filters.PHOTO` → `handle_photo`
3. `filters.Document.ALL` → `handle_document`
4. `filters.TEXT & ~filters.COMMAND` → `handle_message`

Urutan ini penting agar foto/file tidak jatuh ke text handler.

---

## 8. Command yang Tersedia

Saat ini command aktif:

| Command | Fungsi |
|--------|--------|
| `/start` | Salam pembuka |
| `/memory` | Lihat semua memory |
| `/forget [key]` | Hapus 1 memory |
| `/clearmemory` | Hapus semua memory |
| `/clearhistory` | Hapus semua percakapan |
| `/pdf [instruksi]` | Generate file PDF |
| `/docx [instruksi]` | Generate file DOCX |

Semua command ini sudah dimunculkan di Telegram command menu.

---

## 9. Fitur yang Sudah Jadi

### Chat & Memory
- Telegram bot aktif
- polling aktif
- Gemini API terhubung
- recent history 20 pesan
- memory extraction dari output Gemini
- memory injection ke system prompt
- memory summary jika banyak
- `/memory`, `/forget`, `/clearmemory`

### History management
- `/clearhistory`

### Tool calling
- DefiLlama TVL growth

### Document understanding
- baca TXT
- PDF
- DOCX
- CSV
- JSON
- XLSX
- file teks umum
- dokumen panjang via chunking

### Document creation
- generate PDF
- generate DOCX

### Image understanding
- foto Telegram
- file gambar sebagai dokumen

### UX
- command menu Telegram muncul saat ketik `/`

---

## 10. Isu / Catatan Teknis Penting

## A. Thought Signature issue
Model `gemini-3.1-flash-lite-preview` bermasalah saat function calling multi-step.

Error historis:
```text
Function call is missing a thought_signature in functionCall parts
```

Solusi paling stabil yang pernah berhasil:
- bypass second call
- langsung return tool result formatted

Agent berikutnya jangan gegabah merombak tool-calling tanpa ingat issue ini.

---

## B. Dokumen panjang
Poin penting:
- Python tidak merangkum isi, Python hanya memecah chunk
- Gemini yang merangkum tiap chunk
- lalu Gemini lagi yang jawab final

Fix penting:
- final summary harus benar-benar masuk ke prompt yang dibaca Gemini

---

## C. JSON reader masih membatasi 5000 chars
Di `read_json_file`, masih ada limit internal 5000 karakter.
Kalau nanti ingin full-chunking juga untuk JSON besar, ini perlu dirapikan.

---

## D. `/clearmemory` belum dipindah ke database helper
Masih delete SQL langsung di bot.py. Secara fungsi aman, tapi belum se-rapi `/clearhistory`.

---

## E. Image support bergantung model
Saat ini diasumsikan model support multimodal untuk image input. Implementasi sudah terbukti berjalan dari hasil test user.

---

## 11. Requirements yang Dipakai

`requirements.txt` seharusnya minimal memuat:

```txt
python-telegram-bot
google-genai
python-dotenv
httpx
PyPDF2
python-docx
openpyxl
fpdf2
```

Kalau ada error module not found, cek apakah library sudah benar-benar ada di file ini lalu redeploy Railway.

---

## 12. Alur Sistem per Jenis Input

## A. Chat biasa
```text
User kirim teks
→ save_message(user)
→ get_recent_messages(20)
→ get_response()
→ extract_memory_from_response()
→ save_message(assistant)
→ reply
```

## B. Dokumen pendek
```text
User kirim dokumen
→ download tmp
→ extract_text_from_file()
→ save_message(user, isi dokumen)
→ get_recent_messages(20)
→ get_response()
→ extract_memory_from_response()
→ save_message(assistant)
→ reply
```

## C. Dokumen panjang
```text
User kirim dokumen panjang
→ download tmp
→ extract_text_from_file()
→ split_text_into_chunks()
→ summarize_chunk() x N
→ gabung summaries
→ final prompt
→ get_response()
→ extract_memory_from_response()
→ save_message(assistant)
→ reply
```

## D. Gambar
```text
User kirim foto / file gambar
→ download bytes
→ analyze_image()
→ extract_memory_from_response()
→ save_message(assistant)
→ reply
```

## E. Generate PDF/DOCX
```text
User kirim /pdf atau /docx + instruksi
→ get_recent_messages()
→ generate_document_content()
→ create_pdf_file() / create_docx_file()
→ kirim file ke user
→ save log ke DB
```

---

## 13. State Proyek Saat Ini

Sudah jadi:
- chat
- memory
- clear memory
- clear history
- Defi TVL tool
- baca dokumen
- chunking dokumen panjang
- generate PDF/DOCX
- analisis gambar
- command menu Telegram

Belum jadi:
- web search
- voice note / speech-to-text
- semantic retrieval / vector DB
- rate limiting khusus
- image generation
- scheduled cleanup
- multi-model fallback
- clear all helper yang lebih rapi di database layer
- tool DeFi tambahan selain TVL growth

---

## 14. Prinsip yang Harus Dipertahankan oleh AI Agent Selanjutnya

1. Jangan rusak alur 1 API call untuk chat biasa
2. Gunakan SQLite dan local logic sebisa mungkin
3. Jangan menambah fitur berat tanpa mempertimbangkan quota
4. Bahasa default tetap Indonesia
5. Jangan langsung rewrite besar-besaran
6. Selalu perhatikan kompatibilitas dengan Railway
7. Hati-hati mengubah tool calling Gemini karena ada riwayat bug `thought_signature`
8. Kalau menambah command baru, update juga Telegram command menu di `post_init`
9. Kalau menambah file parsing baru, pikirkan:
   - ukuran file
   - ukuran token
   - apakah perlu chunking
10. Setiap perubahan lebih aman dilakukan incremental dan diuji satu per satu

---

## 15. Rekomendasi Immediate Next Step

Kalau agent berikutnya melanjutkan, urutan aman yang direkomendasikan:

1. Audit final code di `gemini.py` untuk memastikan `process_long_document()` sudah memakai fix final prompt yang benar
2. Rapikan `/clearmemory` ke helper database
3. Tambah `/help`
4. Besok lanjut web search dengan desain hemat quota
5. Baru setelah itu pertimbangkan voice note atau tools lain

---

Kalau kamu mau, saya juga bisa buatkan versi kedua dari summary ini yang lebih "operasional", yaitu format:
- file per file
- function per function
- checklist perubahan terakhir
- known bugs
- next task recommendation

Versi itu biasanya lebih enak langsung ditempel ke agent AI berikutnya.
