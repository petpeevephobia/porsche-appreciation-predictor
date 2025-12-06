"""Main script to orchestrate scraping, analysis, and sheet writing."""
import argparse
import logging
import sys
import time
from scraper import PorscheScraper
from condition_analyzer import ConditionAnalyzer
from sheets_writer import SheetsWriter
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Scrape Porsche listings from bringatrailer.com and add to Google Sheet'
    )
    parser.add_argument(
        'url',
        help='URL of the bringatrailer.com search results page with all listings'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of listings to process before writing to sheet (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Validate configuration
    if not config.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set in environment variables")
        sys.exit(1)
    
    if not config.GOOGLE_SHEETS_CREDENTIALS_PATH:
        logger.error("GOOGLE_SHEETS_CREDENTIALS_PATH not set in environment variables")
        sys.exit(1)
    
    if not config.GOOGLE_SHEET_ID:
        logger.error("GOOGLE_SHEET_ID not set in environment variables")
        sys.exit(1)
    
    try:
        # Initialize components
        logger.info("Initializing components...")
        scraper = PorscheScraper()
        analyzer = ConditionAnalyzer()
        writer = SheetsWriter()
        
        # Step 1: Get all category URLs from the main page
        logger.info(f"Fetching category pages from: {args.url}")
        category_urls = scraper.get_all_category_urls(args.url)
        
        if not category_urls:
            logger.warning("No category pages found. Trying to scrape listings directly from URL...")
            # Fallback: try to scrape listings directly from the URL
            listing_urls = scraper.get_all_listing_urls(args.url)
        else:
            # Step 2: Get all listing URLs from each category
            logger.info(f"Found {len(category_urls)} category pages. Fetching listings from each...")
            listing_urls = []
            for i, category_url in enumerate(category_urls, 1):
                logger.info(f"Fetching listings from category {i}/{len(category_urls)}: {category_url}")
                category_listings = scraper.get_all_listing_urls(category_url)
                listing_urls.extend(category_listings)
                logger.info(f"Found {len(category_listings)} listings in this category. Total so far: {len(listing_urls)}")
                time.sleep(config.REQUEST_DELAY)
        
        if not listing_urls:
            logger.warning("No listing URLs found. Exiting.")
            return
        
        # Remove duplicates
        listing_urls = list(set(listing_urls))
        logger.info(f"Found {len(listing_urls)} unique listings to process")
        
        # Step 3: Scrape all listings first
        logger.info("Step 1: Scraping all listings...")
        all_listing_data = []
        failed = 0
        
        for i, listing_url in enumerate(listing_urls, 1):
            logger.info(f"Scraping listing {i}/{len(listing_urls)}: {listing_url}")
            try:
                listing_data = scraper.scrape_listing(listing_url)
                if listing_data:
                    # Skip Non-Running Project listings
                    if listing_data.get('is_non_running_project', False):
                        logger.info(f"Skipping Non-Running Project listing: {listing_url}")
                        failed += 1
                        continue
                    # Skip listings with excluded keywords (wheel, wheels, tool, seat, engine, gearbox)
                    if listing_data.get('should_exclude', False):
                        logger.info(f"Skipping listing with excluded keywords: {listing_url}")
                        failed += 1
                        continue
                    all_listing_data.append(listing_data)
                else:
                    logger.warning(f"Failed to scrape listing: {listing_url}")
                    failed += 1
                time.sleep(config.REQUEST_DELAY)
            except Exception as e:
                logger.error(f"Error scraping listing {listing_url}: {e}")
                failed += 1
                continue
        
        logger.info(f"Scraped {len(all_listing_data)} listings successfully")
        
        # Step 4: Analyze all conditions in batch
        logger.info("Step 2: Analyzing conditions in batch...")
        
        # Separate premium listings (automatically Excellent) from others
        premium_indices = []
        non_premium_data = []
        non_premium_indices = []
        
        for i, data in enumerate(all_listing_data):
            if data.get('is_premium', False):
                premium_indices.append(i)
                logger.debug(f"Listing {i} has Premium tag - will be marked as Excellent")
            else:
                non_premium_data.append(data)
                non_premium_indices.append(i)
        
        # Only analyze non-premium listings with OpenAI
        descriptions = [data['description'] for data in non_premium_data]
        if descriptions:
            conditions = analyzer.analyze_batch_parallel(descriptions)
        else:
            conditions = []
        
        # Step 5: Prepare and write data to sheet
        logger.info("Step 3: Writing to Google Sheet...")
        batch_data = []
        successful = 0
        
        # Create a mapping for conditions
        condition_map = {}
        for idx, condition in enumerate(conditions):
            original_idx = non_premium_indices[idx]
            condition_map[original_idx] = condition
        
        for i, listing_data in enumerate(all_listing_data):
            # Check if it's premium first
            if listing_data.get('is_premium', False):
                condition = "Excellent"
            elif i in condition_map:
                condition = condition_map[i]
            else:
                condition = "Good"  # Default fallback
            
            row_data = [
                listing_data['model_year'],
                listing_data['model_type'],
                listing_data['mileage'],
                condition,
                listing_data.get('price_now', ''),  # price_now
                "",  # price_3_years_ago
                "",  # appreciated
                listing_data['source']
            ]
            
            batch_data.append(row_data)
            
            # Write batch to sheet
            if len(batch_data) >= args.batch_size:
                added = writer.batch_append(batch_data)
                successful += added
                batch_data = []
                logger.info(f"Batch written. Total successful: {successful}")
        
        # Write remaining batch
        if batch_data:
            added = writer.batch_append(batch_data)
            successful += added
        
        # Summary
        logger.info("=" * 50)
        logger.info("Scraping completed!")
        logger.info(f"Total listings processed: {len(listing_urls)}")
        logger.info(f"Successfully added: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info("=" * 50)
        
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

