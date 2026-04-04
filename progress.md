## Summary diskusi kita

### Tujuan proyek
Membangun **AI assistant personal di Telegram** berbasis **Gemini API**, dengan fokus:
- hemat quota
- bisa menyimpan percakapan
- punya memory bertahap
- makin lama makin kontekstual / “pintar”

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

Kurang lebih sekarang strukturnya seperti ini:

```bash
telegram-ai-assistant/
├── .env
├── assistant.db
├── app/
│   ├── bot.py
│   ├── config.py
│   ├── gemini.py
│   └── database.py
└── venv/
```

Catatan:
- `assistant.db` muncul di root project
- `database.py` sekarang harus berada di dalam folder `app/` agar konsisten dengan import package

---

# 4. Perubahan penting yang sudah dilakukan

## 4.1 SQLite berhasil ditambahkan
Tujuan:
- menyimpan riwayat chat permanen
- agar data tidak hilang saat restart

### Tabel yang sudah dibuat
#### `conversations`
Kolom:
- `id`
- `user_id`
- `role`
- `message`
- `created_at`

SQL dasarnya:

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4.2 File `app/database.py`
Fungsi yang sudah dipakai:

### `DB_NAME`
```python
DB_NAME = "assistant.db"
```

### `get_connection()`
Untuk buka koneksi SQLite

### `init_db()`
Untuk membuat tabel `conversations`

### `save_message(user_id, role, message)`
Untuk menyimpan chat user dan assistant

### `get_recent_messages(user_id, limit=10)`
Untuk mengambil beberapa pesan terakhir dari DB

---

# 5. Integrasi ke bot Telegram

## 5.1 Import di `app/bot.py`
Saat ini bot mengimpor:

```python
from app.config import TELEGRAM_BOT_TOKEN
from app.gemini import get_response
from app.database import init_db, save_message, get_recent_messages
```

---

## 5.2 Handler yang sekarang
Fungsi `handle_message()` sekarang konsepnya:

1. ambil `user_id`
2. ambil `user_message`
3. simpan pesan user ke DB
4. ambil `recent_messages` dari DB
5. panggil Gemini dengan history itu
6. simpan jawaban assistant ke DB
7. kirim jawaban ke Telegram

Contoh alur:

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

---

## 5.3 `main()` di `app/bot.py`
`init_db()` sudah dipanggil sebelum bot start.

Builder Telegram saat ini memakai timeout yang lebih besar:

```python
Application.builder() \
    .token(TELEGRAM_BOT_TOKEN) \
    .connect_timeout(30) \
    .read_timeout(30) \
    .write_timeout(30) \
    .build()
```

Ini ditambahkan karena sebelumnya sempat ada masalah timeout polling Telegram.

---

# 6. Evolusi memory

## Tahap awal
Awalnya memory memakai **RAM** di `app/gemini.py`:
- ada `chat_histories = {}`
- ada `MAX_HISTORY = 10`
- history disimpan per user di memori Python

Kelemahannya:
- kalau bot restart, context hilang

---

## Tahap sekarang
Memory short-term sekarang sudah dipindahkan ke **SQLite-backed recent history**:
- pesan user disimpan ke DB
- jawaban assistant disimpan ke DB
- saat ada pesan baru, bot ambil `recent_messages` dari SQLite
- history itu dikirim ke Gemini

Jadi:
- restart bot tidak lagi menghapus konteks sepenuhnya
- source of truth sekarang adalah database

---

# 7. `app/gemini.py` yang sekarang

## Perubahan utama
### Dihapus
- `chat_histories = {}`
- `MAX_HISTORY = 10`

### Diganti dengan pendekatan:
- `build_contents_from_history(recent_messages)`
- `get_response(user_id, user_message, recent_messages)`

---

## Variabel/config penting yang dipakai di `gemini.py`

### `client`
```python
client = genai.Client(api_key=GEMINI_API_KEY)
```

### `SYSTEM_PROMPT`
Sudah beberapa kali diarahkan agar:
- Bahasa Indonesia default
- natural
- tidak kaku
- ringkas
- cocok untuk Telegram
- hindari markdown berlebihan
- jujur kalau user meminta data real-time / lokasi aktual

