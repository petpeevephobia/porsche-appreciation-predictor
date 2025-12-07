"""GUI application for Porsche scraper tools."""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import sys
import os
import logging
from pathlib import Path

# Add parent directory to path to import scraper modules
sys.path.insert(0, str(Path(__file__).parent))

from scraper import PorscheScraper
from condition_analyzer import ConditionAnalyzer
from sheets_writer import SheetsWriter
from image_scraper import ImageScraper
from description_scraper import DescriptionScraper
from historical_matcher import HistoricalMatcher
from match_historical_prices import main as match_historical_main
import config

# Configure logging to output to GUI
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScraperGUI:
    """Main GUI application for Porsche scraper tools."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Porsche Scraper Tools")
        self.root.geometry("1000x700")
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_settings_tab()
        self.create_main_scraper_tab()
        self.create_image_scraper_tab()
        self.create_description_scraper_tab()
        self.create_historical_matcher_tab()
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def create_main_scraper_tab(self):
        """Create the main scraper tab."""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Main Scraper")
        
        # Description
        desc_text = (
            "OBJECTIVE: Scrape Porsche listings from Bring a Trailer and add them to your Google Sheet.\n\n"
            "WHAT IT DOES: This tool extracts listing data (model year, type, mileage, price) from BaT search pages, "
            "analyzes vehicle condition using AI, and writes the data to your Google Sheet. It handles pagination "
            "automatically and skips duplicate listings.\n\n"
            "HOW IT HELPS: This is the primary data collection tool. It populates your sheet with current Porsche "
            "listings, including their condition analysis, which is essential for calculating appreciation values."
        )
        desc_label = ttk.Label(frame, text=desc_text, wraplength=700, justify=tk.LEFT)
        desc_label.grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=10, pady=10)
        
        # Separator
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=3, sticky=tk.EW, padx=5, pady=5)
        
        # URL input
        ttk.Label(frame, text="BaT Search URL:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.url_entry = ttk.Entry(frame, width=60)
        self.url_entry.grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        self.url_entry.insert(0, "https://bringatrailer.com/search/?q=porsche")
        
        # Batch size
        ttk.Label(frame, text="Batch Size:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.batch_size_entry = ttk.Entry(frame, width=10)
        self.batch_size_entry.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        self.batch_size_entry.insert(0, "10")
        
        # Run button
        self.run_scraper_btn = ttk.Button(frame, text="Run Scraper", command=self.run_main_scraper)
        self.run_scraper_btn.grid(row=4, column=0, columnspan=3, pady=10)
        
        # Log output
        ttk.Label(frame, text="Output:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.main_log = scrolledtext.ScrolledText(frame, height=20, width=80)
        self.main_log.grid(row=6, column=0, columnspan=3, sticky=tk.NSEW, padx=5, pady=5)
        
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)
    
    def create_image_scraper_tab(self):
        """Create the image scraper tab."""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Image Scraper")
        
        # Description
        desc_text = (
            "OBJECTIVE: Download images from Porsche listings that are already in your Google Sheet.\n\n"
            "WHAT IT DOES: This tool reads listings from your sheet, visits each listing URL, extracts up to 12 images "
            "per listing, saves them locally, and updates the sheet with image file paths.\n\n"
            "HOW IT HELPS: Images are essential for visual analysis and model training. This tool ensures you have "
            "visual data for each listing, which can be used for image-based condition assessment or feature extraction."
        )
        desc_label = ttk.Label(frame, text=desc_text, wraplength=700, justify=tk.LEFT)
        desc_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=10, pady=10)
        
        # Separator
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        
        # Options
        self.skip_existing_images = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Skip existing images", variable=self.skip_existing_images).grid(
            row=2, column=0, sticky=tk.W, padx=5, pady=5
        )
        
        ttk.Label(frame, text="Limit (optional):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.image_limit_entry = ttk.Entry(frame, width=10)
        self.image_limit_entry.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(frame, text="Batch Size:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.image_batch_entry = ttk.Entry(frame, width=10)
        self.image_batch_entry.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        self.image_batch_entry.insert(0, "10")
        
        # Run button
        self.run_image_btn = ttk.Button(frame, text="Scrape Images", command=self.run_image_scraper)
        self.run_image_btn.grid(row=5, column=0, columnspan=2, pady=10)
        
        # Log output
        ttk.Label(frame, text="Output:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=5)
        self.image_log = scrolledtext.ScrolledText(frame, height=20, width=80)
        self.image_log.grid(row=7, column=0, columnspan=2, sticky=tk.NSEW, padx=5, pady=5)
        
        frame.rowconfigure(7, weight=1)
    
    def create_description_scraper_tab(self):
        """Create the description scraper tab."""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Description Scraper")
        
        # Description
        desc_text = (
            "OBJECTIVE: Extract detailed seller descriptions and listing specifications from Porsche listings.\n\n"
            "WHAT IT DOES: This tool reads listings from your sheet, visits each listing URL, extracts the full seller "
            "description and listing details (specs, features, history), saves them as text files, and updates the "
            "sheet with file paths.\n\n"
            "HOW IT HELPS: Detailed descriptions provide rich textual data for analysis. These descriptions can be "
            "used for natural language processing, sentiment analysis, or as additional context for condition assessment "
            "and price prediction models."
        )
        desc_label = ttk.Label(frame, text=desc_text, wraplength=700, justify=tk.LEFT)
        desc_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=10, pady=10)
        
        # Separator
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        
        # Options
        self.skip_existing_descriptions = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Skip existing descriptions", variable=self.skip_existing_descriptions).grid(
            row=2, column=0, sticky=tk.W, padx=5, pady=5
        )
        
        ttk.Label(frame, text="Limit (optional):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.desc_limit_entry = ttk.Entry(frame, width=10)
        self.desc_limit_entry.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(frame, text="Batch Size:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.desc_batch_entry = ttk.Entry(frame, width=10)
        self.desc_batch_entry.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        self.desc_batch_entry.insert(0, "10")
        
        # Run button
        self.run_desc_btn = ttk.Button(frame, text="Scrape Descriptions", command=self.run_description_scraper)
        self.run_desc_btn.grid(row=5, column=0, columnspan=2, pady=10)
        
        # Log output
        ttk.Label(frame, text="Output:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=5)
        self.desc_log = scrolledtext.ScrolledText(frame, height=20, width=80)
        self.desc_log.grid(row=7, column=0, columnspan=2, sticky=tk.NSEW, padx=5, pady=5)
        
        frame.rowconfigure(7, weight=1)
    
    def create_historical_matcher_tab(self):
        """Create the historical price matcher tab."""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Historical Price Matcher")
        
        # Description
        desc_text = (
            "OBJECTIVE: Match current listings with historical 2020-2022 sold listings to calculate price appreciation.\n\n"
            "WHAT IT DOES: This tool scrapes or loads historical BaT sold listings from 2020-2022, then matches each "
            "current listing with similar historical listings based on model type, year (±1), mileage (±15%), and "
            "condition. It calculates the 'price_3_years_ago' value using the median of the best matches.\n\n"
            "HOW IT HELPS: This is critical for calculating appreciation. By comparing current prices to historical "
            "prices of similar vehicles, you can determine how much each Porsche has appreciated over time, which is "
            "the core metric for your prediction model."
        )
        desc_label = ttk.Label(frame, text=desc_text, wraplength=700, justify=tk.LEFT)
        desc_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=10, pady=10)
        
        # Separator
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        
        # BaT search URL
        ttk.Label(frame, text="BaT Search URL (sold listings):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.hist_url_entry = ttk.Entry(frame, width=60)
        self.hist_url_entry.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        self.hist_url_entry.insert(0, "https://bringatrailer.com/search/?q=porsche&sold=1")
        
        # Options
        self.skip_scraping = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Skip scraping (use existing data)", variable=self.skip_scraping).grid(
            row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5
        )
        
        self.force_scrape = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Force scrape (ignore existing data)", variable=self.force_scrape).grid(
            row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5
        )
        
        self.only_insufficient = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Only process 'insufficient_data' rows", variable=self.only_insufficient).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5
        )
        
        ttk.Label(frame, text="Batch Size:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=5)
        self.hist_batch_entry = ttk.Entry(frame, width=10)
        self.hist_batch_entry.grid(row=6, column=1, sticky=tk.W, padx=5, pady=5)
        self.hist_batch_entry.insert(0, "10")
        
        ttk.Label(frame, text="Limit (optional):").grid(row=7, column=0, sticky=tk.W, padx=5, pady=5)
        self.hist_limit_entry = ttk.Entry(frame, width=10)
        self.hist_limit_entry.grid(row=7, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Run button
        self.run_hist_btn = ttk.Button(frame, text="Match Historical Prices", command=self.run_historical_matcher)
        self.run_hist_btn.grid(row=8, column=0, columnspan=2, pady=10)
        
        # Log output
        ttk.Label(frame, text="Output:").grid(row=9, column=0, sticky=tk.W, padx=5, pady=5)
        self.hist_log = scrolledtext.ScrolledText(frame, height=15, width=80)
        self.hist_log.grid(row=10, column=0, columnspan=2, sticky=tk.NSEW, padx=5, pady=5)
        
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(10, weight=1)
    
    def create_settings_tab(self):
        """Create the settings tab for environment variables."""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Settings")
        
        # Description
        desc_text = (
            "Configure the required environment variables for the scraper to work.\n"
            "These settings will be saved to a .env file in the project root directory."
        )
        desc_label = ttk.Label(frame, text=desc_text, wraplength=700, justify=tk.LEFT)
        desc_label.grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=10, pady=10)
        
        # Separator
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=3, sticky=tk.EW, padx=5, pady=5)
        
        # Google Sheets Credentials Path
        ttk.Label(frame, text="Google Sheets Credentials Path:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.credentials_path_entry = ttk.Entry(frame, width=60)
        self.credentials_path_entry.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        if config.GOOGLE_SHEETS_CREDENTIALS_PATH:
            self.credentials_path_entry.insert(0, config.GOOGLE_SHEETS_CREDENTIALS_PATH)
        browse_creds_btn = ttk.Button(frame, text="Browse...", command=self.browse_credentials_file)
        browse_creds_btn.grid(row=2, column=2, padx=5, pady=5)
        
        # Google Sheet ID
        ttk.Label(frame, text="Google Sheet ID:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.sheet_id_entry = ttk.Entry(frame, width=60)
        self.sheet_id_entry.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=5)
        if config.GOOGLE_SHEET_ID:
            self.sheet_id_entry.insert(0, config.GOOGLE_SHEET_ID)
        
        # OpenAI API Key
        ttk.Label(frame, text="OpenAI API Key:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.openai_key_entry = ttk.Entry(frame, width=60, show="*")
        self.openai_key_entry.grid(row=4, column=1, sticky=tk.EW, padx=5, pady=5)
        if config.OPENAI_API_KEY:
            self.openai_key_entry.insert(0, config.OPENAI_API_KEY)
        show_key_var = tk.BooleanVar()
        show_key_check = ttk.Checkbutton(frame, text="Show", variable=show_key_var, 
                                         command=lambda: self.toggle_password_visibility(self.openai_key_entry, show_key_var))
        show_key_check.grid(row=4, column=2, padx=5, pady=5)
        
        # Save button
        save_btn = ttk.Button(frame, text="Save Settings", command=self.save_settings)
        save_btn.grid(row=5, column=0, columnspan=3, pady=20)
        
        # Status label
        self.settings_status_var = tk.StringVar(value="")
        status_label = ttk.Label(frame, textvariable=self.settings_status_var, foreground="green")
        status_label.grid(row=6, column=0, columnspan=3, pady=5)
        
        # Info text
        info_text = (
            "Note: After saving, you may need to restart the application for changes to take effect.\n"
            "The .env file will be created in the project root directory."
        )
        info_label = ttk.Label(frame, text=info_text, wraplength=700, justify=tk.LEFT, foreground="gray")
        info_label.grid(row=7, column=0, columnspan=3, sticky=tk.W, padx=10, pady=10)
        
        frame.columnconfigure(1, weight=1)
    
    def browse_credentials_file(self):
        """Open file dialog to browse for credentials JSON file."""
        filename = filedialog.askopenfilename(
            title="Select Google Sheets Credentials JSON File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.credentials_path_entry.delete(0, tk.END)
            self.credentials_path_entry.insert(0, filename)
    
    def toggle_password_visibility(self, entry, var):
        """Toggle password visibility in entry field."""
        if var.get():
            entry.config(show="")
        else:
            entry.config(show="*")
    
    def save_settings(self):
        """Save settings to .env file."""
        try:
            # Get project root directory (parent of scraper directory)
            project_root = Path(__file__).parent.parent
            env_file = project_root / ".env"
            
            # Read existing .env file if it exists
            env_vars = {}
            if env_file.exists():
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key.strip()] = value.strip()
            
            # Update with new values
            credentials_path = self.credentials_path_entry.get().strip()
            sheet_id = self.sheet_id_entry.get().strip()
            openai_key = self.openai_key_entry.get().strip()
            
            if credentials_path:
                env_vars['GOOGLE_SHEETS_CREDENTIALS_PATH'] = credentials_path
            if sheet_id:
                env_vars['GOOGLE_SHEET_ID'] = sheet_id
            if openai_key:
                env_vars['OPENAI_API_KEY'] = openai_key
            
            # Write to .env file
            with open(env_file, 'w') as f:
                f.write("# Porsche Scraper Configuration\n")
                f.write("# Generated by GUI Settings\n\n")
                f.write(f"GOOGLE_SHEETS_CREDENTIALS_PATH={env_vars.get('GOOGLE_SHEETS_CREDENTIALS_PATH', '')}\n")
                f.write(f"GOOGLE_SHEET_ID={env_vars.get('GOOGLE_SHEET_ID', '')}\n")
                f.write(f"OPENAI_API_KEY={env_vars.get('OPENAI_API_KEY', '')}\n")
            
            self.settings_status_var.set("Settings saved successfully!")
            self.root.after(3000, lambda: self.settings_status_var.set(""))
            
            # Reload config to update current session
            import importlib
            importlib.reload(config)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}")
            self.settings_status_var.set("Error saving settings")
    
    def log_to_text(self, text_widget, message):
        """Append message to text widget."""
        text_widget.insert(tk.END, message + "\n")
        text_widget.see(tk.END)
        self.root.update_idletasks()
    
    def run_main_scraper(self):
        """Run the main scraper in a separate thread."""
        if not self.validate_config():
            return
        
        self.run_scraper_btn.config(state=tk.DISABLED)
        self.status_var.set("Running main scraper...")
        self.main_log.delete(1.0, tk.END)
        
        thread = threading.Thread(target=self._run_main_scraper_thread)
        thread.daemon = True
        thread.start()
    
    def _run_main_scraper_thread(self):
        """Main scraper thread function."""
        scraper = None
        analyzer = None
        writer = None
        try:
            url = self.url_entry.get().strip()
            batch_size = int(self.batch_size_entry.get() or "10")
            
            self.log_to_text(self.main_log, f"Starting scraper with URL: {url}")
            self.log_to_text(self.main_log, f"Batch size: {batch_size}")
            
            # Initialize components
            self.log_to_text(self.main_log, "Initializing components...")
            scraper = PorscheScraper()
            analyzer = ConditionAnalyzer()
            writer = SheetsWriter()
            
            # Step 1: Get all category URLs from the main page
            self.log_to_text(self.main_log, f"Fetching category pages from: {url}")
            category_urls = scraper.get_all_category_urls(url)
            
            if not category_urls:
                self.log_to_text(self.main_log, "No category pages found. Trying to scrape listings directly from URL...")
                listing_urls = scraper.get_all_listing_urls(url)
            else:
                # Step 2: Get all listing URLs from each category
                self.log_to_text(self.main_log, f"Found {len(category_urls)} category pages. Fetching listings from each...")
                listing_urls = []
                for i, category_url in enumerate(category_urls, 1):
                    self.log_to_text(self.main_log, f"Fetching listings from category {i}/{len(category_urls)}: {category_url}")
                    category_listings = scraper.get_all_listing_urls(category_url)
                    listing_urls.extend(category_listings)
                    self.log_to_text(self.main_log, f"Found {len(category_listings)} listings in this category. Total so far: {len(listing_urls)}")
                    import time
                    time.sleep(config.REQUEST_DELAY)
            
            if not listing_urls:
                self.log_to_text(self.main_log, "No listing URLs found. Exiting.")
                return
            
            # Remove duplicates
            listing_urls = list(set(listing_urls))
            self.log_to_text(self.main_log, f"Found {len(listing_urls)} unique listings to process")
            
            # Step 3: Scrape all listings first
            self.log_to_text(self.main_log, "Step 1: Scraping all listings...")
            all_listing_data = []
            failed = 0
            
            for i, listing_url in enumerate(listing_urls, 1):
                self.log_to_text(self.main_log, f"Scraping listing {i}/{len(listing_urls)}: {listing_url}")
                try:
                    listing_data = scraper.scrape_listing(listing_url)
                    if listing_data:
                        # Skip Non-Running Project listings
                        if listing_data.get('is_non_running_project', False):
                            self.log_to_text(self.main_log, f"Skipping Non-Running Project listing: {listing_url}")
                            failed += 1
                            continue
                        # Skip listings with excluded keywords
                        if listing_data.get('should_exclude', False):
                            self.log_to_text(self.main_log, f"Skipping listing with excluded keywords: {listing_url}")
                            failed += 1
                            continue
                        all_listing_data.append(listing_data)
                    else:
                        self.log_to_text(self.main_log, f"Failed to scrape listing: {listing_url}")
                        failed += 1
                    import time
                    time.sleep(config.REQUEST_DELAY)
                except Exception as e:
                    self.log_to_text(self.main_log, f"Error scraping listing {listing_url}: {e}")
                    failed += 1
                    continue
            
            self.log_to_text(self.main_log, f"Scraped {len(all_listing_data)} listings successfully")
            
            # Step 4: Analyze all conditions in batch
            self.log_to_text(self.main_log, "Step 2: Analyzing conditions in batch...")
            
            # Separate premium listings (automatically Excellent) from others
            premium_indices = []
            non_premium_data = []
            non_premium_indices = []
            
            for i, data in enumerate(all_listing_data):
                if data.get('is_premium', False):
                    premium_indices.append(i)
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
            self.log_to_text(self.main_log, "Step 3: Writing to Google Sheet...")
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
                    listing_data.get('price_now', ''),
                    "",
                    "",
                    listing_data['source']
                ]
                
                batch_data.append(row_data)
                
                # Write batch to sheet
                if len(batch_data) >= batch_size:
                    added = writer.batch_append(batch_data)
                    successful += added
                    batch_data = []
                    self.log_to_text(self.main_log, f"Batch written. Total successful: {successful}")
            
            # Write remaining batch
            if batch_data:
                added = writer.batch_append(batch_data)
                successful += added
            
            # Summary
            self.log_to_text(self.main_log, "=" * 50)
            self.log_to_text(self.main_log, "Scraping completed!")
            self.log_to_text(self.main_log, f"Total listings processed: {len(listing_urls)}")
            self.log_to_text(self.main_log, f"Successfully added: {successful}")
            self.log_to_text(self.main_log, f"Failed: {failed}")
            self.log_to_text(self.main_log, "=" * 50)
            
            self.status_var.set("Ready")
            
        except Exception as e:
            self.log_to_text(self.main_log, f"Error: {str(e)}")
            import traceback
            self.log_to_text(self.main_log, traceback.format_exc())
            self.status_var.set("Error occurred")
        finally:
            # Clean up
            if scraper and hasattr(scraper, 'driver'):
                try:
                    scraper.driver.quit()
                except:
                    pass
            self.run_scraper_btn.config(state=tk.NORMAL)
    
    def run_image_scraper(self):
        """Run image scraper in a separate thread."""
        if not self.validate_config():
            return
        
        self.run_image_btn.config(state=tk.DISABLED)
        self.status_var.set("Running image scraper...")
        self.image_log.delete(1.0, tk.END)
        
        thread = threading.Thread(target=self._run_image_scraper_thread)
        thread.daemon = True
        thread.start()
    
    def _run_image_scraper_thread(self):
        """Image scraper thread function."""
        try:
            skip_existing = self.skip_existing_images.get()
            limit_str = self.image_limit_entry.get().strip()
            limit = int(limit_str) if limit_str else None
            batch_size = int(self.image_batch_entry.get() or "10")
            
            self.log_to_text(self.image_log, "Initializing image scraper...")
            
            scraper = ImageScraper()
            listings = scraper.read_listings_from_sheet()
            
            if not listings:
                self.log_to_text(self.image_log, "No listings found in sheet")
                return
            
            self.log_to_text(self.image_log, f"Found {len(listings)} listings")
            
            summary = scraper.process_all_listings(
                listings,
                limit=limit,
                skip_existing=skip_existing,
                batch_size=batch_size
            )
            
            self.log_to_text(self.image_log, f"\nSummary:")
            self.log_to_text(self.image_log, f"Total: {summary['total']}")
            self.log_to_text(self.image_log, f"Successful: {summary['successful']}")
            self.log_to_text(self.image_log, f"Skipped: {summary['skipped']}")
            self.log_to_text(self.image_log, f"Failed: {summary['failed']}")
            self.log_to_text(self.image_log, f"Total images: {summary['total_images']}")
            
            self.status_var.set("Ready")
            
        except Exception as e:
            self.log_to_text(self.image_log, f"Error: {str(e)}")
            import traceback
            self.log_to_text(self.image_log, traceback.format_exc())
            self.status_var.set("Error occurred")
        finally:
            self.run_image_btn.config(state=tk.NORMAL)
    
    def run_description_scraper(self):
        """Run description scraper in a separate thread."""
        if not self.validate_config():
            return
        
        self.run_desc_btn.config(state=tk.DISABLED)
        self.status_var.set("Running description scraper...")
        self.desc_log.delete(1.0, tk.END)
        
        thread = threading.Thread(target=self._run_description_scraper_thread)
        thread.daemon = True
        thread.start()
    
    def _run_description_scraper_thread(self):
        """Description scraper thread function."""
        try:
            skip_existing = self.skip_existing_descriptions.get()
            limit_str = self.desc_limit_entry.get().strip()
            limit = int(limit_str) if limit_str else None
            batch_size = int(self.desc_batch_entry.get() or "10")
            
            self.log_to_text(self.desc_log, "Initializing description scraper...")
            
            scraper = DescriptionScraper()
            listings = scraper.read_listings_from_sheet()
            
            if not listings:
                self.log_to_text(self.desc_log, "No listings found in sheet")
                return
            
            self.log_to_text(self.desc_log, f"Found {len(listings)} listings")
            
            summary = scraper.process_all_listings(
                listings,
                limit=limit,
                skip_existing=skip_existing,
                batch_size=batch_size
            )
            
            self.log_to_text(self.desc_log, f"\nSummary:")
            self.log_to_text(self.desc_log, f"Total: {summary['total']}")
            self.log_to_text(self.desc_log, f"Successful: {summary['successful']}")
            self.log_to_text(self.desc_log, f"Skipped: {summary['skipped']}")
            self.log_to_text(self.desc_log, f"Failed: {summary['failed']}")
            
            self.status_var.set("Ready")
            
        except Exception as e:
            self.log_to_text(self.desc_log, f"Error: {str(e)}")
            import traceback
            self.log_to_text(self.desc_log, traceback.format_exc())
            self.status_var.set("Error occurred")
        finally:
            self.run_desc_btn.config(state=tk.NORMAL)
    
    def run_historical_matcher(self):
        """Run historical price matcher in a separate thread."""
        if not self.validate_config():
            return
        
        self.run_hist_btn.config(state=tk.DISABLED)
        self.status_var.set("Running historical price matcher...")
        self.hist_log.delete(1.0, tk.END)
        
        thread = threading.Thread(target=self._run_historical_matcher_thread)
        thread.daemon = True
        thread.start()
    
    def _run_historical_matcher_thread(self):
        """Historical matcher thread function."""
        try:
            import sys
            import io
            
            url = self.hist_url_entry.get().strip()
            skip_scraping = self.skip_scraping.get()
            force_scrape = self.force_scrape.get()
            only_insufficient = self.only_insufficient.get()
            batch_size = int(self.hist_batch_entry.get() or "10")
            limit_str = self.hist_limit_entry.get().strip()
            limit = int(limit_str) if limit_str else None
            
            # Build command line args
            sys.argv = ['match_historical_prices.py']
            if url:
                sys.argv.extend(['--bat-search-url', url])
            if skip_scraping:
                sys.argv.append('--skip-scraping')
            if force_scrape:
                sys.argv.append('--force-scrape')
            if only_insufficient:
                sys.argv.append('--only-insufficient-data')
            sys.argv.extend(['--batch-size', str(batch_size)])
            if limit:
                sys.argv.extend(['--limit', str(limit)])
            
            # Capture stdout
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            
            try:
                from match_historical_prices import main
                main()
                output = sys.stdout.getvalue()
                self.log_to_text(self.hist_log, output)
            finally:
                sys.stdout = old_stdout
            
            self.status_var.set("Ready")
            
        except Exception as e:
            self.log_to_text(self.hist_log, f"Error: {str(e)}")
            import traceback
            self.log_to_text(self.hist_log, traceback.format_exc())
            self.status_var.set("Error occurred")
        finally:
            self.run_hist_btn.config(state=tk.NORMAL)
    
    def validate_config(self):
        """Validate that required configuration is set."""
        errors = []
        
        # Reload config in case it was updated
        import importlib
        importlib.reload(config)
        
        if not config.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY not set (required for condition analysis)")
        
        if not config.GOOGLE_SHEETS_CREDENTIALS_PATH:
            errors.append("GOOGLE_SHEETS_CREDENTIALS_PATH not set")
        
        if not config.GOOGLE_SHEET_ID:
            errors.append("GOOGLE_SHEET_ID not set")
        
        if errors:
            error_msg = "\n".join(errors)
            error_msg += "\n\nPlease configure these settings in the Settings tab."
            messagebox.showerror("Configuration Error", error_msg)
            return False
        
        return True


def main():
    """Main entry point for GUI application."""
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

