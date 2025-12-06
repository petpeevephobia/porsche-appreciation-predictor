"""Script to rename existing images to the new naming format and update the sheet."""
import json
import logging
import os
import re
import sys
import time
import uuid
import gspread
from google.oauth2.service_account import Credentials
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rename_images.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def get_listing_id_from_filename(filename):
    """Extract listing ID from filename (e.g., 'p00001_front.jpg' -> 'p00001')."""
    match = re.match(r'^(p\d+)', filename)
    if match:
        return match.group(1)
    return None


def rename_images_in_directory(image_dir):
    """
    Rename all images in the directory to the new format.
    
    Returns:
        dict: Mapping of old filenames to new filenames, grouped by listing_id
    """
    if not os.path.exists(image_dir):
        logger.error(f"Image directory does not exist: {image_dir}")
        return {}
    
    # Get all image files
    all_files = [f for f in os.listdir(image_dir) 
                 if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    # Group by listing ID
    images_by_listing = {}
    for filename in all_files:
        listing_id = get_listing_id_from_filename(filename)
        if listing_id:
            if listing_id not in images_by_listing:
                images_by_listing[listing_id] = []
            images_by_listing[listing_id].append(filename)
    
    logger.info(f"Found {len(all_files)} images for {len(images_by_listing)} listings")
    
    # Rename images for each listing
    # Use two-phase rename to avoid conflicts when mixing old and new format images
    rename_mapping = {}  # {listing_id: {old_filename: new_filename}}
    
    for listing_id, filenames in sorted(images_by_listing.items()):
        # Sort filenames alphabetically to maintain consistent ordering
        filenames.sort()
        
        rename_mapping[listing_id] = {}
        temp_mapping = {}  # {old_filename: temp_filename}
        
        # Phase 1: Rename all to temporary names with unique suffix to avoid conflicts
        unique_suffix = str(uuid.uuid4())[:8]
        
        for idx, old_filename in enumerate(filenames, 1):
            _, ext = os.path.splitext(old_filename)
            if not ext:
                ext = '.jpg'  # Default
            
            temp_filename = f"{listing_id}_temp_{unique_suffix}_{idx}{ext}"
            old_path = os.path.join(image_dir, old_filename)
            temp_path = os.path.join(image_dir, temp_filename)
            
            try:
                os.rename(old_path, temp_path)
                temp_mapping[old_filename] = temp_filename
                logger.debug(f"Phase 1: {old_filename} -> {temp_filename}")
            except Exception as e:
                logger.error(f"Error renaming {old_filename} to temp: {e}")
                continue
        
        # Phase 2: Rename from temp to final format
        for idx, old_filename in enumerate(filenames, 1):
            _, ext = os.path.splitext(old_filename)
            if not ext:
                ext = '.jpg'
            
            new_filename = f"{listing_id}_image_{idx}{ext}"
            temp_filename = temp_mapping.get(old_filename)
            
            if temp_filename:
                temp_path = os.path.join(image_dir, temp_filename)
                new_path = os.path.join(image_dir, new_filename)
                
                try:
                    os.rename(temp_path, new_path)
                    rename_mapping[listing_id][old_filename] = new_filename
                    logger.debug(f"Phase 2: {temp_filename} -> {new_filename}")
                except Exception as e:
                    logger.error(f"Error renaming {temp_filename} to {new_filename}: {e}")
        
        renamed_count = len([v for v in rename_mapping[listing_id].values() if v])
        logger.info(f"Renamed {renamed_count} images for listing {listing_id}")
    
    return rename_mapping


def fix_incorrect_image_paths_in_sheet():
    """
    Fix image paths in the sheet that reference files with old naming format.
    Checks if files exist and updates paths to match actual files on disk.
    """
    try:
        # Initialize Google Sheets client
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_file(
            config.GOOGLE_SHEETS_CREDENTIALS_PATH,
            scopes=scopes
        )
        sheets_client = gspread.authorize(creds)
        sheet = sheets_client.open_by_key(config.GOOGLE_SHEET_ID)
        worksheet = sheet.worksheet(config.SHEET_NAME)
        
        # Read all rows
        all_rows = worksheet.get_all_values()
        if len(all_rows) <= 1:
            logger.warning("No data rows found in sheet")
            return 0
        
        # Find column indices
        header_row = all_rows[0]
        try:
            id_idx = header_row.index('id')
            image_paths_idx = header_row.index('image_paths')
        except ValueError as e:
            logger.error(f"Required column not found: {e}")
            logger.error(f"Available columns: {header_row}")
            return 0
        
        image_dir = config.IMAGE_SAVE_PATH
        
        # Helper function to get relative path from project root
        def get_relative_path(filename):
            return f"project/data/images/{filename}"
        
        updated_count = 0
        fixed_count = 0
        
        logger.info("Scanning sheet for incorrect image paths (old naming format)...")
        
        # Process each row
        for row_idx, row in enumerate(all_rows[1:], start=2):
            if len(row) <= max(id_idx, image_paths_idx):
                continue
            
            listing_id = row[id_idx].strip() if len(row) > id_idx else ''
            image_paths_json = row[image_paths_idx].strip() if len(row) > image_paths_idx else ''
            
            if not listing_id or not image_paths_json:
                continue
            
            try:
                # Parse existing image paths
                old_paths = json.loads(image_paths_json)
                if not isinstance(old_paths, list):
                    continue
                
                # Check if paths use old naming format (e.g., p00158_other.jpg instead of p00158_image_1.jpg)
                # Old format patterns: _front, _back, _side_left, _side_right, _other (with optional _number suffix)
                old_pattern = re.compile(rf'^{re.escape(listing_id)}_(front|back|side_left|side_right|other)(?:_\d+)?\.(jpg|jpeg|png)$', re.IGNORECASE)
                
                needs_fix = False
                for old_path in old_paths:
                    # Extract filename from path
                    filename = os.path.basename(old_path)
                    # Check if it matches old naming pattern
                    if old_pattern.match(filename):
                        needs_fix = True
                        break
                    # Also check if file doesn't exist
                    filepath = os.path.join(image_dir, filename)
                    if not os.path.exists(filepath):
                        needs_fix = True
                        break
                
                if not needs_fix:
                    continue  # All files exist, skip this row
                
                # Find actual files for this listing ID
                actual_files = [f for f in os.listdir(image_dir) 
                               if f.startswith(f"{listing_id}_image_") and 
                               f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                actual_files.sort()  # Sort alphabetically for consistent ordering
                
                if not actual_files:
                    logger.warning(f"No actual image files found for listing {listing_id} (row {row_idx})")
                    continue
                
                # Create new paths from actual files
                new_paths = [get_relative_path(f) for f in actual_files]
                
                # Update sheet if paths changed
                if new_paths != old_paths:
                    new_paths_json = json.dumps(new_paths)
                    worksheet.update_cell(row_idx, image_paths_idx + 1, new_paths_json)
                    updated_count += 1
                    fixed_count += len(new_paths) - len(old_paths)
                    logger.info(f"Fixed image paths for listing {listing_id} (row {row_idx}): {len(old_paths)} old paths -> {len(new_paths)} new paths")
                    
                    # Better rate limiting - wait longer between updates
                    time.sleep(1.0)
                
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in image_paths for listing {listing_id} (row {row_idx})")
                continue
            except Exception as e:
                logger.error(f"Error updating row {row_idx} for listing {listing_id}: {e}")
                # If rate limited, wait longer before continuing
                if '429' in str(e) or 'Quota exceeded' in str(e):
                    logger.warning("Rate limit hit, waiting 60 seconds before continuing...")
                    time.sleep(60)
                continue
        
        logger.info(f"Fixed {fixed_count} incorrect image paths across {updated_count} listings in the sheet")
        return updated_count
        
    except Exception as e:
        logger.error(f"Error fixing incorrect image paths in sheet: {e}", exc_info=True)
        return 0


def fix_absolute_paths_in_sheet():
    """
    Fix any absolute paths in the sheet by converting them to relative paths.
    This handles cases where paths were skipped due to API rate limits.
    """
    try:
        # Initialize Google Sheets client
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_file(
            config.GOOGLE_SHEETS_CREDENTIALS_PATH,
            scopes=scopes
        )
        sheets_client = gspread.authorize(creds)
        sheet = sheets_client.open_by_key(config.GOOGLE_SHEET_ID)
        worksheet = sheet.worksheet(config.SHEET_NAME)
        
        # Read all rows
        all_rows = worksheet.get_all_values()
        if len(all_rows) <= 1:
            logger.warning("No data rows found in sheet")
            return 0
        
        # Find column indices
        header_row = all_rows[0]
        try:
            id_idx = header_row.index('id')
            image_paths_idx = header_row.index('image_paths')
        except ValueError as e:
            logger.error(f"Required column not found: {e}")
            logger.error(f"Available columns: {header_row}")
            return 0
        
        # Helper function to get relative path from project root
        def get_relative_path(filename):
            return f"project/data/images/{filename}"
        
        # Helper function to check if path is absolute
        def is_absolute_path(path):
            # Check for Windows absolute paths (C:\, D:\, etc.) or Unix absolute paths (/)
            return (os.path.isabs(path) or 
                    path.startswith('C:/') or path.startswith('C:\\') or
                    path.startswith('D:/') or path.startswith('D:\\') or
                    'Users' in path and ('C:' in path or 'D:' in path))
        
        updated_count = 0
        fixed_count = 0
        
        logger.info("Scanning sheet for absolute paths to convert...")
        
        # Process each row
        for row_idx, row in enumerate(all_rows[1:], start=2):
            if len(row) <= max(id_idx, image_paths_idx):
                continue
            
            listing_id = row[id_idx].strip() if len(row) > id_idx else ''
            image_paths_json = row[image_paths_idx].strip() if len(row) > image_paths_idx else ''
            
            if not listing_id or not image_paths_json:
                continue
            
            try:
                # Parse existing image paths
                old_paths = json.loads(image_paths_json)
                if not isinstance(old_paths, list):
                    continue
                
                # Check if any paths are absolute
                has_absolute = any(is_absolute_path(path) for path in old_paths)
                if not has_absolute:
                    continue  # Skip if all paths are already relative
                
                # Convert absolute paths to relative
                new_paths = []
                for old_path in old_paths:
                    if is_absolute_path(old_path):
                        # Extract filename and convert to relative path
                        filename = os.path.basename(old_path)
                        new_path = get_relative_path(filename)
                        new_paths.append(new_path)
                        fixed_count += 1
                    else:
                        # Already relative, keep it
                        new_paths.append(old_path)
                
                # Update sheet if paths changed
                if new_paths != old_paths:
                    new_paths_json = json.dumps(new_paths)
                    worksheet.update_cell(row_idx, image_paths_idx + 1, new_paths_json)
                    updated_count += 1
                    logger.info(f"Fixed absolute paths for listing {listing_id} (row {row_idx}): {len([p for p in old_paths if is_absolute_path(p)])} paths converted")
                    
                    # Better rate limiting - wait longer between updates
                    time.sleep(1.0)  # Increased from 0.5 to 1.0 seconds
                
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in image_paths for listing {listing_id} (row {row_idx})")
                continue
            except Exception as e:
                logger.error(f"Error updating row {row_idx} for listing {listing_id}: {e}")
                # If rate limited, wait longer before continuing
                if '429' in str(e) or 'Quota exceeded' in str(e):
                    logger.warning("Rate limit hit, waiting 60 seconds before continuing...")
                    time.sleep(60)
                continue
        
        logger.info(f"Fixed {fixed_count} absolute paths across {updated_count} listings in the sheet")
        return updated_count
        
    except Exception as e:
        logger.error(f"Error fixing absolute paths in sheet: {e}", exc_info=True)
        return 0


def update_sheet_image_paths(rename_mapping):
    """
    Update image paths in the Google Sheet.
    
    Args:
        rename_mapping: Dict mapping listing_id to {old_filename: new_filename}
    """
    try:
        # Initialize Google Sheets client
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_file(
            config.GOOGLE_SHEETS_CREDENTIALS_PATH,
            scopes=scopes
        )
        sheets_client = gspread.authorize(creds)
        sheet = sheets_client.open_by_key(config.GOOGLE_SHEET_ID)
        worksheet = sheet.worksheet(config.SHEET_NAME)
        
        # Read all rows
        all_rows = worksheet.get_all_values()
        if len(all_rows) <= 1:
            logger.warning("No data rows found in sheet")
            return
        
        # Find column indices
        header_row = all_rows[0]
        try:
            id_idx = header_row.index('id')
            image_paths_idx = header_row.index('image_paths')
        except ValueError as e:
            logger.error(f"Required column not found: {e}")
            logger.error(f"Available columns: {header_row}")
            return
        
        image_dir = config.IMAGE_SAVE_PATH
        updated_count = 0
        
        # Process each row
        for row_idx, row in enumerate(all_rows[1:], start=2):
            if len(row) <= max(id_idx, image_paths_idx):
                continue
            
            listing_id = row[id_idx].strip() if len(row) > id_idx else ''
            image_paths_json = row[image_paths_idx].strip() if len(row) > image_paths_idx else ''
            
            if not listing_id or not image_paths_json:
                continue
            
            # Skip if this listing doesn't have renamed images
            if listing_id not in rename_mapping:
                continue
            
            try:
                # Parse existing image paths
                old_paths = json.loads(image_paths_json)
                if not isinstance(old_paths, list):
                    continue
                
                # Create mapping of old basename to new basename for this listing
                filename_mapping = rename_mapping[listing_id]
                
                # Helper function to get relative path from project root
                def get_relative_path(filename):
                    return f"project/data/images/{filename}"
                
                # Update paths
                new_paths = []
                for old_path in old_paths:
                    # Extract filename from path (handle both absolute and relative paths)
                    old_basename = os.path.basename(old_path)
                    
                    if old_basename in filename_mapping:
                        new_basename = filename_mapping[old_basename]
                        # Use relative path from project root
                        new_path = get_relative_path(new_basename)
                        new_paths.append(new_path)
                    else:
                        # If path is already relative, keep it; otherwise convert to relative
                        if old_path.startswith('project/'):
                            new_paths.append(old_path)
                        else:
                            # Convert absolute path to relative
                            new_paths.append(get_relative_path(old_basename))
                
                # Update sheet if paths changed
                if new_paths != old_paths:
                    new_paths_json = json.dumps(new_paths)
                    worksheet.update_cell(row_idx, image_paths_idx + 1, new_paths_json)
                    updated_count += 1
                    logger.info(f"Updated image paths for listing {listing_id} (row {row_idx})")
                    
                    # Better rate limiting - wait longer between updates
                    time.sleep(1.0)  # Increased from 0.5 to 1.0 seconds
                
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in image_paths for listing {listing_id} (row {row_idx})")
                continue
            except Exception as e:
                logger.error(f"Error updating row {row_idx} for listing {listing_id}: {e}")
                # If rate limited, wait longer before continuing
                if '429' in str(e) or 'Quota exceeded' in str(e):
                    logger.warning("Rate limit hit, waiting 60 seconds before continuing...")
                    time.sleep(60)
                continue
        
        logger.info(f"Updated image paths for {updated_count} listings in the sheet")
        
    except Exception as e:
        logger.error(f"Error updating sheet: {e}", exc_info=True)


def main():
    """Main execution function."""
    logger.info("Starting image renaming process...")
    
    # Validate configuration
    if not config.GOOGLE_SHEETS_CREDENTIALS_PATH:
        logger.error("GOOGLE_SHEETS_CREDENTIALS_PATH not set in environment variables")
        sys.exit(1)
    
    if not config.GOOGLE_SHEET_ID:
        logger.error("GOOGLE_SHEET_ID not set in environment variables")
        sys.exit(1)
    
    image_dir = config.IMAGE_SAVE_PATH
    logger.info(f"Image directory: {image_dir}")
    
    # Step 1: Rename images
    logger.info("Step 1: Renaming images in directory...")
    rename_mapping = rename_images_in_directory(image_dir)
    
    if rename_mapping:
        total_renamed = sum(len(mapping) for mapping in rename_mapping.values())
        logger.info(f"Renamed {total_renamed} images total")
    else:
        logger.info("No images needed renaming (may already be in correct format)")
        rename_mapping = {}  # Empty mapping, but continue to fix paths in sheet
    
    # Step 2: Update sheet with renamed images
    if rename_mapping:
        logger.info("Step 2: Updating image paths in Google Sheet for renamed images...")
        update_sheet_image_paths(rename_mapping)
    
    # Step 3: Fix any remaining absolute paths in sheet (handles skipped rows from previous runs)
    logger.info("Step 3: Fixing any remaining absolute paths in Google Sheet...")
    fixed_absolute_count = fix_absolute_paths_in_sheet()
    
    if fixed_absolute_count > 0:
        logger.info(f"Fixed {fixed_absolute_count} rows with absolute paths")
    else:
        logger.info("No absolute paths found in sheet (all paths are already relative)")
    
    # Step 4: Fix incorrect image paths (old naming format like p00158_other.jpg)
    logger.info("Step 4: Fixing incorrect image paths (old naming format) in Google Sheet...")
    fixed_incorrect_count = fix_incorrect_image_paths_in_sheet()
    
    if fixed_incorrect_count > 0:
        logger.info(f"Fixed {fixed_incorrect_count} rows with incorrect image paths")
    else:
        logger.info("No incorrect image paths found in sheet (all paths match actual files)")
    
    logger.info("Image renaming process completed!")


if __name__ == "__main__":
    main()

