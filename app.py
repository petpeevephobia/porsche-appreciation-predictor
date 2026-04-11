import os
import sys
import re
import json
import pickle
import tempfile

import numpy as np
import pandas as pd
import torch
import clip
from collections import Counter
from PIL import Image

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
import google.genai as genai
from dotenv import load_dotenv

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'project', 'data')

from historical_matcher import HistoricalMatcher

# ── Load all models once at startup ───────────────────────────────────────────
print('Loading models ...')
device = 'cuda' if torch.cuda.is_available() else 'cpu'

clip_model, clip_preprocess = clip.load('ViT-B/32', device=device)
print('  CLIP ready')

text_model = SentenceTransformer('all-MiniLM-L6-v2')
print('  SentenceTransformer ready')

qdrant = QdrantClient(path=os.path.join(DATA, 'qdrant_db'))
print('  Qdrant ready')

with open(os.path.join(DATA, 'porsche_model.pkl'), 'rb') as f:
    appreciation_model = pickle.load(f)
with open(os.path.join(DATA, 'porsche_encoder.pkl'), 'rb') as f:
    appreciation_encoder = pickle.load(f)
print('  sklearn models ready')

historical_matcher = HistoricalMatcher()
historical_matcher.load_historical_listings_from_csv()
print('  HistoricalMatcher ready')

GEMINI_MODEL  = os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite-preview')
gemini_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
print('  Gemini client ready')
print('All models loaded.\n')

# ── Pipeline functions ─────────────────────────────────────────────────────────

def find_similar_listings(image_path, top_k=10):
    image = Image.open(image_path).convert('RGB')
    tensor = clip_preprocess(image).unsqueeze(0).to(device)
    with torch.no_grad():
        feats = clip_model.encode_image(tensor)
        feats = feats / feats.norm(dim=1, keepdim=True)

    results = qdrant.query_points(
        collection_name='porsche_images',
        query=feats.cpu().numpy()[0].tolist(),
        limit=top_k,
    )
    return [
        {
            'listing_id': r.payload['listing_id'],
            'model_year':  r.payload['model_year'],
            'model_type':  r.payload['model_type'],
            'mileage':     r.payload['mileage'],
            'condition':   r.payload['condition'],
            'price_now':   r.payload['price_now'],
            'source':      r.payload['source'],
        }
        for r in results.points
    ]


def extract_vehicle_info(similar_listings):
    if not similar_listings:
        return None
    top5 = similar_listings[:5]

    model_type = Counter(l['model_type'] for l in top5).most_common(1)[0][0]
    years      = [float(l['model_year']) for l in top5 if pd.notna(l['model_year'])]
    model_year = int(np.median(years)) if years else None
    condition  = Counter(l['condition'] for l in top5).most_common(1)[0][0]
    mileages   = [l['mileage'] for l in top5 if pd.notna(l['mileage'])]
    mileage    = int(np.median(mileages)) if mileages else None

    return {
        'model_type':        model_type,
        'model_year':        model_year,
        'condition':         condition,
        'mileage':           mileage,
        'similar_listings':  similar_listings,
    }


def get_historical_price(vehicle_info):
    target = {
        'model_year': str(vehicle_info['model_year']),
        'model_type': vehicle_info['model_type'],
        'mileage':    vehicle_info.get('mileage', ''),
        'condition':  vehicle_info['condition'],
    }
    result = historical_matcher.calculate_price_3_years_ago(target)
    return None if result == 'insufficient_data' else result


_CONDITION_PROMPT = """
You are a certified Porsche pre-purchase inspection specialist with 20+ years of experience.
Examine every photo of this used Porsche listing carefully.

Seller description:
\"\"\"
{seller_text}
\"\"\"

Return ONLY valid JSON — no markdown fences, no commentary — matching this exact schema:
{{
  "overall_condition_grade": "Excellent|Good|Fair|Poor",
  "condition_score": <float 1.0-10.0>,
  "paint_and_body": {{
    "issues_found": [{{"location": "", "severity": "minor|moderate|severe", "description": ""}}],
    "panel_gaps_even": true,
    "repaint_evidence": false,
    "repaint_notes": ""
  }},
  "aftermarket_modifications": [{{"item": "", "description": "", "oem_compliant": true}}],
  "missing_or_damaged_trim": [{{"item": "", "location": "", "severity": ""}}],
  "interior_condition": {{"grade": "", "issues": []}},
  "text_photo_inconsistencies": [{{"claim_in_text": "", "what_photos_show": "", "severity": ""}}],
  "red_flags": [],
  "recommended_restoration_steps": [],
  "summary": ""
}}

Only report issues directly observable in the photos or that contradict the seller text.
Use empty lists [] for categories with no issues.
"""


