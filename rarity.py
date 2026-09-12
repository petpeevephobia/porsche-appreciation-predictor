"""
Static, rule-based rarity scoring for identified Porsches.
No LLM calls. Mirrors the manufacturing_history.py pattern: a curated static
dataset + deterministic Python logic, keyed by model_type.

Production figures are the same ones already curated in MANUFACTURING_HISTORY —
kept here as structured numbers instead of prose so they can be bucketed.
"""

import re

# ── Static production data, keyed by model_type ────────────────────────────
# production_total: best-available approximate global unit count.
#   None = mass-production platform where a single "total" isn't meaningful
#   for rarity purposes (still-in-production, or SUV platform).
# homologation: True if the model was built to satisfy racing homologation
#   rules (a small commercial run required to allow a racing variant to compete).
# racing_pedigree: True if the model_type is itself a competition car
#   (not just a road car with a motorsport-derived engine).
RARITY_DATA = {
    "911":           {"production_total": 1_200_000, "homologation": False, "racing_pedigree": False},
    "912":           {"production_total": 34_000,    "homologation": False, "racing_pedigree": False},
    "914":           {"production_total": 119_000,   "homologation": False, "racing_pedigree": False},
    "356":            {"production_total": 76_000,    "homologation": False, "racing_pedigree": False},
    "356 Speedster":  {"production_total": 2_347,     "homologation": False, "racing_pedigree": False},
    "924":           {"production_total": 150_000,   "homologation": False, "racing_pedigree": False},
    "928":           {"production_total": 61_000,    "homologation": False, "racing_pedigree": False},
    "944":           {"production_total": 163_000,   "homologation": False, "racing_pedigree": False},
    "959":           {"production_total": 337,       "homologation": True,  "racing_pedigree": False},
    "Boxster":        {"production_total": 400_000,   "homologation": False, "racing_pedigree": False},
    "Cayman":         {"production_total": 150_000,   "homologation": False, "racing_pedigree": False},
    "957":           {"production_total": None,      "homologation": False, "racing_pedigree": False},
    "958":           {"production_total": None,      "homologation": False, "racing_pedigree": False},
    "550":           {"production_total": 90,        "homologation": False, "racing_pedigree": True},
    "934":           {"production_total": 31,        "homologation": True,  "racing_pedigree": True},
    "935":           {"production_total": 40,        "homologation": True,  "racing_pedigree": True},
    "956":           {"production_total": 28,        "homologation": False, "racing_pedigree": True},
    "962":           {"production_total": 91,        "homologation": False, "racing_pedigree": True},
    "918":           {"production_total": 918,       "homologation": False, "racing_pedigree": False},
}

DEFAULT_RARITY = {"production_total": None, "homologation": False, "racing_pedigree": False}

# Production-volume tier thresholds (units). Deterministic, not per-model.
_TIER_THRESHOLDS = (
    (1_000,    "Ultra-Rare"),
    (50_000,   "Rare"),
    (200_000,  "Limited Production"),
    (float("inf"), "Mass Production"),
)

# Tier -> base score (1-5, 5 = rarest)
_TIER_SCORE = {"Ultra-Rare": 5, "Rare": 4, "Limited Production": 2, "Mass Production": 1}

# Keyword signals scanned in the seller's own listing text. These are
# surfaced as *unverified flags* — the app is not asserting they're true,
# only that the seller mentioned them, so the user can verify.
_KEYWORD_FLAGS = [
    (re.compile(r"\bpaint[\s-]?to[\s-]?sample\b|\bPTS\b", re.I),
     "Seller mentions a paint-to-sample color"),
    (re.compile(r"\bsonderwunsch\b|\bporsche exclusive\b|\bfactory special order\b", re.I),
     "Seller mentions a Porsche Exclusive / Sonderwunsch commission"),
    (re.compile(r"\bleichtbau\b|\blightweight package\b", re.I),
     "Seller mentions a factory lightweight (Leichtbau) build"),
    (re.compile(r"\bone of (only )?\d+\b|\b\d+ (built|made|produced)\b", re.I),
     "Seller claims a specific limited-production number"),
    (re.compile(r"\bmanual transmission\b|\b6-speed\b|\b7-speed manual\b", re.I),
     "Seller highlights a manual-transmission configuration"),
]


def _base_tier(production_total):
    if production_total is None:
        return "Mass Production"
    for threshold, tier in _TIER_THRESHOLDS:
        if production_total < threshold:
            return tier
    return "Mass Production"


def compute_rarity(vehicle_info, seller_text=""):
    """
    Pure rule-based rarity assessment. No LLM call.

    Args:
        vehicle_info: dict with at least 'model_type' (from extract_vehicle_info)
        seller_text: raw seller listing text (already collected for the
                     condition report call — reused here, not re-fetched)

    Returns:
        dict: {
            'tier': str,               # e.g. "Ultra-Rare"
            'score': int,              # 1-5, 5 = rarest
            'production_total': int|None,
            'homologation_special': bool,
            'racing_pedigree': bool,
            'flags': list[str],        # unverified signals found in seller text
        }
    """
    model_type = vehicle_info.get("model_type")
    data = RARITY_DATA.get(model_type, DEFAULT_RARITY)

    tier = _base_tier(data["production_total"])
    score = _TIER_SCORE[tier]

    # Homologation specials and pure racing cars are definitionally rare
    # regardless of the raw unit count bucket.
    if data["homologation"] or data["racing_pedigree"]:
        tier = "Ultra-Rare"
        score = 5

    flags = [label for pattern, label in _KEYWORD_FLAGS if pattern.search(seller_text or "")]

    # Each matched flag nudges the score up by 1 (capped at 5), since a
    # seller-claimed special spec makes an otherwise-common car less certain
    # to be a standard example. This never lowers a score, and never
    # fabricates a production number — it's a visibility bump, not a claim.
    if flags:
        score = min(5, score + 1)
        if score == 5 and tier != "Ultra-Rare":
            tier = "Ultra-Rare"
        elif score == 4 and tier == "Limited Production":
            tier = "Rare"

    return {
        "tier": tier,
        "score": score,
        "production_total": data["production_total"],
        "homologation_special": data["homologation"],
        "racing_pedigree": data["racing_pedigree"],
        "flags": flags,
    }