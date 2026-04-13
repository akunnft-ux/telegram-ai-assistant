
## 1. `README.md`

```markdown
# 🤖 Telegram AI Assistant

A feature-rich personal AI assistant for Telegram powered by Google Gemma 4. Capable of intelligent conversations, real-time web search, crypto market analysis, document processing, image analysis, and persistent memory.

Built with Python, SQLite, and deployed on Railway.

---

## ✨ Features

### 💬 Smart Conversational AI
- Natural, context-aware conversations
- Maintains last 20 messages for continuity
- Automatic web search when real-time information is needed
- Persistent memory system — remembers personal details about the user
- Default language: Bahasa Indonesia (responds in other languages on request)

### 🔍 Web Search
- **Auto-detect**: Bot automatically searches the internet when it determines fresh information is required
- **Manual**: Use `/search [query]` for direct web searches
- Multi-query engine with text + news search via DuckDuckGo
- Intelligent relevancy scoring to surface the best results
- Automatic query variation generation for better coverage

### 📊 Crypto Market Tools
- Global market overview with market cap, volume, and dominance data
- Trending coins from CoinGecko
- Top gainers and losers (24h)
- Fear & Greed Index with historical comparison
- DeFi protocol TVL and 30-day growth (DefiLlama)
- Detailed coin analysis with price, volume, ATH, and supply data
- AI-generated Farcaster post drafts based on market data
- DEX trending tokens from DexScreener

### 📄 Document Processing
- **Read**: PDF, DOCX, TXT, CSV, XLSX, JSON, and 10+ additional formats
- **Long documents**: Automatic chunking with per-chunk summarization
- **Create**: Generate structured PDF and DOCX files from natural language instructions
- Supports captions/instructions when sending documents

### 🖼️ Image Analysis
- Analyze photos sent directly in chat
- Supports images sent as file attachments
- Formats: JPG, JPEG, PNG, WEBP, GIF, BMP
- Describe, explain, or answer questions about image content

### 🧠 Persistent Memory
- Automatically extracts personal information from conversations
- Injects stored memories into AI context for personalized responses
- Full CRUD: view, delete individual keys, or clear all memories
- Memories persist across sessions and history clears

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Bot Framework | python-telegram-bot 21.x |
| AI Model | Google Gemma 4 (gemma-4-26b-a4b-it) |
| AI SDK | google-genai |
| Database | SQLite |
| Web Search | ddgs (DuckDuckGo Search) |
| Crypto Data | CoinGecko API, DefiLlama API, Alternative.me, DexScreener |
| Document I/O | PyPDF2, python-docx, openpyxl, fpdf2 |
| HTTP Client | httpx |
| Deployment | Railway |
| Language | Python 3.11+ |

---

## 📁 Project Structure

```
telegram-ai-assistant/
├── .env                  # Environment variables (not committed)
├── .env.example          # Template for environment setup
├── .gitignore
├── LICENSE
├── README.md
├── CHANGELOG.md
├── requirements.txt
├── app/
│   ├── bot.py            # Telegram handlers, commands, entry point
│   ├── config.py         # Configuration loading & constants
│   ├── gemini.py         # AI logic, prompts, search flow, image analysis
│   ├── database.py       # SQLite connection & CRUD operations
│   ├── memory.py         # Memory extraction, formatting & injection
│   └── tools.py          # Web search, crypto APIs, document R/W, chunking
└── data/
    └── assistant.db      # SQLite database (auto-created at runtime)
