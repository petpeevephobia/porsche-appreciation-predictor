"""Image scraper for downloading Porsche listing images."""
import argparse
import json
import logging
import os
import sys
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import gspread
from google.oauth2.service_account import Credentials
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('image_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class ImageScraper:
    """Scrapes images from Porsche listings."""
    
    def __init__(self):
        """Initialize the image scraper with Sheets and Selenium clients."""
        self._init_sheets_client()
        self._init_selenium_driver()
        self.image_save_path = config.IMAGE_SAVE_PATH
        self.max_images = config.MAX_IMAGES_PER_LISTING
        
        # Ensure image directory exists
        os.makedirs(self.image_save_path, exist_ok=True)
    
    def _get_relative_path(self, filename):
        """
        Convert absolute file path to relative path from project root.
        
        Args:
            filename: Just the filename (e.g., 'p00001_image_1.jpg')
            
        Returns:
            str: Relative path from project root (e.g., 'project/data/images/p00001_image_1.jpg')
        """
        return f"project/data/images/{filename}"
    
    def _init_sheets_client(self):
        """Initialize Google Sheets client."""
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_file(
                config.GOOGLE_SHEETS_CREDENTIALS_PATH,
                scopes=scopes
            )
            self.sheets_client = gspread.authorize(creds)
            self.sheet = self.sheets_client.open_by_key(config.GOOGLE_SHEET_ID)
            self.worksheet = self.sheet.worksheet(config.SHEET_NAME)
            logger.info(f"Connected to Google Sheet: {config.SHEET_NAME}")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            raise
    
    def _init_selenium_driver(self):
        """Initialize Selenium Chrome driver."""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("Selenium driver initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            logger.error("Make sure ChromeDriver is installed and in PATH")
            raise
    
    def __del__(self):
        """Clean up Selenium driver on deletion."""
        if hasattr(self, 'driver'):
            try:
                self.driver.quit()
            except:
                pass
    
    def read_listings_from_sheet(self):
        """
        Read listings from porsche_data sheet.
        
        Returns:
            list: List of dicts with 'id', 'source', 'model_year' keys
        """
        try:
            all_rows = self.worksheet.get_all_values()
            if len(all_rows) <= 1:
                logger.warning("No data rows found in sheet (only header row)")
                return []
            
            # Find column indices
            header_row = all_rows[0]
            try:
                id_idx = header_row.index('id')
                source_idx = header_row.index('source')
                model_year_idx = header_row.index('model_year')
            except ValueError as e:
                logger.error(f"Required column not found in sheet: {e}")
                logger.error(f"Available columns: {header_row}")
                return []
            
            listings = []
            for row_idx, row in enumerate(all_rows[1:], start=2):
                # Skip if missing required fields
                if len(row) <= max(id_idx, source_idx, model_year_idx):
                    continue
                
                listing_id = row[id_idx].strip() if len(row) > id_idx else ''
                source = row[source_idx].strip() if len(row) > source_idx else ''
                model_year = row[model_year_idx].strip() if len(row) > model_year_idx else ''
                
                # Skip if any required field is empty
                if not listing_id or not source or not model_year:
                    continue
                
                listings.append({
                    'id': listing_id,
                    'source': source,
                    'model_year': model_year,
                    'row_idx': row_idx
                })
            
            logger.info(f"Read {len(listings)} valid listings from sheet")
            return listings
            
        except Exception as e:
            logger.error(f"Error reading listings from sheet: {e}")
            return []
    
    def extract_gallery_images(self, listing_url):
        """
        Extract image URLs from listing page's data-gallery-items attribute.
        
        Args:
            listing_url: URL of the listing page
            
        Returns:
            list: List of image URL strings (max MAX_IMAGES_PER_LISTING)
        """
        try:
            self.driver.get(listing_url)
            time.sleep(2)  # Wait for page to load
            
            # Find element with data-gallery-items attribute
            try:
                gallery_element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-gallery-items]'))
                )
                gallery_json = gallery_element.get_attribute('data-gallery-items')
            except Exception as e:
                logger.warning(f"Could not find data-gallery-items attribute: {e}")
                # Try alternative: parse HTML directly
                html = self.driver.page_source
                soup = BeautifulSoup(html, 'lxml')
                gallery_element = soup.find(attrs={'data-gallery-items': True})
                if gallery_element:
                    gallery_json = gallery_element.get('data-gallery-items')
                else:
                    logger.error(f"No gallery data found for {listing_url}")
                    return []
            
            if not gallery_json:
                logger.warning(f"Empty gallery data for {listing_url}")
                return []
            
            # Parse JSON
            try:
                gallery_data = json.loads(gallery_json)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse gallery JSON: {e}")
                return []
            
            # Extract image URLs (first MAX_IMAGES_PER_LISTING)
            image_urls = []
            for item in gallery_data[:self.max_images]:
                if 'large' in item and 'url' in item['large']:
                    image_urls.append(item['large']['url'])
            
            logger.info(f"Extracted {len(image_urls)} image URLs from {listing_url}")
            return image_urls
            
        except Exception as e:
            logger.error(f"Error extracting gallery images from {listing_url}: {e}")
            return []
    
    def download_and_save_image(self, image_url, listing_id, image_index):
        """
        Download image and save with proper naming.
        
        Args:
            image_url: URL of the image to download
            listing_id: ID of the listing
            image_index: Index of image in the listing (1-based)
            
        Returns:
            str or None: Relative path from project root if successful, None otherwise
        """
        try:
            # Download image
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            # Determine file extension from URL or content type
            content_type = response.headers.get('content-type', '')
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            else:
                ext = '.jpg'  # Default
            
            # Create filename: <id>_image_<number>.jpg (e.g., p00245_image_1.jpg)
            filename = f"{listing_id}_image_{image_index}{ext}"
            filepath = os.path.join(self.image_save_path, filename)
            
            # Handle duplicates by incrementing the number
            counter = image_index
            while os.path.exists(filepath):
                counter += 1
                filename = f"{listing_id}_image_{counter}{ext}"
                filepath = os.path.join(self.image_save_path, filename)
            
            # Save image
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            # Return relative path from project root
            relative_path = self._get_relative_path(filename)
            logger.info(f"Saved image: {filename}")
            return relative_path
            
        except Exception as e:
            logger.error(f"Error downloading/saving image {image_url}: {e}")
            return None
    
    def update_image_paths_in_sheet(self, row_idx, image_paths):
        """
        Update the image_paths column for a specific row.
        
        Args:
            row_idx: Row index (1-based, including header)
            image_paths: List of image file paths (relative paths from project root, e.g., 'project/data/images/p00001_image_1.jpg')
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Find image_paths column index
            header_row = self.worksheet.row_values(1)
            try:
                image_paths_idx = header_row.index('image_paths')
            except ValueError:
                logger.warning("image_paths column not found in sheet. Creating it...")
                # Add image_paths column at the end
                self.worksheet.add_cols(1)
                header_row = self.worksheet.row_values(1)
                image_paths_idx = len(header_row) - 1
                # Update header
                self.worksheet.update_cell(1, image_paths_idx + 1, 'image_paths')
            
            # Convert list to JSON string for storage
            image_paths_json = json.dumps(image_paths)
            
            # Update the cell (gspread uses 1-based indexing)
            self.worksheet.update_cell(row_idx, image_paths_idx + 1, image_paths_json)
            logger.info(f"Updated image_paths for row {row_idx} with {len(image_paths)} paths")
            return True
            
        except Exception as e:
            logger.error(f"Error updating image_paths in sheet for row {row_idx}: {e}")
            return False
    
    def process_listing(self, listing, skip_existing=False):
        """
        Process a single listing: extract images and save.
        
        Args:
            listing: Dict with 'id', 'source', 'model_year', 'row_idx' keys
            skip_existing: If True, skip if images already exist for this listing
            
        Returns:
            dict: Summary with 'success', 'images_saved', 'errors', 'image_paths' keys
        """
        listing_id = listing['id']
        listing_url = listing['source']
        row_idx = listing.get('row_idx', None)
        
        logger.info(f"Processing listing {listing_id}: {listing_url}")
        
        # Check if images already exist
        if skip_existing:
            existing_files = [f for f in os.listdir(self.image_save_path) if f.startswith(f"{listing_id}_image_")]
            if existing_files:
                logger.info(f"Skipping listing {listing_id} - {len(existing_files)} images already exist")
                # Get existing image paths (relative paths from project root)
                existing_paths = [self._get_relative_path(f) for f in existing_files]
                # Update sheet with existing paths
                if row_idx:
                    self.update_image_paths_in_sheet(row_idx, existing_paths)
                return {
                    'success': True,
                    'images_saved': len(existing_files),
                    'skipped': True,
                    'errors': [],
                    'image_paths': existing_paths
                }
        
        # Extract gallery images
        image_urls = self.extract_gallery_images(listing_url)
        if not image_urls:
            logger.warning(f"No images found for listing {listing_id}")
            return {'success': False, 'images_saved': 0, 'errors': ['No images found'], 'skipped': False, 'image_paths': []}
        
        # Process each image
        images_saved = 0
        errors = []
        image_paths = []
        
        for idx, image_url in enumerate(image_urls, 1):
            try:
                logger.info(f"Processing image {idx}/{len(image_urls)} for listing {listing_id}")
                
                # Download and save
                image_path = self.download_and_save_image(image_url, listing_id, idx)
                if image_path:
                    images_saved += 1
                    image_paths.append(image_path)
                else:
                    errors.append(f"Failed to save image {idx}")
                
                # Rate limiting between images
                time.sleep(0.5)
                
            except Exception as e:
                error_msg = f"Error processing image {idx}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Update sheet with image paths immediately after all images are saved
        if row_idx and image_paths:
            logger.info(f"Updating sheet with {len(image_paths)} image paths for listing {listing_id}")
            self.update_image_paths_in_sheet(row_idx, image_paths)
        
        return {
            'success': images_saved > 0,
            'images_saved': images_saved,
            'errors': errors,
            'skipped': False,
            'image_paths': image_paths
        }
    
    def process_all_listings(self, listings, limit=None, skip_existing=False, batch_size=10):
        """
        Process all listings with progress tracking.
        
        Args:
            listings: List of listing dicts
            limit: Maximum number of listings to process (None for all)
            skip_existing: Skip listings where images already exist
            batch_size: Process N listings before pausing
            
        Returns:
            dict: Summary statistics
        """
        if limit:
            listings = listings[:limit]
            logger.info(f"Limiting processing to first {limit} listings")
        
        total = len(listings)
        processed = 0
        successful = 0
        skipped = 0
        failed = 0
        total_images = 0
        
        logger.info(f"Starting to process {total} listings...")
        
        for idx, listing in enumerate(listings, 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"Processing listing {idx}/{total}: ID {listing['id']}")
            logger.info(f"{'='*50}")
            
            try:
                result = self.process_listing(listing, skip_existing=skip_existing)
                
                if result.get('skipped', False):
                    skipped += 1
                elif result['success']:
                    successful += 1
                    total_images += result['images_saved']
                else:
                    failed += 1
                
                processed += 1
                
                # Pause after batch
                if idx % batch_size == 0:
                    logger.info(f"\nProcessed {idx} listings. Pausing for rate limiting...")
                    time.sleep(config.REQUEST_DELAY * 2)
                
                # Delay between listings
                time.sleep(config.REQUEST_DELAY)
                
            except Exception as e:
                logger.error(f"Error processing listing {listing['id']}: {e}")
                failed += 1
                processed += 1
                continue
        
        summary = {
            'total': total,
            'processed': processed,
            'successful': successful,
            'skipped': skipped,
            'failed': failed,
            'total_images': total_images
        }
        
        logger.info(f"\n{'='*50}")
        logger.info("Processing Summary:")
        logger.info(f"Total listings: {total}")
        logger.info(f"Processed: {processed}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Skipped: {skipped}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Total images saved: {total_images}")
        logger.info(f"{'='*50}")
        
        return summary


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Scrape images from Porsche listings in porsche_data sheet'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit processing to first N listings (for testing)'
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip listings where images already exist'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Process N listings before pausing (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Validate configuration
    if not config.GOOGLE_SHEETS_CREDENTIALS_PATH:
        logger.error("GOOGLE_SHEETS_CREDENTIALS_PATH not set in environment variables")
        sys.exit(1)
    
    if not config.GOOGLE_SHEET_ID:
        logger.error("GOOGLE_SHEET_ID not set in environment variables")
        sys.exit(1)
    
    try:
        # Initialize scraper
        logger.info("Initializing image scraper...")
        scraper = ImageScraper()
        
        # Read listings from sheet
        logger.info("Reading listings from sheet...")
        listings = scraper.read_listings_from_sheet()
        
        if not listings:
            logger.warning("No valid listings found in sheet")
            return
        
        # Process all listings
        scraper.process_all_listings(
            listings,
            limit=args.limit,
            skip_existing=args.skip_existing,
            batch_size=args.batch_size
        )
        
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Clean up
        if 'scraper' in locals():
            try:
                scraper.__del__()
            except:
                pass


if __name__ == "__main__":
    main()

