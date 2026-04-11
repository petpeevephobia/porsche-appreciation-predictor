# Porsche Appreciation Predictor

An end-to-end multimodal AI system that analyses used Porsche listings — images and seller text — and outputs a condition report, market valuation, and 3-year appreciation prediction.

---

## Project Summary

```
PROJECT:   Porsche Appreciation Predictor

OBJECTIVE: Build an end-to-end ML web app predicting Porsche value trends

TECHNICAL STACK:
  Data:       1,234 Porsche listings scraped from Bring a Trailer
              Features: model type, year, mileage, condition, price (2025 & 2022)
              Images:   up to 12 photos per listing (~14,800 images total)
  Embeddings: CLIP (ViT-B/32) for images, all-MiniLM-L6-v2 for text
  Vector DB:  Qdrant (on-disk) with cosine similarity search
  ML Model:   Random Forest Classifier (scikit-learn), 78% accuracy
  LLM:        Gemini (multimodal) for condition reports and valuation reasoning
  Backend:    Flask, Python
  Frontend:   HTML / CSS / JavaScript (vanilla, no framework)
  Deployment: Fly.io

KEY RESULTS:
  - Model achieves 78% accuracy on held-out test set
  - Identified mileage as the strongest single predictor of depreciation
  - 911 models show higher appreciation rates (70%) vs. Caymans (45%)
  - Gemini condition report catches text/photo inconsistencies in real listings
  - Deployed live web app with <100ms prediction latency (excluding LLM call)

WHAT I LEARNED:
  - End-to-end ML workflow: data collection → preprocessing → training → deployment
  - Multimodal AI: combining vision embeddings (CLIP) with LLM reasoning (Gemini)
  - Vector retrieval: building and querying a Qdrant similarity index
  - Model evaluation: accuracy, precision, recall, F1, feature importance
  - Pipeline engineering: chaining CLIP → Qdrant → Gemini → sklearn in one request
  - Production Flask app: file upload handling, temp files, JSON API
  - Cloud deployment: containerisation and hosting on Fly.io
```

---

## Architecture

```mermaid
flowchart TD
    User["User (browser)"]

    subgraph frontend [Frontend]
        UI["HTML / CSS / JS: Upload + Results"]
    end

    subgraph backend [Flask Backend — app.py]
        Route["/analyze POST route"]
        CLIP["CLIP ViT-B/32: Image encoder"]
        Qdrant["Qdrant Vector DB: Cosine similarity search"]
        Gemini["Gemini (multimodal): Condition report + Valuation"]
        SKLearn["Random Forest: Appreciation classifier"]
        HistMatcher["Historical Matcher: years_ago.csv lookup"]
    end

    User -->|"Upload image + seller text"| UI
    UI -->|"POST /analyze (multipart)"| Route
    Route --> CLIP
    CLIP -->|"512-dim image vector"| Qdrant
    Qdrant -->|"Top-10 similar listings"| Route
    Route --> HistMatcher
    HistMatcher -->|"Price 3 years ago"| Route
    Route --> Gemini
    Gemini -->|"Condition report JSON\n+ Valuation text"| Route
    Route --> SKLearn
    SKLearn -->|"will_appreciate + confidence"| Route
    Route -->|"SSE stream (progress + result)"| UI
    UI --> User
```

---

## Reasoning Flow

How an image and seller text move through the pipeline in a single request:

