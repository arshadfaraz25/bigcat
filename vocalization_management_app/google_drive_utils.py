import os
import io
import logging
from django.conf import settings
from django.core.files.base import ContentFile
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import pickle

# Configure logging
logger = logging.getLogger(__name__)

# Define the scopes required for Google Drive access
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Google OAuth client configuration
CLIENT_CONFIG = {
    'web': {
        'client_id': '1054533644442-6ej1g4v9b3tqacjtbgvpvvhho6c1uu6m.apps.googleusercontent.com',
        'project_id': 'felidetect-drive-integration',
        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
        'token_uri': 'https://oauth2.googleapis.com/token',
        'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
        'client_secret': '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',
        'redirect_uris': ['http://localhost:8000/vocalization_management_app/oauth2callback/']
    }
}

# Path to the credentials file (legacy approach)
CREDENTIALS_PATH = os.path.join(settings.BASE_DIR, 'credentials.json')

# Path to service account key file (if using service account)
SERVICE_ACCOUNT_FILE = os.path.join(settings.BASE_DIR, 'service-account-key.json')

# Directory for storing tokens
TOKEN_DIR = os.path.join(settings.BASE_DIR, 'tokens')
os.makedirs(TOKEN_DIR, exist_ok=True)
TOKEN_PATH = os.path.join(TOKEN_DIR, 'google_drive_token.pickle')


def get_credentials(token_info=None):
    """
    Get or create credentials for Google Drive API.
    
    Args:
        token_info: Optional dictionary containing token information from browser authentication
    
    Returns:
        Google OAuth2 credentials object
    """
    # If token_info is provided (from browser authentication), use it
    if token_info:
        try:
            return Credentials(
                token=token_info.get('access_token'),
                refresh_token=token_info.get('refresh_token'),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=CLIENT_CONFIG['web']['client_id'],
                client_secret=CLIENT_CONFIG['web']['client_secret'],
                scopes=SCOPES
            )
        except Exception as e:
            logger.error(f"Error creating credentials from token info: {e}")
            raise
    
    # Try to use service account if available
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        try:
            return service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        except Exception as e:
            logger.warning(f"Error loading service account credentials: {e}. Falling back to OAuth.")
    
    # Fall back to OAuth flow
    creds = None
    
    # Check if token file exists
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            try:
                creds = pickle.load(token)
            except Exception as e:
                logger.warning(f"Error loading token: {e}")
    
    # If no valid credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                os.remove(TOKEN_PATH) if os.path.exists(TOKEN_PATH) else None
                return get_credentials()  # Retry after removing invalid token
        else:
            # Create a flow instance using client config
            flow = Flow.from_client_config(
                CLIENT_CONFIG,
                scopes=SCOPES,
                redirect_uri=CLIENT_CONFIG['web']['redirect_uris'][0]
            )
            
            # Generate authorization URL for browser redirect
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            
            # Return the auth URL instead of credentials
            # The actual credentials will be obtained after the user authenticates
            return {
                'auth_url': auth_url,
                'requires_auth': True
            }
    
    return creds


def get_drive_service(token_info=None):
    """
    Create and return a Google Drive service instance.
    
    Args:
        token_info: Optional dictionary containing token information from browser authentication
    
    Returns:
        Google Drive API service instance or auth URL if authentication is required
    """
    try:
        creds = get_credentials(token_info)
        
        # If we got an auth URL instead of credentials, return it
        if isinstance(creds, dict) and 'auth_url' in creds:
            return creds
        
        # Otherwise build the service with the credentials
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error creating Drive service: {e}")
        raise


def is_valid_drive_url(url):
    """
    Check if a URL is a valid Google Drive URL.
    Validates against common Google Drive URL patterns.
    """
    if not url or not isinstance(url, str):
        return False
    
    # Normalize the URL by trimming whitespace
    url = url.strip()
    
    # Check if the URL is a Google Drive URL
    if 'drive.google.com' not in url:
        return False
    
    # Check for common Google Drive URL patterns
    valid_patterns = [
        '/folders/', # Folder URL
        '/file/d/',  # File URL
        'open?id=',  # Open URL
        '/drive/u/',  # User-specific folder URL
        '/my-drive/folders/' # My Drive folder URL
    ]
    
    return any(pattern in url for pattern in valid_patterns)


