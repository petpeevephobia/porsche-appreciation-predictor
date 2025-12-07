# Porsche Scraper GUI Application

## Quick Start

### Option 1: Double-click the batch file (shows console)
- Double-click `Porsche Scraper.bat` or `run_gui.bat`
- A console window will appear briefly, then the GUI will open

### Option 2: Double-click the VBScript (no console window)
- Double-click `Porsche Scraper.vbs`
- The GUI will open without showing a console window

## Requirements

- Python 3.8 or higher must be installed
- All dependencies from `requirements.txt` must be installed
- Environment variables must be configured (see main README)

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Or if using a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Double-click `Porsche Scraper.vbs` to launch the GUI

## Troubleshooting

**"Python is not recognized"**
- Make sure Python is installed and added to your system PATH
- Or edit the `.bat` file to use the full path to Python

**Application doesn't start**
- Check that all dependencies are installed: `pip install -r requirements.txt`
- Verify your `.env` file is configured correctly
- Check the console window for error messages

**ModuleNotFoundError**
- Make sure you've installed all dependencies: `pip install -r requirements.txt`
- If using a venv, make sure it's activated before installing dependencies