```

---

## 📋 Commands

### General
| Command | Description |
|---------|-------------|
| `/start` | Start a conversation |
| `/help` | Show all available commands |
| `/search [query]` | Search the internet for information |

### Crypto
| Command | Description |
|---------|-------------|
| `/daily_pick` | AI picks the most interesting crypto today + Farcaster draft |
| `/market` | Global crypto market overview + Fear & Greed |
| `/trending` | Trending coins from CoinGecko |
| `/movers` | Top 5 gainers & losers (24h) |
| `/fear` | Fear & Greed Index (today, yesterday, 7d ago) |
| `/tvl [protocol]` | DeFi protocol TVL + 30-day growth |
| `/analyze [coin]` | Detailed coin analysis + Farcaster post draft |

### Documents
| Command | Description |
|---------|-------------|
| `/pdf [instruction]` | Generate a structured PDF document |
| `/docx [instruction]` | Generate a structured DOCX document |

### Memory & History
| Command | Description |
|---------|-------------|
| `/memory` | View all stored memories |
| `/forget [key]` | Delete a specific memory |
| `/clearmemory` | Delete all memories |
| `/clearhistory` | Clear all conversation history (memories preserved) |

### No-Command Features
| Action | Result |
|--------|--------|
| Send a photo | Bot analyzes and describes the image |
| Send a document | Bot reads, parses, and summarizes the content |
| Ask anything | Bot responds; auto-searches if fresh info is needed |

---

## 🚀 Setup

### Prerequisites
- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Google AI API Key (with Gemma 4 access)
- CoinGecko API Key (free demo tier — optional but recommended)

### Local Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/telegram-ai-assistant.git
cd telegram-ai-assistant

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your actual API keys

# Run the bot
python -m app.bot
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `GEMINI_API_KEY` | Yes | Google AI API key for Gemma 4 |
| `COINGECKO_API_KEY` | No | CoinGecko demo API key (improves rate limits) |

---

## ☁️ Deployment (Railway)

1. Push your code to a GitHub repository
2. Create a new project on [Railway](https://railway.app)
3. Connect your GitHub repository
4. Set environment variables in Railway dashboard
5. Add a persistent volume mounted at `/data`
6. Railway automatically deploys on every push to `main`

### Railway Configuration
- **Build**: Auto-detected (Python)
- **Start Command**: `python -m app.bot`
- **Volume Mount**: `/data` (for SQLite persistence)

---

## 📊 API Usage & Quota

Designed to minimize API calls. Most interactions use only 1 call.

| Action | Gemini API Calls | External API Calls |
|--------|-----------------|-------------------|
| Regular chat | 1 | 0 |
| Chat with auto web search | 2 | 1 (DDG) |
| `/search` (manual) | 1 | 1 (DDG) |
| Short document | 1 | 0 |
| Long document (N chunks) | N + 1 | 0 |
| Image analysis | 1 | 0 |
| Generate PDF/DOCX | 1 | 0 |
| `/daily_pick` | 1 | 5 (crypto APIs) |
| `/analyze [coin]` | 1 | 1 (CoinGecko) |
| `/market` | 0 | 2 (CoinGecko + F&G) |
| `/trending` | 0 | 1 (CoinGecko) |
| `/movers` | 0 | 1 (CoinGecko) |
| `/fear` | 0 | 1 (Alternative.me) |
| `/tvl [protocol]` | 0 | 1 (DefiLlama) |

---

## 🏗️ Architecture

### Request Flow — Regular Chat
```
User sends message
→ Save to SQLite
→ Load last 20 messages
→ Send to Gemma 4 (1 API call)
→ Extract memory if present
→ Save response to SQLite
→ Reply to user
```

### Request Flow — Auto Web Search
```
User sends message
→ Gemma 4 responds with [SEARCH]query[/SEARCH] tag
→ Bot executes DuckDuckGo search locally (text + news)
→ Results ranked by relevancy
→ Send results + original question to Gemma 4 (2nd API call)
→ Reply with informed answer + sources
```

### Request Flow — Long Document
```
User sends large document
→ Extract text from file
→ Split into chunks (8000 chars each, 500 overlap)
→ Summarize each chunk via Gemma 4 (N API calls)
→ Combine summaries + user instruction
→ Final response via Gemma 4 (1 API call)
→ Reply to user
```

---

## 🗄️ Database Schema

### Table: `conversations`
```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,           -- 'user' or 'assistant'
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: `memories`
```sql
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,            -- snake_case identifier
    value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, key)
);
```

---

## ⚠️ Known Limitations