def extract_folder_id_from_url(url):
    """
    Extract the folder ID from a Google Drive URL.
    Handles various Google Drive URL formats.
    """
    try:
        # Check if the URL is valid
        if not is_valid_drive_url(url):
            logger.error(f"Invalid Google Drive URL: {url}")
            return None
        
        # Remove any whitespace and normalize the URL
        url = url.strip()
        
        # Extract folder ID from URL using various patterns
        folder_id = None
        
        # Pattern 1: https://drive.google.com/drive/folders/FOLDER_ID?usp=sharing
        if '/folders/' in url:
            parts = url.split('/folders/')
            if len(parts) > 1:
                folder_id = parts[1].split('?')[0].split('/')[0].strip()
        
        # Pattern 2: https://drive.google.com/drive/u/0/folders/FOLDER_ID
        elif '/u/' in url and '/folders/' in url:
            parts = url.split('/folders/')
            if len(parts) > 1:
                folder_id = parts[1].split('?')[0].split('/')[0].strip()
        
        # Pattern 3: https://drive.google.com/open?id=FOLDER_ID
        elif 'open?id=' in url:
            parts = url.split('open?id=')
            if len(parts) > 1:
                folder_id = parts[1].split('&')[0].strip()
                
        # Pattern 4: https://drive.google.com/file/d/FOLDER_ID/view?usp=sharing
        elif '/file/d/' in url:
            parts = url.split('/file/d/')
            if len(parts) > 1:
                folder_id = parts[1].split('/')[0].split('?')[0].strip()
                
        # Pattern 5: https://drive.google.com/drive/my-drive/folders/FOLDER_ID
        elif '/my-drive/folders/' in url:
            parts = url.split('/my-drive/folders/')
            if len(parts) > 1:
                folder_id = parts[1].split('?')[0].split('/')[0].strip()
        
        # Validate folder ID format (typically 33 characters)
        if folder_id and (len(folder_id) < 25 or len(folder_id) > 100 or ' ' in folder_id):
            logger.warning(f"Extracted folder ID may be invalid: {folder_id}")
        
        return folder_id
    
    except Exception as e:
        logger.error(f"Error extracting folder ID from URL: {e}")
        return None


def list_files_in_folder(folder_id, file_extensions=None, service=None):
    """
    List all files in a Google Drive folder.
    
    Args:
        folder_id: The ID of the Google Drive folder
        file_extensions: Optional list of file extensions to filter by (e.g., ['.wav'])
        service: Optional Google Drive service instance (if not provided, one will be created)
        
    Returns:
        List of file metadata dictionaries
    """
    try:
        # Use provided service or create a new one
        if service is None:
            service = get_drive_service()
            
            # If we need authentication, return empty list
            if isinstance(service, dict) and 'auth_url' in service:
                return []
        
        # Query for files in the specified folder
        query = f"'{folder_id}' in parents and trashed = false"
        
        # Add file extension filter if specified
        if file_extensions:
            extension_conditions = []
            for ext in file_extensions:
                # Ensure the extension starts with a dot
                if not ext.startswith('.'):
                    ext = '.' + ext
                extension_conditions.append(f"name ends with '{ext}'" )
            
            if extension_conditions:
                query += " and (" + " or ".join(extension_conditions) + ")"
        
        # Execute the query
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, mimeType, size)',
            pageSize=1000  # Adjust as needed
        ).execute()
        
        # Get the list of files
        files = results.get('files', [])
        
        # Filter out folders (we only want files)
        files_only = [f for f in files if f.get('mimeType') != 'application/vnd.google-apps.folder']
        
        return files_only
    
    except Exception as e:
        logger.error(f"Error listing files in folder {folder_id}: {e}")
        raise


