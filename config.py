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

# Scraper Configuration
BASE_URL = "https://bringatrailer.com"
REQUEST_DELAY = 1  # Seconds between requests to be respectful
MAX_RETRIES = 3

# Image Scraper Configuration
IMAGE_SAVE_PATH = os.path.join(_PROJECT_ROOT, "project", "data", "images")
MAX_IMAGES_PER_LISTING = 12

# Description Scraper Configuration
DESCRIPTION_SAVE_PATH = os.path.join(_PROJECT_ROOT, "project", "data", "descriptions")
