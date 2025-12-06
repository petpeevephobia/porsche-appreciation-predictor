"""Historical price matcher for finding similar BaT 2022 sold listings."""
import logging
import statistics
import time
import gspread
from google.oauth2.service_account import Credentials
from scraper import PorscheScraper
from condition_analyzer import ConditionAnalyzer
import config

logger = logging.getLogger(__name__)


class HistoricalMatcher:
    """Matches 2025 listings with 2020-2022 BaT sold listings using similarity rules."""
    
    def __init__(self):
        """Initialize the matcher with scraper and condition analyzer."""
        self.scraper = PorscheScraper()
        self.condition_analyzer = ConditionAnalyzer()
        self.historical_listings = []
        self._init_sheets_client()
    
    def _init_sheets_client(self):
        """Initialize Google Sheets client for old data sheet."""
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
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            self.sheets_client = None
            self.sheet = None
    
    def load_historical_listings_from_sheet(self):
        """
        Load historical 2020-2022 listings from years_ago sheet.
        
        Returns:
            list: List of historical listings, or empty list if sheet doesn't exist or is empty
        """
        if not self.sheet:
            logger.warning("Google Sheets client not initialized, cannot load from sheet")
            return []
        
        try:
            # Try to get the years_ago worksheet
            try:
                years_ago_worksheet = self.sheet.worksheet(config.YEARS_AGO_SHEET_NAME)
            except gspread.exceptions.WorksheetNotFound:
                logger.info(f"Sheet '{config.YEARS_AGO_SHEET_NAME}' not found, will need to scrape")
                return []
            
            # Read all rows
            all_rows = years_ago_worksheet.get_all_values()
            if len(all_rows) <= 1:  # Only header row or empty
                logger.info(f"Sheet '{config.YEARS_AGO_SHEET_NAME}' is empty, will need to scrape")
                return []
            
            # Parse rows into historical listings
            historical_listings = []
            columns = config.YEARS_AGO_COLUMNS
            
            for row in all_rows[1:]:  # Skip header
                if len(row) < len(columns):
                    continue
                
                historical_listing = {
                    'model_year': row[columns.index('model_year')].strip() if len(row) > columns.index('model_year') else '',
                    'model_type': row[columns.index('model_type')].strip() if len(row) > columns.index('model_type') else '',
                    'mileage': row[columns.index('mileage')].strip() if len(row) > columns.index('mileage') else '',
                    'condition': row[columns.index('condition')].strip() if len(row) > columns.index('condition') else '',
                    'sale_price': row[columns.index('sale_price')].strip() if len(row) > columns.index('sale_price') else '',
                    'sale_date': row[columns.index('sale_date')].strip() if len(row) > columns.index('sale_date') else '',
                    'source': row[columns.index('source')].strip() if len(row) > columns.index('source') else ''
                }
                
                # Convert sale_price to int if possible
                try:
                    if historical_listing['sale_price']:
                        historical_listing['sale_price'] = int(historical_listing['sale_price'].replace(',', '').replace('$', ''))
                except (ValueError, AttributeError):
                    pass
                
                # Convert mileage to int if possible
                try:
                    if historical_listing['mileage']:
                        historical_listing['mileage'] = int(historical_listing['mileage'].replace(',', ''))
                except (ValueError, AttributeError):
                    pass
                
                # Filter for 2020, 2021, or 2022 sales only
                sale_date = historical_listing.get('sale_date', '')
                if sale_date and (sale_date.startswith('2020') or sale_date.startswith('2021') or sale_date.startswith('2022')):
                    historical_listings.append(historical_listing)
                else:
                    logger.debug(f"Skipping listing with sale_date '{sale_date}' (not 2020-2022) when loading from sheet")
            
            logger.info(f"Loaded {len(historical_listings)} historical listings from '{config.YEARS_AGO_SHEET_NAME}' sheet")
            self.historical_listings = historical_listings
            return historical_listings
                        
        except Exception as e:
            logger.error(f"Error loading historical listings from sheet: {e}")
            return []
    
    def _get_or_create_years_ago_worksheet(self):
        """
        Get or create the years_ago worksheet.
        
        Returns:
            gspread.Worksheet: The years_ago worksheet, or None if error
        """
        if not self.sheet:
            logger.warning("Google Sheets client not initialized")
            return None
        
        try:
            # Get or create the years_ago worksheet
            try:
                years_ago_worksheet = self.sheet.worksheet(config.YEARS_AGO_SHEET_NAME)
            except gspread.exceptions.WorksheetNotFound:
                years_ago_worksheet = self.sheet.add_worksheet(
                    title=config.YEARS_AGO_SHEET_NAME,
                    rows=1000,
                    cols=len(config.YEARS_AGO_COLUMNS)
                )
                # Add header row
                years_ago_worksheet.append_row(config.YEARS_AGO_COLUMNS)
                logger.info(f"Created new worksheet: {config.YEARS_AGO_SHEET_NAME}")
            
            return years_ago_worksheet
        except Exception as e:
            logger.error(f"Error getting/creating years_ago worksheet: {e}")
            return None
    
    def _get_existing_sources_from_sheet(self, worksheet):
        """
        Get set of existing source URLs from the years_ago sheet to avoid duplicates.
        
        Args:
            worksheet: The years_ago worksheet
            
        Returns:
            set: Set of existing source URLs
        """
        existing_sources = set()
        try:
            existing_rows = worksheet.get_all_values()
            if len(existing_rows) > 1:  # Has data beyond header
                source_idx = config.YEARS_AGO_COLUMNS.index('source')
                for row in existing_rows[1:]:
                    if len(row) > source_idx:
                        existing_sources.add(row[source_idx].strip())
        except Exception as e:
            logger.warning(f"Error reading existing sources: {e}")
        return existing_sources
    
    def save_historical_listings_batch(self, historical_listings):
        """
        Save a batch of historical listings to years_ago sheet.
        
        Args:
            historical_listings: List of historical listing dicts to save
        """
        if not self.sheet:
            logger.warning("Google Sheets client not initialized, cannot save to sheet")
            return
        
        try:
            years_ago_worksheet = self._get_or_create_years_ago_worksheet()
            if not years_ago_worksheet:
                return
            
            # Get existing sources to avoid duplicates
            existing_sources = self._get_existing_sources_from_sheet(years_ago_worksheet)
            
            # Prepare rows to add (only new ones)
            rows_to_add = []
            for listing in historical_listings:
                source = listing.get('source', '')
                if source and source not in existing_sources:
                    row_data = [
                        str(listing.get('model_year', '')),
                        str(listing.get('model_type', '')),
                        str(listing.get('mileage', '')),
                        str(listing.get('condition', '')),
                        str(listing.get('sale_price', '')),
                        str(listing.get('sale_date', '')),
                        str(listing.get('source', ''))
                    ]
                    rows_to_add.append(row_data)
                    existing_sources.add(source)  # Track to avoid duplicates
            
            if rows_to_add:
                years_ago_worksheet.append_rows(rows_to_add)
                logger.info(f"Saved {len(rows_to_add)} new listings to '{config.YEARS_AGO_SHEET_NAME}' sheet")
            else:
                logger.debug("No new listings to save (all already exist in sheet)")
                
        except Exception as e:
            logger.error(f"Error saving historical listings batch to sheet: {e}")
    
    def scrape_2022_listings(self, search_url, force_scrape=False):
        """
        Scrape BaT 2020-2022 sold listings from a search URL, or load from sheet if available.
        Saves listings in batches of 10 to the years_ago sheet.
        
        Args:
            search_url: URL to BaT search results page (should filter for sold listings)
            force_scrape: If True, force scraping even if data exists in sheet
            
        Returns:
            list: List of dicts with keys: model_year, model_type, mileage, condition, sale_price, sale_date
        """
        # Try to load from sheet first (unless force_scrape is True)
        if not force_scrape:
            loaded_listings = self.load_historical_listings_from_sheet()
            if loaded_listings:
                logger.info(f"Using {len(loaded_listings)} historical listings from '{config.YEARS_AGO_SHEET_NAME}' sheet")
                return loaded_listings
        
        logger.info(f"Scraping 2020-2022 sold listings from: {search_url}")
        
        # Get all listing URLs (scoped to "Porsche Auction Results" section)
        listing_urls = self.scraper.get_all_listing_urls_from_auction_results(search_url)
        logger.info(f"Found {len(listing_urls)} listing URLs to process")
        
        # Initialize the years_ago worksheet
        years_ago_worksheet = self._get_or_create_years_ago_worksheet()
        if not years_ago_worksheet:
            logger.error("Cannot proceed: failed to initialize years_ago worksheet")
            return []
        
        # Get existing sources to avoid duplicates
        existing_sources = self._get_existing_sources_from_sheet(years_ago_worksheet)
        
        historical_listings = []
        batch_buffer = []  # Buffer to accumulate listings before saving
        batch_size = 10
        failed = 0
        accepted_count = 0
        
        for i, listing_url in enumerate(listing_urls, 1):
            logger.info(f"Scraping sold listing {i}/{len(listing_urls)}: {listing_url}")
            try:
                listing_data = self.scraper.scrape_sold_listing(listing_url)
                if listing_data:
                    # Skip listings with excluded keywords (wheel, wheels, tool, seat, engine, gearbox)
                    if listing_data.get('should_exclude', False):
                        logger.info(f"Skipping listing with excluded keywords: {listing_url}")
                        failed += 1
                        continue
                    
                    # Filter for 2020, 2021, or 2022 sales
                    sale_date = listing_data.get('sale_date', '')
                    logger.debug(f"Listing {i}: sale_date='{sale_date}', model_year={listing_data.get('model_year')}, model_type={listing_data.get('model_type')}")
                    
                    if sale_date and (sale_date.startswith('2020') or sale_date.startswith('2021') or sale_date.startswith('2022')):
                        # Skip if already in sheet
                        source = listing_data.get('source', '')
                        if source in existing_sources:
                            logger.debug(f"Skipping listing already in sheet: {listing_url}")
                            continue
                        
                        # Determine condition (use Premium tag or analyze description)
                        if listing_data.get('is_premium', False):
                            condition = "Excellent"
                        else:
                            description = listing_data.get('description', '')
                            if description:
                                condition = self.condition_analyzer.analyze_condition(description)
                            else:
                                condition = "Fair"  # Default
                        
                        historical_listing = {
                            'model_year': listing_data.get('model_year', ''),
                            'model_type': listing_data.get('model_type', ''),
                            'mileage': listing_data.get('mileage', ''),
                            'condition': condition,
                            'sale_price': listing_data.get('sale_price', ''),
                            'sale_date': sale_date,
                            'source': listing_data.get('source', '')
                        }
                        historical_listings.append(historical_listing)
                        batch_buffer.append(historical_listing)
                        existing_sources.add(source)  # Track to avoid duplicates
                        accepted_count += 1
                        
                        # Save batch of 10 to sheet
                        if len(batch_buffer) >= batch_size:
                            logger.info(f"Saving batch of {len(batch_buffer)} listings to '{config.YEARS_AGO_SHEET_NAME}' sheet...")
                            self.save_historical_listings_batch(batch_buffer)
                            batch_buffer = []  # Clear buffer
                    else:
                        logger.info(f"Skipping listing with sale_date '{sale_date}' (not 2020-2022): {listing_url}")
                else:
                    logger.warning(f"Failed to scrape listing: {listing_url}")
                    failed += 1
                
                time.sleep(config.REQUEST_DELAY)
            except Exception as e:
                logger.error(f"Error scraping listing {listing_url}: {e}")
                failed += 1
                continue
        
        # Save any remaining listings in buffer
        if batch_buffer:
            logger.info(f"Saving final batch of {len(batch_buffer)} listings to '{config.YEARS_AGO_SHEET_NAME}' sheet...")
            self.save_historical_listings_batch(batch_buffer)
        
        logger.info(f"Scraped {len(historical_listings)} 2020-2022 sold listings successfully")
        logger.info(f"Summary: {len(listing_urls)} total URLs found, {accepted_count} had valid 2020-2022 sale dates, {failed} failed/excluded")
        self.historical_listings = historical_listings
        
        return historical_listings
    
    def filter_similar_listings(self, target_listing):
        """
        Filter historical listings that match similarity criteria.
        
        Args:
            target_listing: dict with keys: model_year, model_type, mileage, condition
            
        Returns:
            list: Filtered historical listings that match criteria
        """
        target_model_type = target_listing.get('model_type', '').strip()
        target_year_str = target_listing.get('model_year', '').strip()
        target_mileage = target_listing.get('mileage', '')
        target_condition = target_listing.get('condition', '').strip()
        
        # Convert year to int if possible
        try:
            target_year = int(target_year_str) if target_year_str else None
        except ValueError:
            target_year = None
        
        # Convert mileage to int if possible
        try:
            if isinstance(target_mileage, str):
                target_mileage = int(target_mileage.replace(',', '')) if target_mileage else 0
            elif not target_mileage:
                target_mileage = 0
        except (ValueError, AttributeError):
            target_mileage = 0
        
        filtered = []
        
        for listing in self.historical_listings:
            # Same model_type (exact match required)
            listing_model_type = listing.get('model_type', '').strip()
            if listing_model_type != target_model_type:
                continue
            
            # Model year within ±1
            listing_year_str = listing.get('model_year', '').strip()
            try:
                listing_year = int(listing_year_str) if listing_year_str else None
            except ValueError:
                continue
            
            if target_year is None or listing_year is None:
                continue
            
            if abs(target_year - listing_year) > 1:
                continue
            
            # Mileage within ±15%
            listing_mileage = listing.get('mileage', '')
            try:
                if isinstance(listing_mileage, str):
                    listing_mileage = int(listing_mileage.replace(',', '')) if listing_mileage else 0
                elif not listing_mileage:
                    listing_mileage = 0
            except (ValueError, AttributeError):
                listing_mileage = 0
            
            # Handle edge case: if both are 0 or one is 0, skip mileage filter
            if target_mileage == 0 and listing_mileage == 0:
                pass  # Both 0, allow match
            elif target_mileage == 0 or listing_mileage == 0:
                continue  # One is 0, other isn't - skip
            else:
                # Calculate percentage difference
                mileage_diff = abs(target_mileage - listing_mileage) / max(target_mileage, listing_mileage)
                if mileage_diff > 0.15:  # More than 15% difference
                    continue
            
            # Same condition category
            listing_condition = listing.get('condition', '').strip()
            if listing_condition != target_condition:
                continue
            
            # All criteria met, add to filtered list
            filtered.append(listing)
        
        return filtered
    
    def calculate_similarity_score(self, target_listing, comp_listing):
        """
        Calculate similarity score between target and comp listing.
        Lower score = better match.
        
        Args:
            target_listing: dict with model_year, mileage, condition
            comp_listing: dict with model_year, mileage, condition, sale_price
            
        Returns:
            float: Similarity score (lower is better)
        """
        # Year difference
        target_year_str = target_listing.get('model_year', '').strip()
        comp_year_str = comp_listing.get('model_year', '').strip()
        
        try:
            target_year = int(target_year_str) if target_year_str else 0
            comp_year = int(comp_year_str) if comp_year_str else 0
            year_diff = abs(target_year - comp_year)
        except ValueError:
            year_diff = 10  # Large penalty if can't parse
        
        # Mileage difference (normalized)
        target_mileage = target_listing.get('mileage', '')
        comp_mileage = comp_listing.get('mileage', '')
        
        try:
            if isinstance(target_mileage, str):
                target_mileage = int(target_mileage.replace(',', '')) if target_mileage else 0
            elif not target_mileage:
                target_mileage = 0
            
            if isinstance(comp_mileage, str):
                comp_mileage = int(comp_mileage.replace(',', '')) if comp_mileage else 0
            elif not comp_mileage:
                comp_mileage = 0
            
            if target_mileage == 0 and comp_mileage == 0:
                mileage_diff = 0
            elif target_mileage == 0 or comp_mileage == 0:
                mileage_diff = 1.0  # Large penalty
            else:
                mileage_diff = abs(target_mileage - comp_mileage) / max(target_mileage, comp_mileage)
        except (ValueError, AttributeError):
            mileage_diff = 1.0  # Large penalty
        
        # Condition match (0 if match, 1 if mismatch)
        target_condition = target_listing.get('condition', '').strip()
        comp_condition = comp_listing.get('condition', '').strip()
        condition_penalty = 0 if target_condition == comp_condition else 1
        
        # Weighted combination
        # Year: weight 1.0, Mileage: weight 2.0, Condition: weight 3.0
        score = (year_diff * 1.0) + (mileage_diff * 2.0) + (condition_penalty * 3.0)
        
        return score
    
    def filter_loose_matches(self, target_listing, max_year_diff=5, max_mileage_pct=0.5, allow_condition_mismatch=True):
        """
        Filter historical listings with looser matching criteria for estimation.
        Uses progressively looser criteria to find any relevant matches.
        
        Args:
            target_listing: dict with keys: model_year, model_type, mileage, condition
            max_year_diff: Maximum year difference allowed (default: 5)
            max_mileage_pct: Maximum mileage percentage difference (default: 0.5 = 50%)
            allow_condition_mismatch: Whether to allow different conditions (default: True)
            
        Returns:
            list: Filtered historical listings that match loose criteria
        """
        target_model_type = target_listing.get('model_type', '').strip()
        target_year_str = target_listing.get('model_year', '').strip()
        target_mileage = target_listing.get('mileage', '')
        target_condition = target_listing.get('condition', '').strip()
        
        # Convert year to int if possible
        try:
            target_year = int(target_year_str) if target_year_str else None
        except ValueError:
            target_year = None
        
        # Convert mileage to int if possible
        try:
            if isinstance(target_mileage, str):
                target_mileage = int(target_mileage.replace(',', '')) if target_mileage else 0
            elif not target_mileage:
                target_mileage = 0
        except (ValueError, AttributeError):
            target_mileage = 0
        
        filtered = []
        
        for listing in self.historical_listings:
            # Same model_type (still required for relevance)
            listing_model_type = listing.get('model_type', '').strip()
            if listing_model_type != target_model_type:
                continue
            
            # Model year within max_year_diff
            listing_year_str = listing.get('model_year', '').strip()
            try:
                listing_year = int(listing_year_str) if listing_year_str else None
            except ValueError:
                continue
            
            if target_year is not None and listing_year is not None:
                if abs(target_year - listing_year) > max_year_diff:
                    continue
            
            # Mileage within max_mileage_pct (if both have mileage)
            listing_mileage = listing.get('mileage', '')
            try:
                if isinstance(listing_mileage, str):
                    listing_mileage = int(listing_mileage.replace(',', '')) if listing_mileage else 0
                elif not listing_mileage:
                    listing_mileage = 0
            except (ValueError, AttributeError):
                listing_mileage = 0
            
            # Only filter by mileage if both have valid mileage values
            if target_mileage > 0 and listing_mileage > 0:
                mileage_diff = abs(target_mileage - listing_mileage) / max(target_mileage, listing_mileage)
                if mileage_diff > max_mileage_pct:
                    continue
            
            # Condition check (optional)
            if not allow_condition_mismatch:
                listing_condition = listing.get('condition', '').strip()
                if listing_condition != target_condition:
                    continue
            
            # All criteria met, add to filtered list
            filtered.append(listing)
        
        return filtered

    def calculate_estimated_price(self, target_listing):
        """
        Calculate estimated price using progressively looser matching criteria.
        Used as fallback when strict matching returns insufficient_data.
        
        Args:
            target_listing: dict with model_year, model_type, mileage, condition
            
        Returns:
            int: Estimated price, or None if no matches found even with loose criteria
        """
        # Try progressively looser criteria
        criteria_levels = [
            {'max_year_diff': 3, 'max_mileage_pct': 0.3, 'allow_condition_mismatch': False},  # Level 1: Slightly loose
            {'max_year_diff': 5, 'max_mileage_pct': 0.5, 'allow_condition_mismatch': True},  # Level 2: Medium loose
            {'max_year_diff': 10, 'max_mileage_pct': 1.0, 'allow_condition_mismatch': True},  # Level 3: Very loose
            {'max_year_diff': 999, 'max_mileage_pct': 1.0, 'allow_condition_mismatch': True},  # Level 4: Same model only
        ]
        
        for level, criteria in enumerate(criteria_levels, 1):
            loose_matches = self.filter_loose_matches(target_listing, **criteria)
            
            if len(loose_matches) == 0:
                continue
            
            # Calculate similarity scores and get prices
            scored_listings = []
            for comp in loose_matches:
                score = self.calculate_similarity_score(target_listing, comp)
                sale_price = comp.get('sale_price', '')
                if sale_price and isinstance(sale_price, (int, str)):
                    try:
                        if isinstance(sale_price, str):
                            sale_price = int(sale_price.replace(',', '').replace('$', ''))
                        scored_listings.append({
                            'listing': comp,
                            'score': score,
                            'sale_price': sale_price
                        })
                    except (ValueError, AttributeError):
                        continue
            
            if len(scored_listings) == 0:
                continue
            
            # Sort by score (ascending - lower is better)
            scored_listings.sort(key=lambda x: x['score'])
            
            # Use median of top 5 matches (more matches for estimation)
            top_matches = scored_listings[:5]
            prices = [item['sale_price'] for item in top_matches]
            
            if len(prices) == 0:
                continue
            
            # Calculate estimate
            if len(prices) == 1:
                estimate = prices[0]
            elif len(prices) == 2:
                estimate = int(sum(prices) / 2)
            else:
                estimate = int(statistics.median(prices))
            
            logger.info(f"Estimated price using level {level} criteria: {estimate} (from {len(prices)} matches)")
            return estimate
        
        # No matches found even with very loose criteria
        return None
    
    def calculate_price_3_years_ago(self, target_listing):
        """
        Calculate price_3_years_ago for a target listing by finding best matches.
        Falls back to estimation if strict matching fails.
        
        Args:
            target_listing: dict with model_year, model_type, mileage, condition
            
        Returns:
            str or int: Sale price (int) if match found, estimated price if fallback used, "insufficient_data" if no matches
        """
        # Filter similar listings with strict criteria
        similar_listings = self.filter_similar_listings(target_listing)
        
        if len(similar_listings) == 0:
            # Try fallback estimation with looser criteria
            logger.info("No strict matches found, attempting estimation with looser criteria...")
            estimated_price = self.calculate_estimated_price(target_listing)
            if estimated_price is not None:
                return estimated_price
            return "insufficient_data"
        
        # Calculate similarity scores
        scored_listings = []
        for comp in similar_listings:
            score = self.calculate_similarity_score(target_listing, comp)
            sale_price = comp.get('sale_price', '')
            # Only include listings with valid sale prices
            if sale_price and isinstance(sale_price, (int, str)):
                try:
                    if isinstance(sale_price, str):
                        sale_price = int(sale_price.replace(',', '').replace('$', ''))
                    scored_listings.append({
                        'listing': comp,
                        'score': score,
                        'sale_price': sale_price
                    })
                except (ValueError, AttributeError):
                    continue  # Skip invalid prices
        
        if len(scored_listings) == 0:
            # Try fallback estimation
            logger.info("No valid prices in strict matches, attempting estimation...")
            estimated_price = self.calculate_estimated_price(target_listing)
            if estimated_price is not None:
                return estimated_price
            return "insufficient_data"
        
        # Sort by score (ascending - lower is better)
        scored_listings.sort(key=lambda x: x['score'])
        
        # If 1 match, use its price
        if len(scored_listings) == 1:
            return scored_listings[0]['sale_price']
        
        # If 2+ matches, use median of top 3
        top_3 = scored_listings[:3]
        prices = [item['sale_price'] for item in top_3]
        
        if len(prices) == 1:
            return prices[0]
        elif len(prices) == 2:
            # For 2 prices, return average
            return int(sum(prices) / 2)
        else:
            # For 3+ prices, return median
            return int(statistics.median(prices))

