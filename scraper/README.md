# Porsche Web Scraper with Google Sheets Integration

A Python web scraper that extracts Porsche listing data from bringatrailer.com, analyzes condition using OpenAI GPT, and writes results to a Google Sheet.

## Features

- Scrapes Porsche listings from bringatrailer.com with pagination support
- Extracts: model year, model type (911/Cayman/Boxster), mileage, condition, source URL
- Uses OpenAI GPT to analyze listing descriptions and classify condition (Excellent/Good/Fair)
- Writes data to Google Sheets with duplicate detection
- Batch processing for efficient API usage

## Prerequisites

- Python 3.8 or higher
- OpenAI API key
- Google Cloud project with Sheets API enabled
- Google Sheets service account credentials

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Google Sheets Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sheets API and Google Drive API
4. Create a Service Account:
   - Go to "IAM & Admin" > "Service Accounts"
   - Click "Create Service Account"
   - Give it a name and click "Create and Continue"
   - Skip role assignment (or add "Editor" if needed)
   - Click "Done"
5. Create a key for the service account:
   - Click on the service account you just created
   - Go to "Keys" tab
   - Click "Add Key" > "Create new key"
   - Choose JSON format
   - Download the JSON file and save it securely
6. Create a Google Sheet:
   - Create a new Google Sheet
   - Note the Sheet ID from the URL: `https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit`
   - Share the sheet with the service account email (found in the JSON file) with "Editor" permissions

### 3. Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_SHEETS_CREDENTIALS_PATH=path/to/your/service-account-key.json
GOOGLE_SHEET_ID=your_google_sheet_id_here
```

**Important:** Never commit your `.env` file or service account JSON file to version control.

## Usage

Run the scraper with a URL to the bringatrailer.com search results page:

```bash
python main.py "https://bringatrailer.com/porsche/"
```

You can also specify a batch size (number of listings to process before writing to sheet):

```bash
python main.py "https://bringatrailer.com/porsche/" --batch-size 20
```

### Example

```bash
python main.py "https://bringatrailer.com/search/?q=porsche" --batch-size 15
```

## Output

The scraper will:
1. Extract all listing URLs from the search results page (handling pagination)
2. Scrape each listing for: model year, model type, mileage, description
3. Use OpenAI GPT to analyze the description and classify condition
4. Write rows to the Google Sheet "porsche_data" with columns:
   - `model_year`: Year of the vehicle
   - `model_type`: 911, Cayman, or Boxster
   - `mileage`: Vehicle mileage
   - `condition`: Excellent, Good, or Fair (determined by AI)
   - `source`: URL of the listing

The scraper automatically skips duplicate listings (based on source URL).

## Configuration

Edit `config.py` to adjust:
- OpenAI model (default: gpt-3.5-turbo)
- Request delay between scrapes
- Sheet name
- Column names

## Logging

The scraper logs to both console and `scraper.log` file. Check the log file for detailed information about the scraping process.

## Error Handling

- Network errors: The scraper will retry and continue with the next listing
- Missing data: Empty strings are used for missing fields
- API errors: Defaults to "Good" condition if OpenAI analysis fails
- Duplicate detection: Automatically skips listings already in the sheet

## Notes

- The scraper includes rate limiting to be respectful to bringatrailer.com
- OpenAI API calls have a small delay to avoid rate limits
- Large batches may take significant time due to API rate limiting
- Ensure your OpenAI account has sufficient credits

## Troubleshooting

**"OPENAI_API_KEY not found"**
- Make sure your `.env` file exists and contains the API key

**"Failed to initialize Google Sheets"**
- Verify the service account JSON path is correct
- Ensure the service account email has access to the Google Sheet
- Check that Google Sheets API is enabled in your Google Cloud project

**"No listing URLs found"**
- Verify the URL is correct and accessible
- Check that the page structure hasn't changed (may need to update selectors)

**Empty or incorrect data extracted**
- The website structure may have changed
- Check `scraper.log` for detailed error messages
- You may need to update the CSS selectors in `scraper.py`