Arah prompt yang disepakati:

```python
SYSTEM_PROMPT = """Kamu adalah asisten AI personal yang helpful dan ramah.
Jawab selalu dalam Bahasa Indonesia kecuali diminta bahasa lain.
Jawab dengan natural seperti teman ngobrol, tidak kaku.
Usahakan jawaban ringkas, jelas, dan tidak terlalu panjang kecuali diminta detail.
Kalau memberi daftar, batasi 3-5 poin saja.
Gunakan format teks biasa yang rapi untuk Telegram.
Hindari markdown seperti **bold**, *italic*, atau format aneh lainnya.
Kalau user meminta informasi real-time, lokasi terdekat, data terbaru, atau hasil pencarian aktual, jelaskan dengan jujur bahwa kamu tidak sedang mengakses internet, GPS, atau Google Maps secara langsung. Berikan saran umum saja."""
```

### `max_output_tokens`
Sempat ada jawaban terkesan kepotong, lalu dinaikkan dari:
```python
1024
```
menjadi sekitar:
```python
1500
```

---

## Fungsi penting
### `build_contents_from_history(recent_messages)`
Mengubah hasil SQLite seperti:
```python
[("user", "..."), ("assistant", "...")]
```
menjadi `types.Content(...)` yang bisa dipakai Gemini.

### `get_response(user_id, user_message, recent_messages)`
Saat ini dipakai untuk:
- membangun `contents` dari `recent_messages`
- memanggil `client.aio.models.generate_content(...)`
- mengembalikan `response.text`

Catatan:
- parameter `user_id` dan `user_message` saat ini masih ada, walaupun yang benar-benar dipakai utama adalah `recent_messages`
- ini boleh dirapikan nanti, tapi belum wajib

---

# 8. Model Gemini yang dipakai

## Model lama
Sebelumnya dipakai:
```python
gemini-2.5-flash
```

Limitnya:
- RPM 5
- TPM 250K
- RPD 20

Ini terlalu sempit untuk penggunaan lebih nyaman.

---

## Model baru yang ditemukan
Setelah dicek lewat API / dashboard, ditemukan model dengan limit lebih besar:

```python
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
```

Limitnya:
- **RPM 15**
- **TPM 250K**
- **RPD 500**

Ini dianggap jauh lebih cocok untuk bot personal ini.

### Kesimpulan tentang model
- model baru sangat layak jadi default
- karena bottleneck terbesar sebelumnya adalah **RPD**
- dengan `RPD 500`, testing dan penggunaan harian jadi jauh lebih longgar

Catatan:
- model ini masih ada label `preview`
- jadi bisa ada perubahan perilaku / stabilitas di masa depan

---

# 9. Validasi hasil yang sudah terjadi

## SQLite
Sudah berhasil:
- file `assistant.db` muncul
- data masuk ke tabel `conversations`
- query manual via `sqlite3` berhasil

Contoh query yang dipakai:
```sql
SELECT id, user_id, role, message, created_at FROM conversations;
```

---

## Recent history
Fungsi `get_recent_messages()` sudah dites dan berhasil output seperti:

```python
[
    ('user', 'ayo kita tes memori: sekarang kita ada di jawa timur'),
    ('assistant', '...'),
    ('user', 'halo, ini coba memori')
]
```

Ini menandakan:
- data terbaca dari DB
- urutan sudah benar (lama ke baru)

---

## Context continuity
Sudah dites dan berhasil:
- bot tetap nyambung konteks dari percakapan sebelumnya
- setelah pindah ke SQLite-backed history, konteks tetap jalan
- model baru juga bisa melanjutkan konteks dengan cukup baik

---

# 10. Insight penting dari testing chat

Saat user bertanya:
- tentang lokasi
- cafe terdekat
- rekomendasi real-time

ditemukan bahwa model bisa terdengar meyakinkan, tapi:
- **sebenarnya tidak melakukan pencarian internet / maps real-time**
- jadi perlu dibatasi lewat prompt agar tidak misleading

