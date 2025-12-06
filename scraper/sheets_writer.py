"""Google Sheets integration for writing Porsche listing data."""
import gspread
from google.oauth2.service_account import Credentials
import config
import logging

logger = logging.getLogger(__name__)


class SheetsWriter:
    """Handles writing data to Google Sheets."""
    
    def __init__(self):
        """Initialize the Google Sheets client."""
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_file(
                config.GOOGLE_SHEETS_CREDENTIALS_PATH,
                scopes=scopes
            )
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_key(config.GOOGLE_SHEET_ID)
            
            # Get or create the porsche_data worksheet
            try:
                self.worksheet = self.sheet.worksheet(config.SHEET_NAME)
            except gspread.exceptions.WorksheetNotFound:
                self.worksheet = self.sheet.add_worksheet(
                    title=config.SHEET_NAME,
                    rows=1000,
                    cols=len(config.COLUMNS)
                )
                # Add header row
                self.worksheet.append_row(config.COLUMNS)
                logger.info(f"Created new worksheet: {config.SHEET_NAME}")
            
            logger.info(f"Connected to Google Sheet: {config.SHEET_NAME}")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            raise
    
    def append_row(self, row_data):
        """
        Append a row to the sheet.
        
        Args:
            row_data: List of values [model_year, model_type, mileage, condition, source]
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check for duplicates based on source URL
            if self._is_duplicate(row_data[-1]):  # source is last column
                logger.info(f"Skipping duplicate: {row_data[-1]}")
                return False
            
            self.worksheet.append_row(row_data)
            logger.info(f"Added row: {row_data}")
            return True
        except Exception as e:
            logger.error(f"Failed to append row: {e}")
            return False
    
    def _is_duplicate(self, source_url):
        """
        Check if a listing with this source URL already exists.
        
        Args:
            source_url: The source URL to check
        
        Returns:
            bool: True if duplicate exists, False otherwise
        """
        try:
            # Get all existing source URLs (last column)
            all_values = self.worksheet.get_all_values()
            if len(all_values) <= 1:  # Only header row
                return False
            
            # Check if URL exists in source column (index 4)
            for row in all_values[1:]:  # Skip header
                if len(row) > 4 and row[4] == source_url:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Error checking for duplicates: {e}")
            return False  # If we can't check, allow the write
    
    def batch_append(self, rows_data):
        """
        Append multiple rows at once for better performance.
        
        Args:
            rows_data: List of row data lists
        
        Returns:
            int: Number of rows successfully added
        """
        new_rows = []
        for row_data in rows_data:
            if not self._is_duplicate(row_data[-1]):
                new_rows.append(row_data)
        
        if not new_rows:
            logger.info("No new rows to add (all duplicates)")
            return 0
        
        try:
            self.worksheet.append_rows(new_rows)
            logger.info(f"Added {len(new_rows)} rows in batch")
            return len(new_rows)
        except Exception as e:
            logger.error(f"Failed to batch append rows: {e}")
            return 0

