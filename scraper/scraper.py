"""Web scraper for bringatrailer.com Porsche listings."""
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import re
import logging
from urllib.parse import urljoin, urlparse
import config

logger = logging.getLogger(__name__)


class PorscheScraper:
    """Scrapes Porsche listings from bringatrailer.com."""
    
    def __init__(self):
        """Initialize the scraper with headers and Selenium driver."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.base_url = config.BASE_URL
        
        # Initialize Selenium Chrome driver
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # Run in background
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
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
    
    def _ensure_driver_alive(self):
        """
        Check if driver is still alive, and reinitialize if needed.
        
        Returns:
            bool: True if driver is alive (or was successfully reinitialized), False otherwise
        """
        try:
            # Try a simple operation to check if driver is alive
            _ = self.driver.current_url
            return True
        except Exception as e:
            logger.warning(f"Driver session appears dead: {e}. Reinitializing...")
            try:
                # Close the dead driver
                try:
                    self.driver.quit()
                except:
                    pass
                
                # Reinitialize Chrome driver
                chrome_options = Options()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
                
                self.driver = webdriver.Chrome(options=chrome_options)
                logger.info("Driver successfully reinitialized")
                return True
            except Exception as e2:
                logger.error(f"Failed to reinitialize driver: {e2}")
                return False
    
    def get_all_category_urls(self, main_url):
        """
        Extract all category URLs from the main Porsche models page.
        
        Args:
            main_url: URL of the main page with category cards
        
        Returns:
            list: List of category URLs
        """
        category_urls = []
        try:
            logger.info(f"Fetching category pages from: {main_url}")
            self.driver.get(main_url)
            
            # Wait for page to load
            time.sleep(3)
            
            # Get the fully rendered HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'lxml')
            
            # Find the PorscheModels header/section
            porsche_models_header = soup.find(string=re.compile(r'PorscheModels', re.I))
            if not porsche_models_header:
                # Try alternative: look for header containing "Porsche" and "Models"
                porsche_models_header = soup.find(['h1', 'h2', 'h3'], string=re.compile(r'Porsche.*Models?', re.I))
            
            # Find all category-card-link elements
            category_links = soup.find_all('a', class_='category-card-link')
            
            # If we found a header, try to get links within that section
            if porsche_models_header:
                parent_section = porsche_models_header.find_parent(['section', 'div', 'article'])
                if parent_section:
                    category_links = parent_section.find_all('a', class_='category-card-link')
            
            for link in category_links:
                href = link.get('href')
                if href:
                    full_url = urljoin(self.base_url, href)
                    if full_url not in category_urls:
                        category_urls.append(full_url)
            
            logger.info(f"Found {len(category_urls)} category pages")
            return category_urls
            
        except Exception as e:
            logger.error(f"Error fetching category pages: {e}")
            return []
    
    def get_all_listing_urls(self, search_url):
        """
        Extract all listing URLs from paginated search results.
        
        Args:
            search_url: URL of the search results page
        
        Returns:
            list: List of listing URLs
        """
        listing_urls = []
        current_url = search_url
        page_num = 1
        
        while current_url:
            logger.info(f"Scraping page {page_num}: {current_url}")
            try:
                # Use Selenium to get JavaScript-rendered content
                self.driver.get(current_url)
                
                # Wait for listings to load (wait for listing-card elements)
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'a.listing-card'))
                    )
                except:
                    # If specific elements don't appear, wait a bit anyway
                    time.sleep(3)
                
                # Get the fully rendered HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, 'lxml')
                
                # Find all listing links using CSS selector (no heading scope)
                listing_links = soup.select('a.listing-card[href*="/listing/"][href*="porsche"]')
                
                # Fallback: if CSS selector doesn't work, try the old method
                if not listing_links:
                    listing_links = soup.find_all('a', class_=re.compile('listing-card'))
                    listing_links = [link for link in listing_links
                                     if link.get('href')
                                     and '/listing/' in link.get('href')
                                     and 'porsche' in link.get('href').lower()]
                
                logger.debug(f"Found {len(listing_links)} listing links on page {page_num}")
                
                for link in listing_links:
                    href = link.get('href')
                    if href and '/listing/' in href.lower() and 'porsche' in href.lower():
                        full_url = urljoin(self.base_url, href)
                        if full_url not in listing_urls:
                            listing_urls.append(full_url)
                
                logger.info(f"Found {len(listing_links)} listings on page {page_num}")
                
                # Find next page link
                next_link = soup.find('a', class_=re.compile(r'next|pagination.*next', re.I))
                if not next_link:
                    # Try alternative patterns
                    next_link = soup.find('a', string=re.compile(r'next|>', re.I))
                
                if next_link and next_link.get('href'):
                    current_url = urljoin(self.base_url, next_link.get('href'))
                    page_num += 1
                    time.sleep(config.REQUEST_DELAY)
                else:
                    # Try to find next page using Selenium XPath
                    try:
                        next_button = self.driver.find_element(By.XPATH, '//a[contains(@class, "next") or contains(text(), "Next")]')
                        if next_button:
                            href = next_button.get_attribute('href')
                            if href:
                                current_url = href
                                page_num += 1
                                time.sleep(config.REQUEST_DELAY)
                            else:
                                logger.info("No more pages found")
                                break
                        else:
                            logger.info("No more pages found")
                            break
                    except:
                        logger.info("No more pages found")
                        break
                    
            except requests.RequestException as e:
                logger.error(f"Error fetching page {page_num}: {e}")
                break
            except Exception as e:
                logger.error(f"Error parsing page {page_num}: {e}")
                break
        
        logger.info(f"Total listing URLs found: {len(listing_urls)}")
        return listing_urls
    
    def get_all_listing_urls_from_auction_results(self, search_url):
        """
        Extract all listing URLs from paginated search results, scoped to listings 
        under "Porsche Auction Results" heading. Used for historical price matching.
        
        Args:
            search_url: URL of the search results page with "Porsche Auction Results" heading
        
        Returns:
            list: List of listing URLs from the auction results section
        """
        listing_urls = []
        current_url = search_url
        page_num = 1
        reload_page = True  # Track if we need to reload the page
        
        while current_url:
            # Only reload page if needed (not after clicking "Show More")
            if reload_page:
                logger.info(f"Scraping page {page_num}: {current_url}")
                try:
                    # Ensure driver is alive
                    if not self._ensure_driver_alive():
                        logger.error(f"Cannot load page {current_url}: driver initialization failed")
                        break
                    
                    # Use Selenium to get JavaScript-rendered content
                    self.driver.get(current_url)
                    
                    # Wait for listings to load (wait for listing-card elements)
                    try:
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'a.listing-card'))
                        )
                    except:
                        # If specific elements don't appear, wait a bit anyway
                        time.sleep(3)
                except Exception as e:
                    logger.error(f"Error loading page {current_url}: {e}")
                    break
            else:
                logger.info(f"Re-parsing page {page_num} after 'Show More' click (total so far: {len(listing_urls)})")
            
            try:
                # Get the fully rendered HTML (from current page state)
                html = self.driver.page_source
                soup = BeautifulSoup(html, 'lxml')
                
                # Try to find "Porsche Auction Results" heading and scope to that section
                search_section = None
                auction_results_header = soup.find(string=re.compile(r'Porsche.*Auction.*Results?', re.I))
                if not auction_results_header:
                    # Try alternative: look for header element containing the text
                    auction_results_header = soup.find(['h1', 'h2', 'h3', 'h4'], string=re.compile(r'Porsche.*Auction.*Results?', re.I))
                
                if auction_results_header:
                    # Find parent section (try multiple parent types)
                    search_section = auction_results_header.find_parent(['section', 'div', 'article', 'main'])
                    if not search_section:
                        # If no direct parent, try finding next sibling or parent's parent
                        parent = auction_results_header.find_parent()
                        if parent:
                            search_section = parent.find_next_sibling(['section', 'div', 'article'])
                    if search_section:
                        logger.info("Found 'Porsche Auction Results' section, scoping search to that area")
                
                # Search within the section if found, otherwise search entire page
                search_area = search_section if search_section else soup
                
                # Find all listing links using CSS selector within the search area
                listing_links = search_area.select('a.listing-card[href*="/listing/"][href*="porsche"]')
                
                # Fallback: if CSS selector doesn't work, try the old method
                if not listing_links:
                    listing_links = search_area.find_all('a', class_=re.compile('listing-card'))
                    listing_links = [link for link in listing_links
                                     if link.get('href')
                                     and '/listing/' in link.get('href')
                                     and 'porsche' in link.get('href').lower()]
                
                logger.debug(f"Found {len(listing_links)} listing links on page {page_num}")
                
                for link in listing_links:
                    href = link.get('href')
                    if href and '/listing/' in href.lower() and 'porsche' in href.lower():
                        full_url = urljoin(self.base_url, href)
                        if full_url not in listing_urls:
                            listing_urls.append(full_url)
                
                logger.info(f"Found {len(listing_links)} listings on page {page_num} (total so far: {len(listing_urls)})")
                
                # Try to find and click "Show More" button inside div.auctions-completed
                # This button loads more listings via AJAX without changing the URL
                show_more_clicked = False
                try:
                    show_more_button = self.driver.find_element(By.CSS_SELECTOR, 'div.auctions-completed button.button-show-more')
                    if show_more_button:
                        # Check if button is visible and enabled
                        is_visible = show_more_button.is_displayed()
                        button_text = show_more_button.text.strip().lower()
                        
                        if is_visible and ('show more' in button_text or 'load' in button_text):
                            logger.info(f"Clicking 'Show More' button to load additional listings...")
                            # Get current count of listings before clicking
                            initial_count = len(self.driver.find_elements(By.CSS_SELECTOR, 'a.listing-card'))
                            logger.debug(f"Current listing count before 'Show More': {initial_count}")
                            
                            # Scroll to button to ensure it's in view
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", show_more_button)
                            time.sleep(0.5)
                            # Click the button
                            show_more_button.click()
                            
                            # Wait for new listings to actually appear (not just a fixed time)
                            try:
                                WebDriverWait(self.driver, 10).until(
                                    lambda driver: len(driver.find_elements(By.CSS_SELECTOR, 'a.listing-card')) > initial_count
                                )
                                new_count = len(self.driver.find_elements(By.CSS_SELECTOR, 'a.listing-card'))
                                logger.info(f"New listings loaded! Count increased from {initial_count} to {new_count}")
                            except:
                                # If count doesn't increase, wait a bit anyway
                                logger.warning("New listings may not have loaded, waiting anyway...")
                                time.sleep(3)
                            
                            show_more_clicked = True
                            page_num += 1
                            reload_page = False  # Don't reload - re-parse current page with new listings
                            # Continue loop to re-scrape the page with new listings
                            continue
                        else:
                            logger.info("'Show More' button found but not clickable or indicates no more content")
                except Exception as e:
                    logger.debug(f"Could not find 'Show More' button: {e}")
                
                # If "Show More" button wasn't found or clicked, try traditional pagination
                if not show_more_clicked:
                    next_link = soup.find('a', class_=re.compile(r'next|pagination.*next', re.I))
                    if not next_link:
                        # Try alternative patterns
                        next_link = soup.find('a', string=re.compile(r'next|>', re.I))
                    
                    if next_link and next_link.get('href'):
                        current_url = urljoin(self.base_url, next_link.get('href'))
                        page_num += 1
                        reload_page = True  # Need to reload for new URL
                        time.sleep(config.REQUEST_DELAY)
                    else:
                        # Try to find next page using Selenium XPath
                        try:
                            next_button = self.driver.find_element(By.XPATH, '//a[contains(@class, "next") or contains(text(), "Next")]')
                            if next_button:
                                href = next_button.get_attribute('href')
                                if href:
                                    current_url = href
                                    page_num += 1
                                    reload_page = True  # Need to reload for new URL
                                    time.sleep(config.REQUEST_DELAY)
                                else:
                                    logger.info("No more pages found")
                                    break
                            else:
                                logger.info("No more pages found (no 'Show More' button and no next link)")
                                break
                        except:
                            logger.info("No more pages found (no 'Show More' button and no next link)")
                            break
                    
            except requests.RequestException as e:
                logger.error(f"Error fetching page {page_num}: {e}")
                break
            except Exception as e:
                logger.error(f"Error parsing page {page_num}: {e}")
                break
        
        logger.info(f"Total listing URLs found: {len(listing_urls)}")
        return listing_urls
    
    def _should_exclude_listing(self, title, description):
        """
        Check if a listing should be excluded based on keywords.
        
        Args:
            title: Listing title text
            description: Listing description text
            
        Returns:
            bool: True if listing should be excluded, False otherwise
        """
        exclude_keywords = ['wheel', 'wheels', 'tool', 'seat', 'engine', 'gearbox', 'seats']
        
        # Combine title and description for checking
        combined_text = f"{title} {description}".lower()
        
        # Check if any exclude keyword is present
        for keyword in exclude_keywords:
            if keyword in combined_text:
                logger.debug(f"Excluding listing due to keyword: {keyword}")
                return True
        
        return False
    
    def scrape_listing(self, listing_url):
        """
        Scrape data from a single listing page.
        
        Args:
            listing_url: URL of the listing page
        
        Returns:
            dict: Dictionary with keys: model_year, model_type, mileage, price_now, description, source
                  (is_premium is included internally but not used in sheet)
                  Returns None if scraping fails
        """
        try:
            # Use Selenium to get JavaScript-rendered content
            self.driver.get(listing_url)
            
            # Wait for page to load
            time.sleep(2)
            
            # Get the fully rendered HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'lxml')
            
            # Extract title (usually contains year and model)
            title_elem = soup.find('h1') or soup.find('title')
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # Extract model year from title
            model_year = self._extract_year(title)
            
            # Extract model type (911, Cayman, Boxster)
            model_type = self._extract_model_type(title, soup)
            
            # Extract mileage
            mileage = self._extract_mileage(soup)
            logger.debug(f"Extracted mileage: {mileage} for {listing_url}")
            
            # Extract final price
            price_now = self._extract_price(soup)
            
            # Extract full description for sentiment analysis
            description = self._extract_description(soup)
            
            # Check if listing has Premium tag (used internally for condition determination)
            is_premium = self._is_premium_listing(soup)
            
            # Check if listing is a Non-Running Project (should be excluded)
            is_non_running_project = self._is_non_running_project(soup)
            
            # Check if listing should be excluded based on keywords
            should_exclude = self._should_exclude_listing(title, description)
            
            return {
                'model_year': model_year,
                'model_type': model_type,
                'mileage': mileage,
                'price_now': price_now,
                'description': description,
                'is_premium': is_premium,  # Internal use only - not written to sheet
                'is_non_running_project': is_non_running_project,  # Internal use only - exclude from sheet
                'should_exclude': should_exclude,  # Internal use only - exclude from sheet
                'source': listing_url
            }
            
        except requests.RequestException as e:
            logger.error(f"Error fetching listing {listing_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing listing {listing_url}: {e}")
            return None
    
    def _extract_year(self, text):
        """Extract 4-digit year from text."""
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            return year_match.group()
        return ""
    
    def _extract_model_type(self, title, soup):
        """Extract model type: 911, Cayman, or Boxster."""
        text = title.lower()
        
        # Check for specific model types
        if 'cayman' in text:
            return 'Cayman'
        elif 'boxster' in text:
            return 'Boxster'
        elif '911' in text or 'nine-eleven' in text or '911SC' in text:
            return '911'
        elif '356' in text:
            return '356'
        elif '356-pre-a' in text:
            return '356 Pre-A'
        elif '356A' in text:
            return '356A'
        elif '356B' in text:
            return '356B'
        elif '356C' in text:
            return '356C'
        elif '550' in text:
            return '550'
        elif '914' in text:
            return '914'
        elif '918' in text:
            return '918'
        elif '912' in text or '912E' in text:
            return '912'
        elif '924' in text:
            return '924'
        elif '928' in text:
            return '928'
        elif '930' in text:
            return '930'
        elif '934' in text:
            return '934'
        elif '935' in text:
            return '935'
        elif '944' in text:
            return '944'
        elif '955' in text:
            return '955'
        elif '957' in text:
            return '957'
        elif '962' in text:
            return '962'
        elif '956' in text:
            return '956'
        elif '958' in text:
            return '958'
        elif '959' in text:
            return '959'
        elif '964' in text:
            return '964'
        elif '968' in text:
            return '968'
        elif '981' in text:
            return '981'
        elif '982' in text:
            return '982'
        elif '986' in text:
            return '986'
        elif '987' in text:
            return '987'
        elif '991' in text:
            return '991'
        elif '992' in text:
            return '992'
        elif '993' in text:
            return '993'
        elif '996' in text:
            return '996'
        elif '997' in text:
            return '997'
        elif '9Y0' in text:
            return '9Y0'
        elif '9Y3' in text:
            return '9Y3'
        
        # Try to find in listing details
        details_text = soup.get_text().lower()
        if 'cayman' in details_text:
            return 'Cayman'
        elif 'boxster' in details_text:
            return 'Boxster'
        elif '911' in details_text:
            return '911'
        
        return ""
    
    def _extract_mileage(self, soup):
        """Extract mileage from the Listing Details section."""
        # Try multiple approaches to find mileage
        
        # Approach 1: Find "Listing Details" section
        details_heading = soup.find('strong', string=re.compile(r'Listing Details', re.I))
        if not details_heading:
            # Try alternative: look for any strong tag with "Details"
            details_heading = soup.find('strong', string=re.compile(r'Details', re.I))
        
        if details_heading:
            # Find the parent div with class "item" or the ul that follows
            parent = details_heading.find_parent('div', class_='item')
            if not parent:
                parent = details_heading.find_parent('div')
            if not parent:
                parent = details_heading.find_parent()
            
            # Find the ul within this section
            ul = parent.find('ul') if parent else None
            if ul:
                # Look for li containing "Miles" or "Mileage"
                for li in ul.find_all('li'):
                    li_text = li.get_text()
                    if 'mile' in li_text.lower():
                        logger.debug(f"Found mileage-related li: {li_text}")
                        # Extract number closest to "mile" word
                        result = self._extract_number_near_word(li_text, ['mile', 'miles', 'mileage'])
                        if result:
                            return result
        
        # Approach 2: Search all ul/li elements for mileage
        all_uls = soup.find_all('ul')
        for ul in all_uls:
            for li in ul.find_all('li'):
                li_text = li.get_text()
                if 'mile' in li_text.lower():
                    logger.debug(f"Found mileage-related li (fallback): {li_text}")
                    result = self._extract_number_near_word(li_text, ['mile', 'miles', 'mileage'])
                    if result:
                        return result
        
        # Approach 3: Search in div elements with class containing "detail" or "info"
        detail_divs = soup.find_all('div', class_=re.compile(r'detail|info', re.I))
        for div in detail_divs:
            div_text = div.get_text()
            if 'mile' in div_text.lower():
                logger.debug(f"Found mileage in div: {div_text[:200]}")
                result = self._extract_number_near_word(div_text, ['mile', 'miles', 'mileage'])
                if result:
                    return result
        
        # Approach 4: Last resort - search entire page text
        page_text = soup.get_text()
        if 'mile' in page_text.lower():
            logger.debug("Searching entire page for mileage")
            result = self._extract_number_near_word(page_text, ['mile', 'miles', 'mileage'])
            if result:
                return result
        
        logger.debug("No mileage found")
        return ""
    
    def _extract_number_near_word(self, text, keywords):
        """
        Extract number closest to any of the given keywords.
        
        Args:
            text: Text to search in
            keywords: List of keywords to search for (e.g., ['mile', 'miles'])
        
        Returns:
            int: Mileage value, or empty string if not found
        """
        # Find all numbers (including with "k" notation)
        all_numbers = list(re.finditer(r'(\d{1,3}(?:,\d{3})*)\s*(k)?\b', text, re.IGNORECASE))
        
        if not all_numbers:
            return ""
        
        numbers_list = []
        for match in all_numbers:
            has_k = match.group(2) and match.group(2).lower() == 'k'
            numbers_list.append({
                'value': match.group(1),
                'has_k': has_k,
                'start': match.start(),
                'end': match.end()
            })
        
        # Find the closest keyword
        closest_keyword_pos = None
        for keyword in keywords:
            keyword_match = re.search(r'\b' + re.escape(keyword) + r'\b', text, re.IGNORECASE)
            if keyword_match:
                keyword_pos = keyword_match.start()
                if closest_keyword_pos is None or keyword_pos < closest_keyword_pos:
                    closest_keyword_pos = keyword_pos
        
        if closest_keyword_pos is not None:
            # Find number closest to keyword
            closest_number = min(numbers_list, 
                                key=lambda x: abs(x['start'] - closest_keyword_pos))
        else:
            # If no keyword found, take first number
            closest_number = numbers_list[0]
        
        # Extract and process the number
        mileage_str = closest_number['value'].replace(',', '')
        try:
            mileage = int(mileage_str)
            # If number has "k", multiply by 1000
            if closest_number['has_k']:
                mileage *= 1000
            logger.debug(f"Extracted mileage: {mileage}")
            return mileage
        except ValueError:
            return ""
    
    def _extract_price(self, soup):
        """Extract final price from listing page."""
        # Look for price in listing-available-info div
        # Structure: div.listing-available-info > span.info-value > strong (contains price)
        price_info = soup.find('div', class_='listing-available-info')
        if price_info:
            # Look for strong tag with price
            strong_tag = price_info.find('strong')
            if strong_tag:
                price_text = strong_tag.get_text(strip=True)
                # Extract numeric value from price text (e.g., "USD $100,000" -> "100000")
                price_match = re.search(r'[\$]?\s*(\d{1,3}(?:,\d{3})*)', price_text)
                if price_match:
                    price_str = price_match.group(1).replace(',', '')
                    try:
                        return int(price_str)
                    except ValueError:
                        pass
        
        # Alternative: Look for "Sold for" or "Bid to" text patterns
        text = soup.get_text()
        # Pattern: "Sold for USD $100,000" or "Bid to USD $100,000"
        price_patterns = [
            r'(?:Sold for|Bid to)\s+(?:USD\s*)?[\$]?\s*(\d{1,3}(?:,\d{3})*)',
            r'[\$](\d{1,3}(?:,\d{3})*)\s*(?:on|$)',  # Price at end of line
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(',', '')
                try:
                    return int(price_str)
                except ValueError:
                    continue
        
        # Look for any strong tag with price-like content
        all_strong = soup.find_all('strong')
        for strong in all_strong:
            strong_text = strong.get_text(strip=True)
            if '$' in strong_text or 'USD' in strong_text.upper():
                price_match = re.search(r'[\$]?\s*(\d{1,3}(?:,\d{3})*)', strong_text)
                if price_match:
                    price_str = price_match.group(1).replace(',', '')
                    try:
                        return int(price_str)
                    except ValueError:
                        continue
        
        return ""
    
    def _is_premium_listing(self, soup):
        """
        Check if listing has Premium tag.
        
        Args:
            soup: BeautifulSoup object of the listing page
        
        Returns:
            bool: True if listing has Premium tag, False otherwise
        """
        # Look for div with class "item-tag-premium"
        premium_tag = soup.find('div', class_=re.compile(r'item-tag-premium', re.I))
        if premium_tag:
            # Check if it contains "Premium" text
            tag_text = premium_tag.get_text()
            if 'premium' in tag_text.lower():
                return True
        
        # Alternative: search for "Premium" text in item-tags div
        item_tags = soup.find('div', class_=re.compile(r'item-tags', re.I))
        if item_tags:
            tags_text = item_tags.get_text()
            if 'premium' in tags_text.lower():
                return True
        
        return False
    
    def _is_non_running_project(self, soup):
        """
        Check if listing contains "Non-Running Project" in listing details.
        
        Args:
            soup: BeautifulSoup object of the listing page
        
        Returns:
            bool: True if listing is a Non-Running Project, False otherwise
        """
        # Look for "Non-Running Project" in Listing Details section
        details_heading = soup.find('strong', string=re.compile(r'Listing Details', re.I))
        if details_heading:
            parent = details_heading.find_parent('div', class_='item')
            if not parent:
                parent = details_heading.find_parent('div')
            if not parent:
                parent = details_heading.find_parent()
            
            if parent:
                # Check all text in the listing details section
                details_text = parent.get_text()
                if 'non-running project' in details_text.lower():
                    return True
        
        # Fallback: search all ul/li elements
        all_uls = soup.find_all('ul')
        for ul in all_uls:
            for li in ul.find_all('li'):
                li_text = li.get_text()
                if 'non-running project' in li_text.lower():
                    return True
        
        # Last resort: search entire page
        page_text = soup.get_text()
        if 'non-running project' in page_text.lower():
            return True
        
        return False
    
    def _extract_description(self, soup):
        """Extract full description text from listing."""
        # Try to find main description/content area
        description_selectors = [
            'div.lot-description',
            'div.description',
            'div.content',
            'article',
            'div[class*="description"]',
            'div[class*="content"]',
        ]
        
        for selector in description_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                return desc_elem.get_text(separator=' ', strip=True)
        
        # Fallback: get all paragraph text
        paragraphs = soup.find_all('p')
        if paragraphs:
            return ' '.join([p.get_text(strip=True) for p in paragraphs])
        
        # Last resort: get body text
        body = soup.find('body')
        if body:
            return body.get_text(separator=' ', strip=True)
        
        return ""
    
    def _extract_sale_date(self, soup):
        """
        Extract sale date from a sold listing page.
        Looks specifically in the sale info element: <span class="info-value noborder-tiny">
        which contains "Sold for ... <span class="date">on MM/DD/YY</span>"
        
        Args:
            soup: BeautifulSoup object of the listing page
            
        Returns:
            str: Sale date in YYYY-MM-DD format, or empty string if not found
        """
        # Look for the sale info element (same structure as price extraction)
        # Structure: <span class="info-value noborder-tiny">Sold for <strong>USD $68,000</strong> <span class="date">on 11/23/25</span></span>
        sale_info = soup.find('span', class_='info-value')
        if not sale_info:
            return ""
        
        sale_info_text = sale_info.get_text()

        print(f"\nCONTENT SCANNING: {sale_info_text}")
        
        # Check if listing is sold/bid by looking for "Sold for" or "Bid to" text in this element
        if 'sold for' not in sale_info_text.lower() and 'bid to' not in sale_info_text.lower():
            return ""  # Not a sold/bid listing
        
        # Look for the date inside <span class="date"> within the sale info element
        date_span = sale_info.find('span', class_='date')
        if date_span:
            date_text = date_span.get_text(strip=True)
            # Pattern: "on 11/23/25" or "on 1/4/22"
            date_match = re.search(r'on\s+(\d{1,2})/(\d{1,2})/(\d{2})', date_text, re.IGNORECASE)
            if date_match:
                month = date_match.group(1).zfill(2)
                day = date_match.group(2).zfill(2)
                year_2digit = date_match.group(3)
                
                # Handle 2-digit year (always assume 20xx)
                year = f"20{year_2digit}"
                print(f"SALE_DATE IDENTIFIED: {year}\n")
                
                return f"{year}-{month}-{day}"
        
        # Fallback: Look for date pattern in the sale_info_text itself
        # Pattern: "Sold for ... on 11/23/25" or "Bid to ... on 11/23/25"
        date_pattern = r'(?:Sold\s+for|Bid\s+to)\s+.*?on\s+(\d{1,2})/(\d{1,2})/(\d{2})'
        match = re.search(date_pattern, sale_info_text, re.IGNORECASE)
        
        if match:
            month = match.group(1).zfill(2)
            day = match.group(2).zfill(2)
            year_2digit = match.group(3)
            
            # Handle 2-digit year (always assume 20xx)
            year = f"20{year_2digit}"
            
            return f"{year}-{month}-{day}"
        
        return ""
    
    def scrape_sold_listing(self, listing_url):
        """
        Scrape data from a sold listing page, including sale date and price.
        
        Args:
            listing_url: URL of the sold listing page
            
        Returns:
            dict: Dictionary with keys: model_year, model_type, mileage, condition, sale_price, sale_date
                  Returns None if scraping fails
        """
        try:
            # Ensure driver is alive before attempting to scrape
            if not self._ensure_driver_alive():
                logger.error(f"Cannot scrape {listing_url}: driver initialization failed")
                return None
            
            # Use Selenium to get JavaScript-rendered content
            self.driver.get(listing_url)
            
            # Wait for page to load
            time.sleep(2)
            
            # Get the fully rendered HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'lxml')
            
            # Extract title (usually contains year and model)
            title_elem = soup.find('h1') or soup.find('title')
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # Extract model year from title
            model_year = self._extract_year(title)
            
            # Extract model type
            model_type = self._extract_model_type(title, soup)
            
            # Extract mileage
            mileage = self._extract_mileage(soup)
            
            # Extract sale price
            sale_price = self._extract_price(soup)
            
            # Extract sale date
            sale_date = self._extract_sale_date(soup)
            
            # Extract description for condition analysis
            description = self._extract_description(soup)
            
            # Check if listing has Premium tag
            is_premium = self._is_premium_listing(soup)
            
            # Check if listing should be excluded based on keywords
            should_exclude = self._should_exclude_listing(title, description)
            
            return {
                'model_year': model_year,
                'model_type': model_type,
                'mileage': mileage,
                'sale_price': sale_price,
                'sale_date': sale_date,
                'description': description,
                'is_premium': is_premium,
                'should_exclude': should_exclude,  # Internal use only - exclude from sheet
                'source': listing_url
            }
            
        except Exception as e:
            logger.error(f"Error scraping sold listing {listing_url}: {e}")
            return None