Karena itu prompt diarahkan agar model:
- jujur saat tidak punya akses internet / GPS / Google Maps
- hanya memberi saran umum jika tidak ada tool pencarian real-time

---

# 11. Diskusi tentang multi-model / fallback

User sempat bertanya apakah bisa pakai lebih dari satu model:
- kalau model A quota habis, pindah ke model B

## Jawaban
- **bisa dibuat**
- pola umumnya:
  1. coba model utama
  2. kalau quota habis, coba model cadangan
  3. kalau semua gagal, kirim error ke user

## Tapi keputusan saat ini
**belum perlu diimplementasikan dulu**, karena:
- model baru `gemini-3.1-flash-lite-preview` sudah punya `RPD 500`
- untuk personal bot, kemungkinan ini sudah cukup
- fallback model bisa ditambahkan nanti jika benar-benar diperlukan

---

# 12. Cara cek model available dari terminal

Sudah dibahas cara cek model yang tersedia untuk API key dengan script Python kecil.

Contoh:

```python
from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

for model in client.models.list():
    print(model.name)
```

Ini dipakai untuk memastikan model benar-benar tersedia di API, bukan hanya terlihat di dashboard.

---

# 13. Parameter / variable penting yang sudah dipakai

## Di `app/config.py`
```python
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
```

---

## Di `app/database.py`
```python
DB_NAME = "assistant.db"
```

Fungsi:
- `get_connection()`
- `init_db()`
- `save_message(user_id, role, message)`
- `get_recent_messages(user_id, limit=10)`

Parameter penting:
- `limit=10` untuk recent history

---

## Di `app/gemini.py`
Variabel penting:
- `client`
- `SYSTEM_PROMPT`

Parameter generation penting:
- `temperature=0.7`
- `max_output_tokens=1500` (arah final setelah sempat 1024)

Fungsi penting:
- `build_contents_from_history(recent_messages)`
- `get_response(user_id, user_message, recent_messages)`

---

## Di `app/bot.py`
Fungsi penting:
- `start(...)`
- `handle_message(...)`
- `main()`

Timeout builder:
- `.connect_timeout(30)`
- `.read_timeout(30)`
- `.write_timeout(30)`

---

# 14. Status proyek saat ini

## Sudah jadi
- Telegram bot aktif
- polling jalan
- Gemini API terhubung
- model baru dengan quota lebih besar sudah dipakai
- chat user dan assistant tersimpan di SQLite
- recent history diambil dari DB
- context percakapan sudah jalan setelah restart
- output sudah lebih aman dari masalah “kepotong”

## Belum jadi
- tabel `memories`
- memory penting vs tidak penting
- rule-based extraction
- long-term memory injection ke prompt
- semantic search / vector retrieval
- fallback multi-model
- deploy VPS production

---

# 15. Rekomendasi next step untuk agent berikutnya

## Next step terbaik
### **Buat tabel `memories`**
Tujuannya:
- simpan fakta penting jangka panjang tentang user / proyek
- tidak tergantung hanya pada recent history

## Rencana implementasi berikutnya
Urutan yang disarankan:

1. desain tabel `memories`
2. buat fungsi insert / upsert memory
3. buat rule-based extraction sederhana
4. inject memory penting ke prompt bersama recent history

---

## Contoh memory penting yang nanti perlu disimpan
Dari diskusi ini sendiri, contoh memory penting user:
- default bahasa: **Bahasa Indonesia**
- kalau diminta baru bahasa Inggris
- gaya diskusi: **pelan-pelan**
- jangan langsung full code besar
- user sedang membangun **AI assistant Telegram berbasis Gemini**
- fokus ke **hemat quota / hemat biaya / efisien**
- bot bersifat **personal / 1 user**

---

Kalau besok agent baru melanjutkan, patokan paling pentingnya adalah:

## Prinsip arsitektur yang harus dijaga
- tetap hemat request
- sebisa mungkin tetap **1 API call per user message**
- gunakan local logic / SQLite sebanyak mungkin
- jangan buru-buru menambah fitur yang boros API
- default bahasa Indonesia
- pembahasan pelan-pelan dan praktis