def download_file_from_drive(file_id, file_name, service=None):
    """
    Download a file from Google Drive.
    
    Args:
        file_id: The ID of the file to download
        file_name: The name to save the file as
        service: Optional Google Drive service instance (if not provided, one will be created)
        
    Returns:
        Django ContentFile object containing the downloaded file
    """
    temp_file = None
    try:
        # Use provided service or create a new one
        if service is None:
            service = get_drive_service()
            
            # If we need authentication, return None
            if isinstance(service, dict) and 'auth_url' in service:
                return None
        
        request = service.files().get_media(fileId=file_id)
        
        # Download the file to a BytesIO object
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            logger.info(f"Download {file_name} {int(status.progress() * 100)}%")
        
        # Reset the file pointer to the beginning
        file_content.seek(0)
        
        # Create a Django ContentFile with sanitized filename
        # Replace any potentially problematic characters in the filename
        safe_filename = os.path.basename(file_name.replace('\\', '/').replace('/', '_'))
        django_file = ContentFile(file_content.read(), name=safe_filename)
        return django_file
    
    except Exception as e:
        logger.error(f"Error downloading file {file_id} ({file_name}): {e}")
        # Clean up any temporary files if they exist
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                logger.info(f"Cleaned up temporary file {temp_file}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up temporary file {temp_file}: {cleanup_error}")
        raise


def process_drive_folder(folder_id, animal_type, zoo, uploaded_by=None, token_info=None):
    """
    Process all audio files in a Google Drive folder.
    
    Args:
        folder_id: The ID of the Google Drive folder
        animal_type: The animal type to associate with the files
        zoo: The zoo to associate with the files
        uploaded_by: The user who initiated the upload
        token_info: Optional dictionary containing token information from browser authentication
        
    Returns:
        Dictionary with statistics about the processed files
    """
    from .models import OriginalAudioFile, ProcessingLog
    from .audio_processing import handle_duplicate_file, update_audio_metadata
    from django.utils.timezone import now
    
    stats = {
        'total': 0,
        'processed': 0,
        'failed': 0,
        'duplicates': 0,
        'errors': [],
        'requires_auth': False,
        'auth_url': None
    }
    
    temp_files = []  # Track temporary files for cleanup
    
    try:
        # Get drive service with token info if provided
        service_or_auth = get_drive_service(token_info)
        
        # If we need authentication, return the auth URL
        if isinstance(service_or_auth, dict) and 'auth_url' in service_or_auth:
            stats['requires_auth'] = True
            stats['auth_url'] = service_or_auth['auth_url']
            return stats
        
        # List all WAV files in the folder using the service
        files = list_files_in_folder(folder_id, file_extensions=['.wav'], service=service_or_auth)
        stats['total'] = len(files)
        
        # Process each file
        for file_info in files:
            file_id = file_info['id']
            file_name = file_info['name']
            temp_file_path = None
            
            try:
                # Download the file using the service
                django_file = download_file_from_drive(file_id, file_name, service=service_or_auth)
                
                # Handle duplicate file detection and replacement
                original_audio, is_duplicate, replaced_file_id = handle_duplicate_file(
                    new_file=django_file,
                    animal_type=animal_type,
                    zoo=zoo,
                    uploaded_by=uploaded_by
                )
                
                # Track duplicate count
                if is_duplicate:
                    stats['duplicates'] += 1
                
                # Update metadata
                file_path = original_audio.audio_file.path
                temp_files.append(file_path)  # Track the file path for potential cleanup
                update_audio_metadata(file_path, original_audio)
                
                # Create initial processing log
                ProcessingLog.objects.create(
                    audio_file=original_audio,
                    timestamp=now(),
                    level='INFO',
                    message=f'Audio file "{file_name}" uploaded from Google Drive successfully.'
                )
                
                stats['processed'] += 1
                
            except Exception as e:
                stats['failed'] += 1
                error_msg = f"Error processing {file_name}: {str(e)}"
                stats['errors'].append(error_msg)
                logger.error(error_msg)
                
                # Clean up any temporary files created during this file's processing
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                        logger.info(f"Cleaned up temporary file {temp_file_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to clean up temporary file {temp_file_path}: {cleanup_error}")
        
        return stats
    
    except Exception as e:
        error_msg = f"Error processing Google Drive folder: {str(e)}"
        stats['errors'].append(error_msg)
        logger.error(error_msg)
        
        # Clean up any temporary files in case of overall failure
        for temp_file in temp_files:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.info(f"Cleaned up temporary file {temp_file}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up temporary file {temp_file}: {cleanup_error}")
        
        return stats
