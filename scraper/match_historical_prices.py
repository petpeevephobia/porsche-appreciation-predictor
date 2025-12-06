"""Standalone script to match historical prices for existing Google Sheet rows."""
import argparse
import logging
import sys
import time
from historical_matcher import HistoricalMatcher
from sheets_writer import SheetsWriter
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('historical_matcher.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def count_empty_rows(writer, price_3_years_ago_idx, include_insufficient_data=False):
    """
    Count how many rows have empty price_3_years_ago column.
    
    Args:
        writer: SheetsWriter instance
        price_3_years_ago_idx: Column index for price_3_years_ago
        include_insufficient_data: If True, also count rows with "insufficient_data" as empty
        
    Returns:
        int: Number of empty rows
    """
    try:
        all_rows = writer.worksheet.get_all_values()
        if len(all_rows) <= 1:
            return 0
        
        empty_count = 0
        for row in all_rows[1:]:  # Skip header
            if len(row) <= price_3_years_ago_idx or not row[price_3_years_ago_idx].strip():
                empty_count += 1
            elif include_insufficient_data and row[price_3_years_ago_idx].strip() == "insufficient_data":
                empty_count += 1
        
        return empty_count
    except Exception as e:
        logger.error(f"Error counting empty rows: {e}")
        return 0


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Match historical BaT 2020-2022 prices for existing Google Sheet rows'
    )
    parser.add_argument(
        '--bat-search-url',
        type=str,
        default='https://bringatrailer.com/search/?q=porsche&sold=1',
        help='URL to BaT search results page for 2020-2022 sold listings (default: search with sold filter)'
    )
    parser.add_argument(
        '--skip-scraping',
        action='store_true',
        help='Skip scraping step (load from years_ago sheet if available)'
    )
    parser.add_argument(
        '--force-scrape',
        action='store_true',
        help='Force scraping even if data exists in years_ago sheet'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of rows to update before pausing (default: 10)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit processing to first N rows (useful for testing, default: process all rows)'
    )
    parser.add_argument(
        '--retry-delay',
        type=int,
        default=60,
        help='Seconds to wait between retry iterations when quota is hit (default: 60)'
    )
    parser.add_argument(
        '--max-retries',
        type=int,
        default=None,
        help='Maximum number of retry iterations (default: unlimited)'
    )
    parser.add_argument(
        '--only-insufficient-data',
        action='store_true',
        help='Only process rows that currently have "insufficient_data" in price_3_years_ago column'
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
        # Initialize components
        logger.info("Initializing components...")
        matcher = HistoricalMatcher()
        writer = SheetsWriter()
        
        # Step 1: Load or scrape 2020-2022 sold listings
        if args.skip_scraping:
            logger.info("Step 1: Loading historical listings from years_ago sheet...")
            historical_listings = matcher.load_historical_listings_from_sheet()
            if not historical_listings:
                logger.warning("No historical listings found in sheet. Run without --skip-scraping to scrape.")
                sys.exit(1)
            logger.info(f"Loaded {len(historical_listings)} historical listings from sheet")
        else:
            logger.info("Step 1: Loading/scraping BaT 2020-2022 sold listings...")
            historical_listings = matcher.scrape_2022_listings(args.bat_search_url, force_scrape=args.force_scrape)
            logger.info(f"Using {len(historical_listings)} 2020-2022 sold listings")
        
        # Get column indices
        columns = config.COLUMNS
        try:
            model_year_idx = columns.index('model_year')
            model_type_idx = columns.index('model_type')
            mileage_idx = columns.index('mileage')
            condition_idx = columns.index('condition')
            price_3_years_ago_idx = columns.index('price_3_years_ago')
        except ValueError as e:
            logger.error(f"Column not found in config: {e}")
            sys.exit(1)
        
        # Main retry loop - continue until all rows are filled
        iteration = 0
        total_processed = 0
        total_insufficient_data = 0
        
        while True:
            iteration += 1
            logger.info("=" * 50)
            logger.info(f"ITERATION {iteration}")
            logger.info("=" * 50)
            
            if args.max_retries and iteration > args.max_retries:
                logger.info(f"Reached maximum retry limit ({args.max_retries})")
                break
            
            # Check how many empty rows remain
            empty_count = count_empty_rows(writer, price_3_years_ago_idx, include_insufficient_data=True)
            logger.info(f"Empty rows remaining: {empty_count}")
            
            if empty_count == 0:
                logger.info("All rows are filled! Exiting.")
                break
            
            # Step 2: Read existing rows from Google Sheet
            logger.info("Step 2: Reading existing rows from Google Sheet...")
            all_rows = writer.worksheet.get_all_values()
            
            if len(all_rows) <= 1:
                logger.warning("No data rows found in sheet (only header row)")
                break
            
            # Step 3: Process rows and calculate price_3_years_ago
            logger.info("Step 3: Processing rows and calculating price_3_years_ago...")
            if args.limit:
                logger.info(f"Limiting processing to first {args.limit} rows (testing mode)")
            rows_to_update = []
            processed = 0
            skipped = 0
            insufficient_data = 0
            
            # Limit rows if --limit is specified
            rows_to_process = all_rows[1:args.limit+1] if args.limit else all_rows[1:]
            
            for row_idx, row in enumerate(rows_to_process, start=2):  # Start at row 2 (skip header)
                # Check if price_3_years_ago is already filled
                if len(row) > price_3_years_ago_idx and row[price_3_years_ago_idx].strip():
                    current_value = row[price_3_years_ago_idx].strip()
                    
                    # If --only-insufficient-data flag is set, only process "insufficient_data" rows
                    if args.only_insufficient_data:
                        if current_value != "insufficient_data":
                            skipped += 1
                            continue
                        else:
                            logger.info(f"Row {row_idx} has 'insufficient_data', attempting estimation...")
                    else:
                        # Normal mode: skip if it's a valid number, but process if it's "insufficient_data"
                        if current_value != "insufficient_data":
                            skipped += 1
                            continue
                        else:
                            logger.info(f"Row {row_idx} has 'insufficient_data', attempting estimation...")
                
                # Extract target listing data
                if len(row) <= max(model_year_idx, model_type_idx, mileage_idx, condition_idx):
                    logger.warning(f"Row {row_idx} has insufficient columns, skipping")
                    skipped += 1
                    continue
                
                target_listing = {
                    'model_year': row[model_year_idx].strip() if len(row) > model_year_idx else '',
                    'model_type': row[model_type_idx].strip() if len(row) > model_type_idx else '',
                    'mileage': row[mileage_idx].strip() if len(row) > mileage_idx else '',
                    'condition': row[condition_idx].strip() if len(row) > condition_idx else ''
                }
                
                # Skip if essential fields are missing
                if not target_listing['model_type'] or not target_listing['model_year']:
                    logger.warning(f"Row {row_idx} missing model_type or model_year, skipping")
                    skipped += 1
                    continue
                
                # Calculate price_3_years_ago
                logger.info(f"Processing row {row_idx}: {target_listing['model_year']} {target_listing['model_type']}")
                price_3_years_ago = matcher.calculate_price_3_years_ago(target_listing)
                
                if price_3_years_ago == "insufficient_data":
                    insufficient_data += 1
                    total_insufficient_data += 1
                    logger.info(f"Row {row_idx}: insufficient_data - no matching comps found")
                    # Still update with "insufficient_data" so we know it was processed
                    rows_to_update.append({
                        'row': row_idx,
                        'price_3_years_ago': "insufficient_data"
                    })
                else:
                    logger.info(f"Row {row_idx}: Found price_3_years_ago = {price_3_years_ago}")
                    rows_to_update.append({
                        'row': row_idx,
                        'price_3_years_ago': price_3_years_ago
                    })
                
                processed += 1
                total_processed += 1
                
                # Batch update to sheet
                if len(rows_to_update) >= args.batch_size:
                    success = _update_sheet_batch(writer, rows_to_update, price_3_years_ago_idx)
                    if success:
                        rows_to_update = []
                        logger.info(f"Updated batch. Processed: {processed}, Skipped: {skipped}, Insufficient data: {insufficient_data}")
                    else:
                        # If batch update failed, wait and retry this batch
                        logger.warning("Batch update failed, will retry in next iteration")
                        break  # Break out of row processing loop to retry
            
            # Update remaining rows
            if rows_to_update:
                success = _update_sheet_batch(writer, rows_to_update, price_3_years_ago_idx)
                if not success:
                    logger.warning("Final batch update failed, will retry in next iteration")
            
            # Summary for this iteration
            logger.info("=" * 50)
            logger.info(f"Iteration {iteration} completed!")
            logger.info(f"This iteration - Processed: {processed}, Skipped: {skipped}, Insufficient data: {insufficient_data}")
            logger.info(f"Total across all iterations - Processed: {total_processed}, Insufficient data: {total_insufficient_data}")
            logger.info("=" * 50)
            
            # Check if we should continue
            empty_count_after = count_empty_rows(writer, price_3_years_ago_idx, include_insufficient_data=True)
            if empty_count_after == 0:
                logger.info("All rows are filled! Exiting.")
                break
            
            # Wait before next iteration (to handle quota limits)
            if empty_count_after < empty_count:  # Made progress
                logger.info(f"Waiting {args.retry_delay} seconds before next iteration...")
                time.sleep(args.retry_delay)
            else:
                # No progress made, might be stuck - wait longer
                logger.warning("No progress made this iteration, waiting longer...")
                time.sleep(args.retry_delay * 2)
        
        # Final summary
        logger.info("=" * 50)
        logger.info("Historical price matching completed!")
        final_empty = count_empty_rows(writer, price_3_years_ago_idx, include_insufficient_data=True)
        logger.info(f"Final empty rows: {final_empty}")
        logger.info(f"Total iterations: {iteration}")
        logger.info(f"Total processed: {total_processed}")
        logger.info(f"Total insufficient data: {total_insufficient_data}")
        logger.info("=" * 50)
        
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Clean up scraper
        if 'matcher' in locals() and hasattr(matcher, 'scraper'):
            try:
                matcher.scraper.__del__()
            except:
                pass


def _update_sheet_batch(writer, rows_to_update, price_3_years_ago_idx, max_retries=3):
    """
    Update a batch of rows in the Google Sheet with retry logic.
    
    Args:
        writer: SheetsWriter instance
        rows_to_update: List of dicts with 'row' and 'price_3_years_ago' keys
        price_3_years_ago_idx: Column index for price_3_years_ago
        max_retries: Maximum number of retry attempts
        
    Returns:
        bool: True if successful, False if failed after retries
    """
    for attempt in range(max_retries):
        try:
            for item in rows_to_update:
                row_num = item['row']
                price_value = item['price_3_years_ago']
                
                # Convert to string for sheet
                if isinstance(price_value, int):
                    price_str = str(price_value)
                else:
                    price_str = str(price_value)
                
                # Update the cell (using 1-based indexing for gspread)
                # Column is price_3_years_ago_idx + 1 (gspread uses 1-based)
                writer.worksheet.update_cell(row_num, price_3_years_ago_idx + 1, price_str)
                time.sleep(0.1)  # Small delay to avoid rate limits
            
            logger.info(f"Updated {len(rows_to_update)} rows in sheet")
            return True
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "Quota exceeded" in error_str or "rateLimitExceeded" in error_str:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 30  # Exponential backoff: 30s, 60s, 90s
                    logger.warning(f"Quota exceeded (attempt {attempt + 1}/{max_retries}). Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Quota exceeded after {max_retries} attempts. Will retry in next iteration.")
                    return False
            else:
                logger.error(f"Error updating sheet batch: {e}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    return False
    
    return False


if __name__ == "__main__":
    main()

