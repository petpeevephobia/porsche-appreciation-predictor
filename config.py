"""Configuration settings for the Porsche scraper."""
import os
from dotenv import load_dotenv

load_dotenv()

# Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

# CSV Data Paths (relative to repo root: project/data/csv/)
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_CSV_PATH = os.path.join(_PROJECT_ROOT, "project", "data", "csv", "porsche_data.csv")
YEARS_AGO_CSV_PATH = os.path.join(_PROJECT_ROOT, "project", "data", "csv", "years_ago.csv")

# Column names for the main data CSV
COLUMNS = ["model_year", "model_type", "mileage", "condition", "price_now", "price_3_years_ago", "appreciated", "source"]

# Column names for the years_ago CSV (historical 2020-2022 listings)
YEARS_AGO_COLUMNS = ["model_year", "model_type", "mileage", "condition", "sale_price", "sale_date", "source"]

# Result card visibility
# Toggle which of the 4 result cards are computed and shown. Applies globally.
DISPLAY_CARDS = {
    "vehicle_info":     True,   # Card 1: Vehicle Detected
    "condition_report": False,   # Card 2: Condition Report
    "valuation":        True,   # Card 3: Market Valuation
    "appreciation":     True,   # Card 4: 3-Year Outlook
}
