from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os
import json
import sys
from app.audio_processor import AudioProcessor
from app.utils import update_account_token
import tempfile
import logging
import traceback
import google.oauth2.credentials
import google_auth_oauthlib.flow
import google.auth.transport.requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = '/tmp/uploads'
ALLOWED_EXTENSIONS = {'mp4', 'mov'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB limit

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def clean_title(title, hashtags=None, max_length=100):
    # Strip forbidden characters
    clean = re.sub(r'[<>:{}\[\]|\\^~"\'`]', '', title)
    
    # Remove extra whitespace
    clean = ' '.join(clean.split())
    
    # Prepare hashtags
    if hashtags and hashtags[0]:
        # Remove any existing '#' from the hashtags before adding them
        cleaned_hashtags = [tag.strip().lstrip('#') for tag in hashtags if tag.strip()]
        hashtag_text = ' ' + ' '.join(f'#{tag}' for tag in cleaned_hashtags)
        hashtag_text += ' #Shorts'
    else:
        hashtag_text = ' #Shorts'
    
    # Calculate available space for title (subtracting space for hashtags)
    available_length = max_length - len(hashtag_text)
    
    # Truncate to available length while preserving whole words
    clean = clean.strip()
    if len(clean) > available_length:
        # Split into words and start trimming
        words = clean.split()
        truncated = ''
        for word in words:
            if len(truncated) + len(word) + 1 <= available_length:
                truncated += word + ' '
            else:
                break
        clean = truncated.strip()
    
    # Combine title with hashtags
    return clean + hashtag_text

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_accounts():
    try:
        with open('/app/config/accounts.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("accounts.json not found in /app/config/")
        raise
    except json.JSONDecodeError:
        logger.error("accounts.json is not valid JSON")
        raise

def cleanup_temp_files(files):
    """Safely cleanup temporary files"""
    for file_path in files:
        try:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
                logger.debug(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logger.error(f"Error cleaning up {file_path}: {str(e)}")

def find_sound_file(sound_name):
    """Find a sound file regardless of case or spaces"""
    sounds_dir = '/app/sounds'
    try:
        # Strip any quotes from the sound name
        sound_name = sound_name.strip("'\"")
        logger.info(f"Looking for sound file with name: {sound_name}")
        
        # List all files in the sounds directory
        files = os.listdir(sounds_dir)
        logger.info(f"Available sound files: {files}")
        
        for filename in files:
            base_name = filename.lower().rsplit('.', 1)[0]
            logger.info(f"Comparing {base_name} with {sound_name.lower()}")
            if base_name == sound_name.lower():
                full_path = os.path.join(sounds_dir, filename)
                logger.info(f"Found matching sound file: {full_path}")
                return full_path
        logger.error(f"No matching sound file found for {sound_name}")
        return None
    except Exception as e:
        logger.error(f"Error searching for sound file: {str(e)}")
        return None

def get_youtube_service(credentials_data, account_name=None):
    try:
        # Create a Request object for token refresh
        request = google.auth.transport.requests.Request()
        
        # Initialize credentials, treating None as a non-existent token
        token = credentials_data.get('token')
        if token == 'None':
            token = None
            
        credentials = google.oauth2.credentials.Credentials(
            token=token,
            refresh_token=credentials_data['refresh_token'],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=credentials_data['client_id'],
            client_secret=credentials_data['client_secret']
        )
        
        # Log credential info for debugging (excluding sensitive info)
        logger.info(f"Credentials initialized for YouTube API. Token present: {bool(token)}, Refresh token present: {bool(credentials_data.get('refresh_token'))}, Client ID present: {bool(credentials_data.get('client_id'))}, Client Secret present: {bool(credentials_data.get('client_secret'))}")
        
        # Force token refresh if no token or token is expired
        if not token or credentials.expired:
            logger.info("No token or token expired, refreshing token")
            try:
                credentials.refresh(request)
                logger.info("Token refreshed successfully")
                
                # Save the new token back to the accounts.json file
                if credentials.token and account_name:
                    logger.info(f"Saving new token for future use for account {account_name}")
                    # Also save the token expiry time if available
                    if hasattr(credentials, 'expiry') and credentials.expiry:
                        expiry_iso = credentials.expiry.isoformat()
                        update_account_token(account_name, credentials.token, expiry_iso)
                    else:
                        update_account_token(account_name, credentials.token)
                elif credentials.token:
                    logger.warning("Token refreshed but no account name provided, can't save token")
                else:
                    logger.warning("No token received after refresh")
                
            except Exception as refresh_error:
                logger.error(f"Token refresh failed: {str(refresh_error)}")
                
                # If refresh_token is invalid, we might need to guide the user to re-authenticate
                if 'invalid_grant' in str(refresh_error).lower():
                    logger.error("The refresh token appears to be invalid or expired. User needs to re-authenticate.")
                    raise Exception("OAuth refresh token is invalid. Please re-authenticate the YouTube account.")
                raise
        
        return build('youtube', 'v3', credentials=credentials)
    except Exception as e:
        logger.error(f"Error initializing YouTube service: {str(e)}")
        raise

@app.route('/upload', methods=['POST'])
def upload_video():
    temp_files = []  # Keep track of temporary files to clean up

    try:
        # Validate request content type
        if not request.content_type or 'multipart/form-data' not in request.content_type:
            return jsonify({'error': 'Invalid content type. Must be multipart/form-data'}), 400

        # Check if video file is provided
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400
        
        video = request.files['video']
        if not video or not video.filename:
            return jsonify({'error': 'No video file selected'}), 400
        
        if not allowed_file(video.filename):
            return jsonify({'error': f'Invalid file type. Allowed types are: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

        # Get and validate parameters
        title = request.form.get('description', '')
        accountname = request.form.get('accountname')
        hashtags = request.form.get('hashtags', '').split(',') if request.form.get('hashtags') else []
        sound_name = request.form.get('sound_name')
        sound_aud_vol = request.form.get('sound_aud_vol', 'mix')

        if not accountname:
            return jsonify({'error': 'Account name is required'}), 400

        # Load account credentials
        try:
            accounts = load_accounts()
        except Exception as e:
            logger.error(f"Error loading accounts: {str(e)}")
            return jsonify({'error': 'Error loading account configuration'}), 500

        if accountname not in accounts:
            return jsonify({'error': 'Account not found'}), 404

        # Save video to a temporary file with a unique name
        temp_suffix = os.urandom(8).hex()
        temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=f'_{temp_suffix}.mp4')
        temp_files.append(temp_video.name)
        
        try:
            video.save(temp_video.name)
            logger.info(f"Video saved temporarily as {temp_video.name}")
        except Exception as e:
            logger.error(f"Error saving video file: {str(e)}")
            return jsonify({'error': 'Error saving video file'}), 500

        # Process audio if sound is specified
        final_video_path = temp_video.name
        if sound_name:
            sound_path = find_sound_file(sound_name)
            if not sound_path:
                logger.error(f"Sound file not found for name: {sound_name}")
                return jsonify({'error': f'Sound file not found: {sound_name}'}), 404
            
            try:
                processor = AudioProcessor()
                final_video_path = processor.mix_audio(
                    temp_video.name,
                    sound_path,
                    sound_aud_vol
                )
                temp_files.append(final_video_path)
                logger.info(f"Audio processing completed: {final_video_path}")
            except Exception as e:
                logger.error(f"Error processing audio: {str(e)}")
                return jsonify({'error': f'Error processing audio: {str(e)}'}), 500

        # Process hashtags
        if hashtags and hashtags[0]:  # Remove any existing '#' from the hashtags
            cleaned_hashtags = [tag.strip().lstrip('#') for tag in hashtags if tag.strip()]
        else:
            cleaned_hashtags = []

        # Upload to YouTube
        try:
            youtube = get_youtube_service(accounts[accountname], accountname)

            # Clean up the title, passing cleaned hashtags
            clean_video_title = clean_title(title, cleaned_hashtags)
            
            logger.info(f"Using video title: {clean_video_title}")

            # Prepare description
            # If the original title is different from the clean title, use the full title in description
            description = title if len(title) > len(clean_video_title.split(' #Shorts')[0]) else ''

            request_body = {
                'snippet': {
                    'title': clean_video_title,
                    'description': description,
                    'tags': cleaned_hashtags,
                    'categoryId': '22'
                },
                'status': {
                    'privacyStatus': 'public',
                    'selfDeclaredMadeForKids': False
                }
            }

            media = MediaFileUpload(
                final_video_path,
                chunksize=-1,
                resumable=True
            )

            insert_request = youtube.videos().insert(
                part='snippet,status',
                body=request_body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = insert_request.next_chunk()
                if status:
                    logger.info(f"Uploaded {int(status.progress() * 100)}%")

            video_id = response['id']
            logger.info(f"Successfully uploaded video to YouTube. Video ID: {video_id}")
            
            return jsonify({
                'success': True,
                'message': 'Video uploaded successfully',
                'video_id': video_id,
                'url': f'https://youtube.com/shorts/{video_id}'
            })

        except HttpError as e:
            try:
                error_content = json.loads(e.content.decode('utf-8'))
                error_reason = error_content.get('error', {}).get('errors', [{}])[0].get('reason', '')
                error_message = error_content.get('error', {}).get('message', str(e))
                error_details = error_content.get('error', {}).get('errors', [{}])[0]
                
                logger.error(f"Error uploading to YouTube: {error_reason}: {error_message}")
                logger.error(f"Error details: {error_details}")
                
                return jsonify({
                    'error': f'Error uploading to YouTube: {error_reason}: {error_message}',
                    'details': error_details
                }), 500
            except Exception as parse_error:
                logger.error(f"Error parsing HttpError: {str(e)} / Parser error: {str(parse_error)}")
                logger.error(f"Raw error content: {e.content[:500] if hasattr(e, 'content') else 'No content'}")
                return jsonify({'error': f'Error uploading to YouTube: {str(e)}'}), 500
        except Exception as e:
            logger.error(f"Error uploading to YouTube: {str(e)}")
            return jsonify({'error': f'Error uploading to YouTube: {str(e)}'}), 500

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Unexpected error in upload_video: {str(e)}\n{error_trace}")
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500
    
    finally:
        # Cleanup temporary files
        cleanup_temp_files(temp_files)

@app.route('/check-account', methods=['GET'])
def check_account():
    try:
        accountname = request.args.get('accountname')
        
        if not accountname:
            return jsonify({'error': 'Account name is required as a query parameter'}), 400
            
        # Load account credentials
        try:
            accounts = load_accounts()
        except Exception as e:
            logger.error(f"Error loading accounts: {str(e)}")
            return jsonify({'error': 'Error loading account configuration'}), 500
            
        if accountname not in accounts:
            return jsonify({'error': 'Account not found'}), 404
            
        account_data = accounts[accountname]
        
        # Create a sanitized version of the account data (without sensitive info)
        safe_data = {
            'account': accountname,
            'has_token': bool(account_data.get('token')),
            'has_refresh_token': bool(account_data.get('refresh_token')),
            'token_expiry': account_data.get('token_expiry'),
            'channel_title': account_data.get('channel_title', 'Unknown'),
            'scopes': account_data.get('scopes', [])
        }
        
        return jsonify({
            'success': True,
            'account_info': safe_data
        })
            
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Unexpected error in check_account: {str(e)}\n{error_trace}")
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

@app.route('/refresh-token', methods=['POST'])
def refresh_token():
    try:
        data = request.get_json()
        accountname = data.get('accountname')
        
        if not accountname:
            return jsonify({'error': 'Account name is required'}), 400
            
        # Load account credentials
        try:
            accounts = load_accounts()
        except Exception as e:
            logger.error(f"Error loading accounts: {str(e)}")
            return jsonify({'error': 'Error loading account configuration'}), 500
            
        if accountname not in accounts:
            return jsonify({'error': 'Account not found'}), 404
            
        # Try to refresh the token
        try:
            credentials_data = accounts[accountname]
            
            # Create a Request object for token refresh
            request_obj = google.auth.transport.requests.Request()
            
            # Initialize credentials
            token = credentials_data.get('token')
            if token == 'None':
                token = None
                
            credentials = google.oauth2.credentials.Credentials(
                token=token,
                refresh_token=credentials_data['refresh_token'],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=credentials_data['client_id'],
                client_secret=credentials_data['client_secret']
            )
            
            # Force token refresh
            credentials.refresh(request_obj)
            
            # Save the new token
            if credentials.token:
                # Also save the token expiry time if available
                if hasattr(credentials, 'expiry') and credentials.expiry:
                    expiry_iso = credentials.expiry.isoformat()
                    update_account_token(accountname, credentials.token, expiry_iso)
                else:
                    update_account_token(accountname, credentials.token)
                    
                return jsonify({
                    'success': True,
                    'message': 'Token refreshed successfully',
                    'expires': expiry_iso if hasattr(credentials, 'expiry') and credentials.expiry else 'unknown'
                })
            else:
                return jsonify({
                    'error': 'No token received after refresh'
                }), 500
                
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error refreshing token: {error_message}")
            
            if 'invalid_grant' in error_message.lower():
                return jsonify({
                    'error': 'OAuth refresh token is invalid or revoked',
                    'message': 'You need to re-authenticate the YouTube account.'
                }), 401
            
            return jsonify({'error': f'Error refreshing token: {error_message}'}), 500
            
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Unexpected error in refresh_token: {str(e)}\n{error_trace}")
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8048, debug=True)