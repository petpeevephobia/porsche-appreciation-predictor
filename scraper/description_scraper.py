"""Description scraper for extracting seller descriptions and listing specs from Porsche listings."""
import argparse
import logging
import os
import sys
import time
import re
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
        logging.FileHandler('description_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class DescriptionScraper:
    """Scrapes seller descriptions and listing specs from Porsche listings."""
    
    def __init__(self):
        """Initialize the description scraper with Sheets and Selenium clients."""
        self._init_sheets_client()
        self._init_selenium_driver()
        self.description_save_path = config.DESCRIPTION_SAVE_PATH
        
        # Ensure description directory exists
        os.makedirs(self.description_save_path, exist_ok=True)
    
    def _get_relative_path(self, filename):
        """
        Convert absolute file path to relative path from project root.
        
        Args:
            filename: Just the filename (e.g., 'p00001_seller_description.txt')
            
        Returns:
            str: Relative path from project root (e.g., 'project/data/descriptions/p00001_seller_description.txt')
        """
        return f"project/data/descriptions/{filename}"
    
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
            list: List of dicts with 'id', 'source', 'row_idx' keys
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
            except ValueError as e:
                logger.error(f"Required column not found in sheet: {e}")
                logger.error(f"Available columns: {header_row}")
                return []
            
            listings = []
            for row_idx, row in enumerate(all_rows[1:], start=2):
                # Skip if missing required fields
                if len(row) <= max(id_idx, source_idx):
                    continue
                
                listing_id = row[id_idx].strip() if len(row) > id_idx else ''
                source = row[source_idx].strip() if len(row) > source_idx else ''
                
                # Skip if any required field is empty
                if not listing_id or not source:
                    continue
                
                listings.append({
                    'id': listing_id,
                    'source': source,
                    'row_idx': row_idx
                })
            
            logger.info(f"Read {len(listings)} valid listings from sheet")
            return listings
            
        except Exception as e:
            logger.error(f"Error reading listings from sheet: {e}")
            return []
    
    def extract_seller_description(self, soup):
        """
        Extract seller description from listing page.
        
        Args:
            soup: BeautifulSoup object of the listing page
            
        Returns:
            str: Description text, or empty string if not found
        """
        try:
            # Look for div with class "post-excerpt" (handle typo with double class attribute)
            # Try exact match first
            desc_div = soup.find('div', class_='post-excerpt')
            
            # If not found, try to find div with class containing "post-excerpt"
            if not desc_div:
                desc_div = soup.find('div', class_=re.compile(r'post-excerpt', re.I))
            
            # If still not found, try to find by attribute (handling the typo case)
            if not desc_div:
                # Look for div with tabindex="0" that might have the class typo
                divs_with_tabindex = soup.find_all('div', attrs={'tabindex': '0'})
                for div in divs_with_tabindex:
                    # Check if class attribute contains "post-excerpt" (even with typo)
                    class_attr = div.get('class', [])
                    if isinstance(class_attr, list):
                        class_str = ' '.join(class_attr)
                    else:
                        class_str = str(class_attr)
                    if 'post-excerpt' in class_str.lower():
                        desc_div = div
                        break
            
            if desc_div:
                description = desc_div.get_text(separator=' ', strip=True)
                logger.debug(f"Extracted description: {len(description)} characters")
                return description
            else:
                logger.warning("Could not find post-excerpt div")
                return ""
                
        except Exception as e:
            logger.error(f"Error extracting seller description: {e}")
            return ""
    
    def extract_listing_specs(self, soup):
        """
        Extract listing specs from the Listing Details section.
        
        Args:
            soup: BeautifulSoup object of the listing page
            
        Returns:
            str: Specs text, or empty string if not found
        """
        try:
            # Find "Listing Details" strong tag
            details_heading = soup.find('strong', string=re.compile(r'Listing Details', re.I))
            
            if not details_heading:
                logger.warning("Could not find 'Listing Details' heading")
                return ""
            
            # Find the parent div with class "item"
            parent = details_heading.find_parent('div', class_='item')
            
            if not parent:
                # Try to find parent div and then look for item class
                parent = details_heading.find_parent('div')
                if parent and 'item' not in parent.get('class', []):
                    # Look for a parent with class "item"
                    parent = parent.find_parent('div', class_='item')
            
            if not parent:
                logger.warning("Could not find parent div with class 'item'")
                return ""
            
            # Find the ul within this section
            ul = parent.find('ul')
            
            if not ul:
                logger.warning("Could not find ul after 'Listing Details'")
                return ""
            
            # Extract all list items
            specs_list = []
            for li in ul.find_all('li'):
                li_text = li.get_text(strip=True)
                if li_text:
                    specs_list.append(li_text)
            
            specs_text = '\n'.join(specs_list)
            logger.debug(f"Extracted {len(specs_list)} spec items")
            return specs_text
            
        except Exception as e:
            logger.error(f"Error extracting listing specs: {e}")
            return ""
    
    def save_description_file(self, listing_id, description, specs):
        """
        Save description and specs to a TXT file.
        
        Args:
            listing_id: ID of the listing
            description: Description text
            specs: Specs text
            
        Returns:
            str or None: Relative path from project root if successful, None otherwise
        """
        try:
            # Create filename: <id>_seller_description.txt
            filename = f"{listing_id}_seller_description.txt"
            filepath = os.path.join(self.description_save_path, filename)
            
            # Combine description and specs
            content_parts = []
            if description:
                content_parts.append(description)
            if specs:
                # Add separator if both exist
                if description:
                    content_parts.append("\n\n--- Listing Details ---\n")
                content_parts.append(specs)
            
            if not content_parts:
                logger.warning(f"No content to save for listing {listing_id}")
                return None
            
            content = '\n'.join(content_parts)
            
            # Save to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Return relative path from project root
            relative_path = self._get_relative_path(filename)
            logger.info(f"Saved description file: {filename}")
            return relative_path
            
        except Exception as e:
            logger.error(f"Error saving description file for listing {listing_id}: {e}")
            return None
    
    def update_seller_description_in_sheet(self, row_idx, file_path):
        """
        Update the seller_description column for a specific row.
        
        Args:
            row_idx: Row index (1-based, including header)
            file_path: Relative path from project root (e.g., 'project/data/descriptions/p00001_seller_description.txt')
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Find seller_description column index
            header_row = self.worksheet.row_values(1)
            try:
                seller_desc_idx = header_row.index('seller_description')
            except ValueError:
                logger.warning("seller_description column not found in sheet. Creating it...")
                # Add seller_description column at the end
                self.worksheet.add_cols(1)
                header_row = self.worksheet.row_values(1)
                seller_desc_idx = len(header_row) - 1
                # Update header
                self.worksheet.update_cell(1, seller_desc_idx + 1, 'seller_description')
            
            # Update the cell (gspread uses 1-based indexing)
            self.worksheet.update_cell(row_idx, seller_desc_idx + 1, file_path)
            logger.info(f"Updated seller_description for row {row_idx} with path: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating seller_description in sheet for row {row_idx}: {e}")
            return False
    
    def scrape_listing_page(self, listing_url):
        """
        Scrape listing page and extract description and specs.
        
        Args:
            listing_url: URL of the listing page
            
        Returns:
            dict: Dictionary with 'description' and 'specs' keys, or None if failed
        """
        try:
            self.driver.get(listing_url)
            time.sleep(2)  # Wait for page to load
            
            # Get the fully rendered HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'lxml')
            
            # Extract description
            description = self.extract_seller_description(soup)
            
            # Extract specs
            specs = self.extract_listing_specs(soup)
            
            return {
                'description': description,
                'specs': specs
            }
            
        except Exception as e:
            logger.error(f"Error scraping listing page {listing_url}: {e}")
            return None
    
    def process_listing(self, listing, skip_existing=False):
        """
        Process a single listing: extract description/specs and save.
        
        Args:
            listing: Dict with 'id', 'source', 'row_idx' keys
            skip_existing: If True, skip if description file already exists
            
        Returns:
            dict: Summary with 'success', 'errors', 'file_path' keys
        """
        listing_id = listing['id']
        listing_url = listing['source']
        row_idx = listing.get('row_idx', None)
        
        logger.info(f"Processing listing {listing_id}: {listing_url}")
        
        # Check if file already exists
        if skip_existing:
            filename = f"{listing_id}_seller_description.txt"
            filepath = os.path.join(self.description_save_path, filename)
            if os.path.exists(filepath):
                logger.info(f"Skipping listing {listing_id} - description file already exists")
                relative_path = self._get_relative_path(filename)
                # Update sheet with existing path
                if row_idx:
                    self.update_seller_description_in_sheet(row_idx, relative_path)
                return {
                    'success': True,
                    'skipped': True,
                    'errors': [],
                    'file_path': relative_path
                }
        
        # Scrape listing page
        scraped_data = self.scrape_listing_page(listing_url)
        if not scraped_data:
            return {
                'success': False,
                'skipped': False,
                'errors': ['Failed to scrape listing page'],
                'file_path': None
            }
        
        description = scraped_data.get('description', '')
        specs = scraped_data.get('specs', '')
        
        # Check if we got any content
        if not description and not specs:
            logger.warning(f"No description or specs found for listing {listing_id}")
            return {
                'success': False,
                'skipped': False,
                'errors': ['No description or specs found'],
                'file_path': None
            }
        
        # Save to file
        file_path = self.save_description_file(listing_id, description, specs)
        if not file_path:
            return {
                'success': False,
                'skipped': False,
                'errors': ['Failed to save description file'],
                'file_path': None
            }
        
        # Update sheet with file path
        if row_idx:
            self.update_seller_description_in_sheet(row_idx, file_path)
        
        return {
            'success': True,
            'skipped': False,
            'errors': [],
            'file_path': file_path
        }
    
    def process_all_listings(self, listings, limit=None, skip_existing=False, batch_size=10):
        """
        Process all listings with progress tracking.
        
        Args:
            listings: List of listing dicts
            limit: Maximum number of listings to process (None for all)
            skip_existing: Skip listings where description file already exists
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
            'failed': failed
        }
        
        logger.info(f"\n{'='*50}")
        logger.info("Processing Summary:")
        logger.info(f"Total listings: {total}")
        logger.info(f"Processed: {processed}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Skipped: {skipped}")
        logger.info(f"Failed: {failed}")
        logger.info(f"{'='*50}")
        
        return summary


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Scrape seller descriptions and listing specs from Porsche listings in porsche_data sheet'
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
        help='Skip listings where description file already exists'
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
        logger.info("Initializing description scraper...")
        scraper = DescriptionScraper()
        
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

