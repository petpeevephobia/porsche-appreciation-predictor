# Portability Guide

This project runs entirely locally — no cloud database, no paid API (beyond the Gemini free tier).
Below is everything you need to move the project to a different PC.

## What to copy

| Item | Path | Why |
|---|---|---|
| Code | entire repo | All scripts, notebooks |
| Historical CSV | `project/data/csv/years_ago.csv` | 2020-2022 BaT sold listings used at runtime |
| Vector DB | `project/data/qdrant_db/` | Local Qdrant collections (image + text vectors) |
| Trained model | `project/data/porsche_model.pkl` | Sklearn appreciation prediction model |
| Encoder | `project/data/porsche_encoder.pkl` | Fitted OneHotEncoder used by the model |
| API key | `.env` | Your `GEMINI_API_KEY` |

> **Not needed at runtime:** `project/data/images/`, `project/data/descriptions/`, and `project/data/csv/porsche_data.csv` were only used during training. You do not need to copy them to run the app.

## Step-by-step: set up on a new PC

1. **Clone or copy the repo**
   ```bash
   git clone <your-repo-url>
   # or unzip the repo archive
   ```

2. **Copy the data files** (not tracked by git — copy manually):
   ```
   project/data/qdrant_db/
   project/data/csv/years_ago.csv
   project/data/porsche_model.pkl
   project/data/porsche_encoder.pkl
   ```

3. **Create your `.env` file**
   ```bash
   cp .env.example .env
   # then edit .env and paste your GEMINI_API_KEY
   ```
   Get a free key at https://aistudio.google.com/apikey

4. **Create and activate a virtual environment**
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

5. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   > Note: `git+https://github.com/openai/CLIP.git` in requirements.txt installs the CLIP model
   > directly from GitHub and requires `git` to be on your PATH.

6. **Open the notebooks**
   ```bash
   jupyter notebook project/notebooks/
   ```

## What stays local (never in git)

- `project/data/qdrant_db/` — vector database
- `project/data/csv/years_ago.csv` — historical price data
- `project/data/porsche_model.pkl` — trained model
- `project/data/porsche_encoder.pkl` — fitted encoder
- `.env` — API key

These paths are already listed in `.gitignore`.

## Ongoing costs

| Service | Cost |
|---|---|
| Gemini API (free tier) | $0 — 1,500 requests/day free via Google AI Studio |
| Data storage | $0 — local files only |
| Vector DB (Qdrant local) | $0 — runs on disk |
| Embeddings (CLIP + SentenceTransformers) | $0 — runs locally |
