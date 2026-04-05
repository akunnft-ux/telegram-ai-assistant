import httpx
from datetime import datetime, timedelta

CHUNK_SIZE = 8000  # karakter per chunk
CHUNK_OVERLAP = 500  # overlap antar chunk biar konteks tidak putus

DEFILLAMA_BASE_URL = "https://api.llama.fi"


async def get_tvl_growth(protocol_name: str) -> dict:
    url = f"{DEFILLAMA_BASE_URL}/protocol/{protocol_name.lower()}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)

            if response.status_code == 404:
                return {"error": f"Protokol '{protocol_name}' tidak ditemukan di DefiLlama."}

            if response.status_code != 200:
                return {"error": f"DefiLlama API error: {response.status_code}"}

            data = response.json()

            tvl_data = data.get("tvl", [])

            if not tvl_data:
                return {"error": f"Data TVL untuk '{protocol_name}' tidak tersedia."}

            # Ambil TVL sekarang (index terakhir)
            current = tvl_data[-1]
            current_tvl = current["totalLiquidityUSD"]
            current_date = datetime.fromtimestamp(current["date"]).strftime("%d %b %Y")

            # Cari TVL 30 hari lalu
            target_date = datetime.now() - timedelta(days=30)
            past_entry = None

            for entry in reversed(tvl_data):
                entry_date = datetime.fromtimestamp(entry["date"])
                if entry_date <= target_date:
                    past_entry = entry
                    break

            if not past_entry:
                return {"error": f"Data 30 hari lalu untuk '{protocol_name}' tidak tersedia."}

            past_tvl = past_entry["totalLiquidityUSD"]
            past_date = datetime.fromtimestamp(past_entry["date"]).strftime("%d %b %Y")

            # Hitung growth
            if past_tvl == 0:
                return {"error": "TVL 30 hari lalu adalah 0, tidak bisa hitung growth."}

            growth = ((current_tvl - past_tvl) / past_tvl) * 100

            return {
                "protocol": data.get("name", protocol_name),
                "current_tvl": current_tvl,
                "current_date": current_date,
                "past_tvl": past_tvl,
                "past_date": past_date,
                "growth_percent": round(growth, 2)
            }

    except httpx.TimeoutException:
        return {"error": "DefiLlama API timeout. Coba lagi."}

    except Exception as e:
        return {"error": f"Error: {str(e)}"}


def format_tvl_result(result: dict) -> str:
    if "error" in result:
        return result["error"]

    growth = result["growth_percent"]
    arrow = "🟢 +" if growth >= 0 else "🔴 "

    current = result["current_tvl"]
    past = result["past_tvl"]

    def format_usd(value):
        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"
        elif value >= 1_000_000:
            return f"${value / 1_000_000:.2f}M"
        else:
            return f"${value:,.0f}"

    return (
        f"TVL {result['protocol']}:\n"
        f"- Sekarang ({result['current_date']}): {format_usd(current)}\n"
        f"- 30 hari lalu ({result['past_date']}): {format_usd(past)}\n"
        f"- Growth: {arrow}{growth}%"
    )


# ============================================
# DOCUMENT READER TOOLS
# ============================================

import os
import csv
import json


def read_txt(file_path):
    """Baca file .txt"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as f:
            return f.read()


def read_pdf(file_path):
    """Baca file .pdf"""
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(file_path)
        texts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                texts.append(text)

        return "\n".join(texts) if texts else "[PDF kosong atau tidak bisa dibaca]"
    except Exception as e:
        return f"[Error baca PDF: {e}]"


def read_docx(file_path):
    """Baca file .docx"""
    try:
        from docx import Document

        doc = Document(file_path)
        texts = []
        for para in doc.paragraphs:
            if para.text.strip():
                texts.append(para.text)

        # Baca juga tabel kalau ada
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells)
                if row_text.strip():
                    texts.append(row_text)

        return "\n".join(texts) if texts else "[DOCX kosong]"
    except Exception as e:
        return f"[Error baca DOCX: {e}]"


def read_csv_file(file_path):
    """Baca file .csv"""
    try:
        rows = []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i >= 100:  # Batasi 100 baris biar tidak boros token
                    rows.append(f"... (total baris dipotong di 100)")
                    break
                rows.append(" | ".join(row))

        return "\n".join(rows) if rows else "[CSV kosong]"
    except Exception as e:
        return f"[Error baca CSV: {e}]"


def read_json_file(file_path):
    """Baca file .json"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        text = json.dumps(data, indent=2, ensure_ascii=False)

        # Batasi panjang
        if len(text) > 5000:
            text = text[:5000] + "\n... (dipotong, file terlalu panjang)"

        return text
    except Exception as e:
        return f"[Error baca JSON: {e}]"


def read_xlsx(file_path):
    """Baca file .xlsx"""
    try:
        from openpyxl import load_workbook

        wb = load_workbook(file_path, read_only=True)
        texts = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            texts.append(f"--- Sheet: {sheet_name} ---")

            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= 100:  # Batasi 100 baris per sheet
                    texts.append("... (dipotong di 100 baris)")
                    break
                row_text = " | ".join(str(cell) if cell is not None else "" for cell in row)
                if row_text.strip():
                    texts.append(row_text)

        wb.close()
        return "\n".join(texts) if texts else "[XLSX kosong]"
    except Exception as e:
        return f"[Error baca XLSX: {e}]"


# Mapping ekstensi ke fungsi
DOCUMENT_READERS = {
    ".txt": read_txt,
    ".pdf": read_pdf,
    ".docx": read_docx,
    ".csv": read_csv_file,
    ".json": read_json_file,
    ".xlsx": read_xlsx,
    ".xls": read_xlsx,
    ".log": read_txt,
    ".md": read_txt,
    ".py": read_txt,
    ".js": read_txt,
    ".html": read_txt,
    ".xml": read_txt,
    ".yaml": read_txt,
    ".yml": read_txt,
    ".env": read_txt,
    ".ini": read_txt,
    ".cfg": read_txt,
    ".sql": read_txt,
}

# Ekstensi yang didukung
SUPPORTED_EXTENSIONS = list(DOCUMENT_READERS.keys())


# ============================================
# DOCUMENT CHUNKING
# ============================================


def split_text_into_chunks(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Pecah teks panjang jadi chunks dengan overlap"""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Coba potong di akhir paragraf atau kalimat
        if end < len(text):
            # Cari newline terdekat dari posisi end
            newline_pos = text.rfind("\n", start + chunk_size - 1000, end)
            if newline_pos > start:
                end = newline_pos + 1
            else:
                # Cari titik terdekat
                dot_pos = text.rfind(". ", start + chunk_size - 1000, end)
                if dot_pos > start:
                    end = dot_pos + 2

        chunks.append(text[start:end].strip())

        # Mulai chunk berikutnya dengan overlap
        start = end - overlap
        if start < 0:
            start = 0

        # Safety: kalau start tidak maju, paksa maju
        if start <= (end - chunk_size):
            start = end

    return chunks


def extract_text_from_file(file_path):
    """Ekstrak teks dari file berdasarkan ekstensi — TANPA batasan karakter"""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext not in DOCUMENT_READERS:
        return None, f"Format {ext} belum didukung. Format yang didukung: {', '.join(SUPPORTED_EXTENSIONS)}"

    reader = DOCUMENT_READERS[ext]
    text = reader(file_path)

    if not text or not text.strip():
        return None, "Dokumen kosong atau tidak bisa dibaca."

    return text, None