```
1. USER UPLOADS IMAGE + (optional) seller description + asking price + (optional) mileage
        |
        v
2. CLIP ENCODING
   Image → 512-dimensional vector (normalised)
        |
        v
3. QDRANT SIMILARITY SEARCH
   Query vector → top-10 most visually similar listings from 1,234-listing index
        |
        v
4. VEHICLE IDENTIFICATION  (majority vote on top-5 matches)
   model_type  → most common among top-5
   model_year  → median of top-5
   condition   → most common among top-5
   mileage     → median of top-5
        |
        v
5. HISTORICAL PRICE LOOKUP
   HistoricalMatcher queries years_ago.csv (BaT 2020-2022 sold listings)
   Finds best price match within ±1 year, ±15% mileage, same condition
        |
        v
6. GEMINI CONDITION REPORT  (multimodal)
   Input:  uploaded image + seller description
   Output: structured JSON
           - overall grade + score (1-10)
           - paint/body issues (location, severity)
           - aftermarket modifications
           - missing/damaged trim
           - text-photo inconsistencies
           - red flags
           - recommended restoration steps
        |
        v
7. GEMINI VALUATION  (multimodal)
   Input:  uploaded image + vehicle info + similar listings + historical price
   Output: VALUATION: $X,XXX  /  REASONING: ...  /  FACTORS: ...
        |
        v
8. SKLEARN APPRECIATION PREDICTION
   Features: model_year, model_type, mileage, condition,
             current_valuation, price_3_years_ago
   Output:   will_appreciate (bool) + confidence score
        |
        v
9. SSE STREAM → browser updates real-time progress bar, then renders 4 result cards
```

---

## Why This Project Maps to Porsche AI

| Capability | How it appears in this project |
|---|---|
| **Multimodal AI** | CLIP image embeddings + Gemini vision for condition analysis and valuation — images and text are processed jointly |
| **Retrieval systems** | Qdrant vector DB with cosine similarity search over 1,234 listings; custom historical price matcher over 5,000+ BaT sold records |
| **Pipeline engineering** | Six-stage chain (CLIP → Qdrant → HistoricalMatcher → Gemini × 2 → sklearn) streamed to the browser in real time via Server-Sent Events |
| **LLM + vision integration** | Gemini receives raw PIL images alongside structured prompts; outputs both structured JSON (condition) and free-text (valuation) |
| **ML modelling** | Random Forest trained on scraped real-world data; feature importance analysis identifies mileage as the dominant depreciation signal |
| **Cloud deployment** | Containerised Flask app deployed to Fly.io; environment-variable secret management; persistent Qdrant DB volume |
| **Monitoring** | Model predictions logged per-request; pipeline step timing visible in server stdout; error states surfaced to the UI |
| **Data engineering** | Custom Selenium scraper collects listings, images, and seller descriptions from Bring a Trailer; data cleaned and structured into CSVs |

---

## Running Locally

### Prerequisites

- Python 3.10+
- A Gemini API key ([get one free at Google AI Studio](https://aistudio.google.com/apikey))

### Setup

```bash
# Clone the repo
git clone https://github.com/your-username/porsche-appreciation-predictor.git
cd porsche-appreciation-predictor

# Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set your Gemini API key
cp .env.example .env
# Then open .env and paste your key:  GEMINI_API_KEY=your_key_here
```

### Run

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

> **First boot takes ~60 seconds** while CLIP and SentenceTransformer load into memory. Subsequent requests are fast.

### Notebooks (optional)

The `project/notebooks/` folder contains the full development history:

| Notebook | Purpose |
|---|---|
| `01_eda.ipynb` | Exploratory data analysis |
| `02_preprocessing_and_training.ipynb` | Feature engineering + Random Forest training |
| `03_multimodal_preprocessing.ipynb` | CLIP + SentenceTransformer embedding generation, Qdrant indexing |
| `04_valuation_pipeline.ipynb` | End-to-end pipeline prototype |

---

## Project Structure

```
porsche-appreciation-predictor/
├── app.py                          # Flask app + full pipeline
├── historical_matcher.py           # years_ago.csv price lookup
├── condition_analyzer.py           # Rule-based condition classifier
├── config.py                       # Paths and API config
├── scraper.py                      # Selenium BaT scraper (data collection only)
├── requirements.txt
├── .env.example
├── templates/
│   └── index.html                  # Single-page UI
├── static/
│   └── style.css
└── project/
    ├── notebooks/                  # Development notebooks
    └── data/                       # Not in git — copy manually
        ├── csv/
        │   ├── porsche_data.csv    # 1,234 current listings (training only)
        │   └── years_ago.csv       # 5,000+ BaT 2020-2022 sold records (runtime)
        ├── qdrant_db/              # On-disk vector index (runtime)
        ├── porsche_model.pkl       # Trained Random Forest (runtime)
        └── porsche_encoder.pkl     # Fitted OneHotEncoder (runtime)
```