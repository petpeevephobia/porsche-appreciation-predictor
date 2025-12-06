"""Configuration settings for the Porsche scraper."""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o-mini"  # Can be changed to gpt-4 if needed

# Google Sheets Configuration
GOOGLE_SHEETS_CREDENTIALS_PATH = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SHEET_NAME = "porsche_data"
YEARS_AGO_SHEET_NAME = "years_ago"

# Column names for the years_ago sheet (historical 2020-2022 listings)
YEARS_AGO_COLUMNS = ["model_year", "model_type", "mileage", "condition", "sale_price", "sale_date", "source"]

# Scraper Configuration
BASE_URL = "https://bringatrailer.com"
REQUEST_DELAY = 1  # Seconds between requests to be respectful
MAX_RETRIES = 3

# Column names for the Google Sheet
COLUMNS = ["model_year", "model_type", "mileage", "condition", "price_now", "price_3_years_ago", "appreciated", "source"]

# Image Scraper Configuration
# Path relative to scraper directory: go up one level, then into project/data/images
IMAGE_SAVE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "project", "data", "images")
VISION_MODEL = "gpt-4o-mini"  # Use gpt-4o for vision, or gpt-4o-mini for cost savings
MAX_IMAGES_PER_LISTING = 12

# Description Scraper Configuration
# Path relative to scraper directory: go up one level, then into project/data/descriptions
DESCRIPTION_SAVE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "project", "data", "descriptions")