def generate_condition_report(image_path, seller_text=''):
    prompt = _CONDITION_PROMPT.format(
        seller_text=seller_text.strip() or 'Not provided.'
    )
    image = Image.open(image_path).convert('RGB')
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt, image],
    )
    raw = response.text.strip()
    # Strip markdown fences if Gemini adds them despite instructions
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            'overall_condition_grade': 'Unknown',
            'condition_score': None,
            'paint_and_body': {'issues_found': [], 'panel_gaps_even': None,
                               'repaint_evidence': None, 'repaint_notes': ''},
            'aftermarket_modifications': [],
            'missing_or_damaged_trim': [],
            'interior_condition': {'grade': 'Unknown', 'issues': []},
            'text_photo_inconsistencies': [],
            'red_flags': [],
            'recommended_restoration_steps': [],
            'summary': raw,  # surface raw text so user sees something
        }


def generate_valuation(image_path, vehicle_info, similar_listings,
                       price_3_years_ago, current_price=None, user_mileage=None):
    similar_summary = '\n'.join(
        f"- {l['model_type']} {l['model_year']} ({l['condition']}, "
        f"{l['mileage']}mi, USD{int(l['price_now']):,})"
        for l in similar_listings[:5]
    )
    mileage_line = (f"- Mileage: {int(user_mileage):,} mi"
                    if user_mileage is not None else "")
    prompt = f"""
You are an expert Porsche appraiser with 20 years of experience.
Analyse this Porsche listing and provide a market valuation.

Vehicle Information (from image matching):
- Model Type: {vehicle_info['model_type']}
- Model Year: {vehicle_info['model_year']}
- Condition: {vehicle_info['condition']}
{mileage_line}
Similar Historical Listings (from vector search):
{similar_summary}

Historical Price (3 years ago): {"${:,}".format(price_3_years_ago) if price_3_years_ago else "Unknown"}
Current Asking Price: {"${:,}".format(int(current_price)) if current_price else "Not provided"}

Analyse the uploaded image, compare with similar listings, and provide:
1. Estimated Current Market Value (USD)
2. Brief reasoning (2-3 sentences)
3. Key factors affecting valuation

Format your response as:
VALUATION: $X,XXX
REASONING: [your analysis]
FACTORS: [key factors]
"""
    image = Image.open(image_path).convert('RGB')
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt, image],
    )
    return response.text


def parse_llm_valuation(text):
    match = re.search(r'VALUATION:\s*\$?([\d,]+)', text)
    return float(match.group(1).replace(',', '')) if match else None


def predict_appreciation(vehicle_info, current_valuation, price_3_years_ago, user_mileage=None):
    mileage = user_mileage if user_mileage is not None else vehicle_info.get('mileage')
    input_df = pd.DataFrame([{
        'model_year':        vehicle_info['model_year'],
        'model_type':        vehicle_info['model_type'],
        'mileage':           mileage,
        'condition':         vehicle_info['condition'],
        'price_now':         current_valuation,
        'price_3_years_ago': price_3_years_ago if price_3_years_ago is not None else 0,
    }])
    object_cols = appreciation_encoder.feature_names_in_.tolist()
    for col in object_cols:
        input_df[col] = input_df[col].astype(str)
    encoded = pd.DataFrame(appreciation_encoder.transform(input_df[object_cols]))
    encoded.index = input_df.index
    X = pd.concat([input_df.drop(object_cols, axis=1), encoded], axis=1)
    X.columns = X.columns.astype(str)
    raw = appreciation_model.predict(X)
    return {
        'will_appreciate': bool(int(np.round(raw[0])) == 1),
        'confidence':      round(float(raw[0]), 2),
    }


def full_pipeline(image_path, seller_text='', current_price=None, user_mileage=None):
    similar      = find_similar_listings(image_path, top_k=10)
    vehicle_info = extract_vehicle_info(similar)
    hist_price   = get_historical_price(vehicle_info)

    condition_report = generate_condition_report(image_path, seller_text)
    llm_valuation    = generate_valuation(image_path, vehicle_info, similar,
                                           hist_price, current_price,
                                           user_mileage=user_mileage)
    current_val = parse_llm_valuation(llm_valuation)
    if current_val is None:
        current_val = current_price or float(
            np.median([l['price_now'] for l in similar[:5]])
        )

    appreciation = predict_appreciation(vehicle_info, current_val, hist_price,
                                        user_mileage=user_mileage)

    # Remove nested similar_listings from vehicle_info to keep response clean
    vehicle_info_clean = {k: v for k, v in vehicle_info.items()
                          if k != 'similar_listings'}

    return {
        'vehicle_info':          vehicle_info_clean,
        'price_3_years_ago':     hist_price,
        'condition_report':      condition_report,
        'llm_valuation':         llm_valuation,
        'current_valuation':     current_val,
        'appreciation_prediction': appreciation,
    }