| Issue | Detail |
|-------|--------|
| Gemma 4 Thinking Mode | Cannot be disabled; handled by `extract_full_text()` which prioritizes text parts over thinking parts |
| `thought_signature` Bug | Multi-step function calling may fail; bypassed with fallback logic |
| DuckDuckGo Reliability | Free search — occasionally returns irrelevant results; mitigated by multi-query + news search |
| JSON Reader Limit | JSON files truncated at 5000 characters (chunking not yet applied) |
| Single User Design | Designed for personal use with one user; no auth/rate-limiting |

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Google Gemma 4](https://ai.google.dev/) — AI model
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — Telegram framework
- [DuckDuckGo](https://duckduckgo.com/) — Web search
- [CoinGecko](https://www.coingecko.com/) — Crypto market data
- [DefiLlama](https://defillama.com/) — DeFi TVL data
- [DexScreener](https://dexscreener.com/) — DEX trending data
- [Railway](https://railway.app/) — Cloud deployment
```

---

## 2. `.env.example`

```env
# Telegram Bot Token (obtain from @BotFather on Telegram)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Google AI API Key (for Gemma 4 model access)
GEMINI_API_KEY=your_gemini_api_key_here

# CoinGecko Demo API Key (free tier, optional but recommended for better rate limits)
COINGECKO_API_KEY=your_coingecko_api_key_here
```

---

## 3. `.gitignore`

```gitignore
# Python bytecode
__pycache__/
*.py[cod]
*$py.class
*.so
*.egg
*.egg-info/
dist/
build/
eggs/
*.whl

# Virtual environments
venv/
env/
.venv/
.env

# IDE / Editor
.vscode/
.idea/
*.swp
*.swo
*~
.project
.settings/

# OS files
.DS_Store
Thumbs.db
desktop.ini

# Database
*.db
data/

# Temporary files
/tmp/
*.tmp
*.bak

# Logs
*.log

# Archives
*.tar.gz
*.zip
*.rar
```

---

## 4. `LICENSE`

```
MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 5. `CHANGELOG.md`

```markdown
# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [1.5.0] - 2025-07-xx

### Added
- Web search feature with auto-detection and manual `/search` command
- DuckDuckGo text + news combined search
- Multi-query variation engine for improved search accuracy
- Relevancy scoring system for search result ranking
- `/help` command displaying all available commands with examples
- Search instruction integrated into system prompt

### Changed
- Migrated from `duckduckgo-search` to `ddgs` package
- Chat handler now uses `get_response_with_search()` for automatic web search
- System prompt updated with `SEARCH_INSTRUCTION` block
- Search region changed from `id-id` to `wt-wt` for global/neutral results

---

## [1.4.0] - 2025-07-xx

### Added
- Full crypto market toolkit
  - `/market` — Global market overview (CoinGecko)
  - `/trending` — Trending coins
  - `/movers` — Top 5 gainers & losers (24h)
  - `/fear` — Fear & Greed Index with 1d and 7d comparison
  - `/analyze [coin]` — Detailed coin analysis + Farcaster post draft
  - `/daily_pick` — AI-selected daily crypto pick + Farcaster post
- CoinGecko API integration with demo API key support
- DexScreener trending tokens integration
- Fear & Greed Index from Alternative.me
- Farcaster post generator with critical analysis rules
- Anti-shill analysis logic (wash trading detection, ATH distance warnings, pump signals)

---

## [1.3.0] - 2025-07-xx

### Added
- Image analysis for Telegram photos and image file attachments
- Support for JPG, JPEG, PNG, WEBP, GIF, BMP formats
- MIME type detection for image documents
- Document creation commands: `/pdf` and `/docx`
- Structured content generation with headings, lists, and paragraphs
- PDF generation via fpdf2 with clean formatting
- DOCX generation via python-docx with styled output

---

## [1.2.0] - 2025-07-xx

### Added
- Document reading support for 20+ file formats
- Supported formats: PDF, DOCX, TXT, CSV, XLSX, XLS, JSON, LOG, MD, PY, JS, HTML, XML, YAML, YML, ENV, INI, CFG, SQL
- Automatic long document chunking (8000 chars per chunk, 500 char overlap)
- Per-chunk summarization with Gemma 4
- Combined summary + final response flow for long documents
- File size limit: 20MB

### Fixed
- Long document final prompt now correctly saved to database and included in context
- Fresh messages fetched after saving final prompt to ensure Gemma sees the full summary

---

## [1.1.0] - 2025-07-xx

### Added
- Memory system with automatic extraction from conversations
- Memory categories: name, city, job, hobbies, status, favorites, preferences
- Custom category support (any snake_case key)
- Memory injection into system prompt for personalized responses
- Memory summary compression when count exceeds 10
- `/memory` — View all stored memories
- `/forget [key]` — Delete a specific memory
- `/clearmemory` — Delete all memories
- `/clearhistory` — Clear conversation history (preserves memories)
- DeFi TVL tool via DefiLlama with Gemini function calling
- `/tvl [protocol]` command for TVL growth data

### Fixed
- Memory regex pattern corrected from `$$MEMORY$$` to `\[MEMORY\](.*?)\[/MEMORY\]`
- Fallback memory parser no longer incorrectly strips responses containing the word "memory"
- This was the root cause of truncated bot responses

---

## [1.0.0] - 2025-07-xx

### Added
- Initial release
- Telegram bot powered by Google Gemma 4 (gemma-4-26b-a4b-it)
- Natural conversation in Bahasa Indonesia (default)
- Conversation history with last 20 messages context
- SQLite database for message and memory persistence
- Railway deployment with persistent volume at `/data`
- `extract_full_text()` handler for Gemma 4 thinking mode responses
- Error handling for quota limits, timeouts, auth errors, and model availability
- Telegram command menu registration via `post_init`

---

## Technical Notes

### Gemma 4 Thinking Mode
Gemma 4 always uses thinking mode. Responses contain both `thinking` parts and `text` parts. The `extract_full_text()` function handles this by:
1. Prioritizing text parts (non-thinking)
2. Falling back to thinking parts if text is too short or empty
3. Final fallback to `response.text`

### Function Calling Limitation
The `thought_signature` field in Gemma 4 function calling can cause errors during multi-step tool use. Current implementation includes:
- Copying `thought_signature` from function call parts to function response parts
- Fallback to direct tool result if second call fails

### Web Search Architecture
Web search avoids Gemini function calling to prevent `thought_signature` issues. Instead:
1. Gemma 4 outputs a `[SEARCH]query[/SEARCH]` tag in its response
2. Bot parses the tag locally (regex)
3. Executes search via ddgs (no API call)
4. Sends results back to Gemma 4 for summarization (1 additional API call)
```

---

## 6. `requirements.txt`

```txt
python-telegram-bot
google-genai
python-dotenv
httpx
PyPDF2
python-docx
openpyxl
fpdf2
ddgs
```


