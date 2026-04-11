"""Historical price matcher for finding similar BaT 2022 sold listings."""
import logging
import os
import statistics
import time
import pandas as pd
from condition_analyzer import ConditionAnalyzer
import config

logger = logging.getLogger(__name__)


class HistoricalMatcher:
    """Matches 2025 listings with 2020-2022 BaT sold listings using similarity rules."""

    def __init__(self):
        """Initialize the matcher with condition analyzer."""
        self._scraper = None
        self.condition_analyzer = ConditionAnalyzer()
        self.historical_listings = []
        os.makedirs(os.path.dirname(config.YEARS_AGO_CSV_PATH), exist_ok=True)

    @property
    def scraper(self):
        if self._scraper is None:
            from scraper import PorscheScraper
            self._scraper = PorscheScraper()
        return self._scraper

    def load_historical_listings_from_csv(self):
        """
        Load historical 2020-2022 listings from the years_ago CSV file.

        Returns:
            list: List of historical listings, or empty list if file doesn't exist or is empty
        """
        if not os.path.exists(config.YEARS_AGO_CSV_PATH):
            logger.warning(f"CSV not found at {config.YEARS_AGO_CSV_PATH}, will need to scrape")
            return []

        try:
            df = pd.read_csv(config.YEARS_AGO_CSV_PATH)
            if df.empty:
                logger.info("years_ago CSV is empty, will need to scrape")
                return []

            historical_listings = []
            for _, row in df.iterrows():
                listing = {col: (str(row[col]).strip() if pd.notna(row[col]) else '') for col in config.YEARS_AGO_COLUMNS if col in df.columns}

                # Convert sale_price to int if possible
                try:
                    if listing.get('sale_price'):
                        listing['sale_price'] = int(str(listing['sale_price']).replace(',', '').replace('$', ''))
                except (ValueError, AttributeError):
                    pass

                # Convert mileage to int if possible
                try:
                    if listing.get('mileage'):
                        listing['mileage'] = int(str(listing['mileage']).replace(',', ''))
                except (ValueError, AttributeError):
                    pass

                sale_date = listing.get('sale_date', '')
                if sale_date and (sale_date.startswith('2020') or sale_date.startswith('2021') or sale_date.startswith('2022')):
                    historical_listings.append(listing)
                else:
                    logger.debug(f"Skipping listing with sale_date '{sale_date}' (not 2020-2022)")

            logger.info(f"Loaded {len(historical_listings)} historical listings from CSV")
            self.historical_listings = historical_listings
            return historical_listings

        except Exception as e:
            logger.error(f"Error loading historical listings from CSV: {e}")
            return []

    def load_historical_listings_from_sheet(self):
        """Alias for load_historical_listings_from_csv (backwards compatibility)."""
        return self.load_historical_listings_from_csv()

    def _get_existing_sources(self):
        """
        Get set of existing source URLs from the years_ago CSV to avoid duplicates.

        Returns:
            set: Set of existing source URLs
        """
        existing_sources = set()
        if not os.path.exists(config.YEARS_AGO_CSV_PATH):
            return existing_sources
        try:
            df = pd.read_csv(config.YEARS_AGO_CSV_PATH)
            if 'source' in df.columns:
                existing_sources = set(df['source'].dropna().astype(str).str.strip())
        except Exception as e:
            logger.warning(f"Error reading existing sources: {e}")
        return existing_sources

    def save_historical_listings_batch(self, historical_listings):
        """
        Save a batch of historical listings to the years_ago CSV.

        Args:
            historical_listings: List of historical listing dicts to save
        """
        existing_sources = self._get_existing_sources()

        rows_to_add = []
        for listing in historical_listings:
            source = listing.get('source', '')
            if source and source not in existing_sources:
                rows_to_add.append({col: str(listing.get(col, '')) for col in config.YEARS_AGO_COLUMNS})
                existing_sources.add(source)

        if not rows_to_add:
            logger.debug("No new listings to save (all already exist in CSV)")
            return

        new_df = pd.DataFrame(rows_to_add, columns=config.YEARS_AGO_COLUMNS)
        write_header = not os.path.exists(config.YEARS_AGO_CSV_PATH)
        new_df.to_csv(config.YEARS_AGO_CSV_PATH, mode='a', header=write_header, index=False)
        logger.info(f"Saved {len(rows_to_add)} new listings to {config.YEARS_AGO_CSV_PATH}")

    def scrape_2022_listings(self, search_url, force_scrape=False):
        """
        Scrape BaT 2020-2022 sold listings from a search URL, or load from CSV if available.
        Saves listings in batches of 10 to the years_ago CSV.

        Args:
            search_url: URL to BaT search results page (should filter for sold listings)
            force_scrape: If True, force scraping even if data exists in CSV

        Returns:
            list: List of dicts with keys: model_year, model_type, mileage, condition, sale_price, sale_date
        """
        if not force_scrape:
            loaded_listings = self.load_historical_listings_from_csv()
            if loaded_listings:
                logger.info(f"Using {len(loaded_listings)} historical listings from CSV")
                return loaded_listings

        logger.info(f"Scraping 2020-2022 sold listings from: {search_url}")

        listing_urls = self.scraper.get_all_listing_urls_from_auction_results(search_url)
        logger.info(f"Found {len(listing_urls)} listing URLs to process")

        existing_sources = self._get_existing_sources()

        historical_listings = []
        batch_buffer = []
        batch_size = 10
        failed = 0
        accepted_count = 0

        for i, listing_url in enumerate(listing_urls, 1):
            logger.info(f"Scraping sold listing {i}/{len(listing_urls)}: {listing_url}")
            try:
                listing_data = self.scraper.scrape_sold_listing(listing_url)
                if listing_data:
                    if listing_data.get('should_exclude', False):
                        logger.info(f"Skipping listing with excluded keywords: {listing_url}")
                        failed += 1
                        continue

                    sale_date = listing_data.get('sale_date', '')
                    logger.debug(f"Listing {i}: sale_date='{sale_date}', model_year={listing_data.get('model_year')}, model_type={listing_data.get('model_type')}")

                    if sale_date and (sale_date.startswith('2020') or sale_date.startswith('2021') or sale_date.startswith('2022')):
                        source = listing_data.get('source', '')
                        if source in existing_sources:
                            logger.debug(f"Skipping listing already in CSV: {listing_url}")
                            continue

                        if listing_data.get('is_premium', False):
                            condition = "Excellent"
                        else:
                            description = listing_data.get('description', '')
                            condition = self.condition_analyzer.analyze_condition(description) if description else "Fair"

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
                        existing_sources.add(source)
                        accepted_count += 1

                        if len(batch_buffer) >= batch_size:
                            logger.info(f"Saving batch of {len(batch_buffer)} listings to CSV...")
                            self.save_historical_listings_batch(batch_buffer)
                            batch_buffer = []
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

        if batch_buffer:
            logger.info(f"Saving final batch of {len(batch_buffer)} listings to CSV...")
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

        try:
            target_year = int(target_year_str) if target_year_str else None
        except ValueError:
            target_year = None

        try:
            if isinstance(target_mileage, str):
                target_mileage = int(target_mileage.replace(',', '')) if target_mileage else 0
            elif not target_mileage:
                target_mileage = 0
        except (ValueError, AttributeError):
            target_mileage = 0

        filtered = []

        for listing in self.historical_listings:
            listing_model_type = listing.get('model_type', '').strip()
            if listing_model_type != target_model_type:
                continue

            listing_year_str = listing.get('model_year', '').strip()
            try:
                listing_year = int(listing_year_str) if listing_year_str else None
            except ValueError:
                continue

            if target_year is None or listing_year is None:
                continue

            if abs(target_year - listing_year) > 1:
                continue

            listing_mileage = listing.get('mileage', '')
            try:
                if isinstance(listing_mileage, str):
                    listing_mileage = int(listing_mileage.replace(',', '')) if listing_mileage else 0
                elif not listing_mileage:
                    listing_mileage = 0
            except (ValueError, AttributeError):
                listing_mileage = 0

            if target_mileage == 0 and listing_mileage == 0:
                pass
            elif target_mileage == 0 or listing_mileage == 0:
                continue
            else:
                mileage_diff = abs(target_mileage - listing_mileage) / max(target_mileage, listing_mileage)
                if mileage_diff > 0.15:
                    continue

            listing_condition = listing.get('condition', '').strip()
            if listing_condition != target_condition:
                continue

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
        target_year_str = target_listing.get('model_year', '').strip()
        comp_year_str = comp_listing.get('model_year', '').strip()

        try:
            target_year = int(target_year_str) if target_year_str else 0
            comp_year = int(comp_year_str) if comp_year_str else 0
            year_diff = abs(target_year - comp_year)
        except ValueError:
            year_diff = 10

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
                mileage_diff = 1.0
            else:
                mileage_diff = abs(target_mileage - comp_mileage) / max(target_mileage, comp_mileage)
        except (ValueError, AttributeError):
            mileage_diff = 1.0

        target_condition = target_listing.get('condition', '').strip()
        comp_condition = comp_listing.get('condition', '').strip()
        condition_penalty = 0 if target_condition == comp_condition else 1

        score = (year_diff * 1.0) + (mileage_diff * 2.0) + (condition_penalty * 3.0)
        return score

    def filter_loose_matches(self, target_listing, max_year_diff=5, max_mileage_pct=0.5, allow_condition_mismatch=True):
        """
        Filter historical listings with looser matching criteria for estimation.

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

        try:
            target_year = int(target_year_str) if target_year_str else None
        except ValueError:
            target_year = None

        try:
            if isinstance(target_mileage, str):
                target_mileage = int(target_mileage.replace(',', '')) if target_mileage else 0
            elif not target_mileage:
                target_mileage = 0
        except (ValueError, AttributeError):
            target_mileage = 0

        filtered = []

        for listing in self.historical_listings:
            listing_model_type = listing.get('model_type', '').strip()
            if listing_model_type != target_model_type:
                continue

            listing_year_str = listing.get('model_year', '').strip()
            try:
                listing_year = int(listing_year_str) if listing_year_str else None
            except ValueError:
                continue

            if target_year is not None and listing_year is not None:
                if abs(target_year - listing_year) > max_year_diff:
                    continue

            listing_mileage = listing.get('mileage', '')
            try:
                if isinstance(listing_mileage, str):
                    listing_mileage = int(listing_mileage.replace(',', '')) if listing_mileage else 0
                elif not listing_mileage:
                    listing_mileage = 0
            except (ValueError, AttributeError):
                listing_mileage = 0

            if target_mileage > 0 and listing_mileage > 0:
                mileage_diff = abs(target_mileage - listing_mileage) / max(target_mileage, listing_mileage)
                if mileage_diff > max_mileage_pct:
                    continue

            if not allow_condition_mismatch:
                listing_condition = listing.get('condition', '').strip()
                if listing_condition != target_condition:
                    continue

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
        criteria_levels = [
            {'max_year_diff': 3, 'max_mileage_pct': 0.3, 'allow_condition_mismatch': False},
            {'max_year_diff': 5, 'max_mileage_pct': 0.5, 'allow_condition_mismatch': True},
            {'max_year_diff': 10, 'max_mileage_pct': 1.0, 'allow_condition_mismatch': True},
            {'max_year_diff': 999, 'max_mileage_pct': 1.0, 'allow_condition_mismatch': True},
        ]

        for level, criteria in enumerate(criteria_levels, 1):
            loose_matches = self.filter_loose_matches(target_listing, **criteria)

            if len(loose_matches) == 0:
                continue

            scored_listings = []
            for comp in loose_matches:
                score = self.calculate_similarity_score(target_listing, comp)
                sale_price = comp.get('sale_price', '')
                if sale_price and isinstance(sale_price, (int, str)):
                    try:
                        if isinstance(sale_price, str):
                            sale_price = int(sale_price.replace(',', '').replace('$', ''))
                        scored_listings.append({'listing': comp, 'score': score, 'sale_price': sale_price})
                    except (ValueError, AttributeError):
                        continue

            if len(scored_listings) == 0:
                continue

            scored_listings.sort(key=lambda x: x['score'])
            top_matches = scored_listings[:5]
            prices = [item['sale_price'] for item in top_matches]

            if len(prices) == 0:
                continue

            if len(prices) == 1:
                estimate = prices[0]
            elif len(prices) == 2:
                estimate = int(sum(prices) / 2)
            else:
                estimate = int(statistics.median(prices))

            logger.info(f"Estimated price using level {level} criteria: {estimate} (from {len(prices)} matches)")
            return estimate

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
        similar_listings = self.filter_similar_listings(target_listing)

        if len(similar_listings) == 0:
            logger.info("No strict matches found, attempting estimation with looser criteria...")
            estimated_price = self.calculate_estimated_price(target_listing)
            if estimated_price is not None:
                return estimated_price
            return "insufficient_data"

        scored_listings = []
        for comp in similar_listings:
            score = self.calculate_similarity_score(target_listing, comp)
            sale_price = comp.get('sale_price', '')
            if sale_price and isinstance(sale_price, (int, str)):
                try:
                    if isinstance(sale_price, str):
                        sale_price = int(sale_price.replace(',', '').replace('$', ''))
                    scored_listings.append({'listing': comp, 'score': score, 'sale_price': sale_price})
                except (ValueError, AttributeError):
                    continue

        if len(scored_listings) == 0:
            logger.info("No valid prices in strict matches, attempting estimation...")
            estimated_price = self.calculate_estimated_price(target_listing)
            if estimated_price is not None:
                return estimated_price
            return "insufficient_data"

        scored_listings.sort(key=lambda x: x['score'])

        if len(scored_listings) == 1:
            return scored_listings[0]['sale_price']

        top_3 = scored_listings[:3]
        prices = [item['sale_price'] for item in top_3]

        if len(prices) == 1:
            return prices[0]
        elif len(prices) == 2:
            return int(sum(prices) / 2)
        else:
            return int(statistics.median(prices))