# ── Debug logging helper ───────────────────────────────────────────────────────
import time as _time

_DBG_LOG = os.path.join(ROOT, 'debug-8147b6.log')

def _dbg(msg, data=None, hypothesis=''):
    entry = json.dumps({'sessionId':'8147b6','timestamp':int(_time.time()*1000),
                        'location':'app.py','message':msg,'data':data or {},
                        'hypothesisId':hypothesis})
    with open(_DBG_LOG, 'a') as _f:
        _f.write(entry + '\n')

# ── Flask routes ───────────────────────────────────────────────────────────────
app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/debug-log', methods=['POST'])
def debug_log():
    entry = request.get_json(silent=True) or {}
    with open(_DBG_LOG, 'a') as f:
        f.write(json.dumps(entry) + '\n')
    return '', 204


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.route('/analyze', methods=['POST'])
def analyze():
    if 'image' not in request.files or request.files['image'].filename == '':
        return jsonify({'error': 'No image provided.'}), 400

    image_file        = request.files['image']
    seller_text       = request.form.get('seller_text', '')
    asking_price_raw  = request.form.get('asking_price', '').strip()
    asking_price      = float(asking_price_raw) if asking_price_raw else None
    mileage_raw       = request.form.get('mileage', '').strip()
    user_mileage      = float(mileage_raw) if mileage_raw else None

    suffix = os.path.splitext(image_file.filename)[1] or '.jpg'
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    image_file.save(tmp.name)
    tmp.close()

    @stream_with_context
    def generate():
        try:
            _dbg('yield scanning', hypothesis='H-A')
            chunk = _sse({'step': 'scanning', 'label': 'Scanning image…', 'progress': 10})
            _dbg('about to yield scanning chunk', {'chunk': chunk}, hypothesis='H-A')
            yield chunk
            _dbg('yielded scanning — now running find_similar_listings', hypothesis='H-A')
            similar = find_similar_listings(tmp.name, top_k=10)

            _dbg('yield identifying', hypothesis='H-A')
            yield _sse({'step': 'identifying', 'label': 'Identifying vehicle…', 'progress': 25})
            vehicle_info = extract_vehicle_info(similar)

            _dbg('yield history', hypothesis='H-A')
            yield _sse({'step': 'history', 'label': 'Checking market history…', 'progress': 40})
            hist_price = get_historical_price(vehicle_info)

            _dbg('yield condition', hypothesis='H-A')
            yield _sse({'step': 'condition', 'label': 'Analysing condition…', 'progress': 55})
            condition_report = generate_condition_report(tmp.name, seller_text)

            _dbg('yield valuation', hypothesis='H-A')
            yield _sse({'step': 'valuation', 'label': 'Valuing the car…', 'progress': 75})
            llm_valuation = generate_valuation(tmp.name, vehicle_info, similar,
                                               hist_price, asking_price,
                                               user_mileage=user_mileage)
            current_val = parse_llm_valuation(llm_valuation)
            if current_val is None:
                current_val = asking_price or float(
                    np.median([l['price_now'] for l in similar[:5]])
                )

            _dbg('yield predicting', hypothesis='H-A')
            yield _sse({'step': 'predicting', 'label': 'Predicting appreciation…', 'progress': 90})
            appreciation = predict_appreciation(vehicle_info, current_val, hist_price,
                                                user_mileage=user_mileage)

            vehicle_info_clean = {k: v for k, v in vehicle_info.items()
                                  if k != 'similar_listings'}
            result = {
                'vehicle_info':            vehicle_info_clean,
                'price_3_years_ago':       hist_price,
                'condition_report':        condition_report,
                'llm_valuation':           llm_valuation,
                'current_valuation':       current_val,
                'appreciation_prediction': appreciation,
            }
            _dbg('yield done', hypothesis='H-A')
            yield _sse({'step': 'done', 'label': 'Done', 'progress': 100, 'result': result})
            _dbg('generator finished normally', hypothesis='H-A')

        except Exception as e:
            _dbg('generator exception', {'error': str(e)}, hypothesis='H-A')
            yield _sse({'step': 'error', 'error': str(e)})
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=False, threaded=True)
