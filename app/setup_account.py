import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
import argparse

def setup_account(client_secrets_file, account_name):
    """Set up YouTube account authentication and save credentials."""
    
    # OAuth 2.0 scopes for uploading videos
    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    
    # Load existing accounts if any
    accounts = {}
    if os.path.exists('/app/config/accounts.json'):
        with open('/app/config/accounts.json', 'r') as f:
            accounts = json.load(f)
    
    # Create the OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    
    # Run the OAuth flow
    credentials = flow.run_local_server(port=8090)
    
    # Save the credentials
    accounts[account_name] = {
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'refresh_token': credentials.refresh_token,
        'token': credentials.token,
        'token_uri': credentials.token_uri,
        'scopes': credentials.scopes
    }
    
    # Save to config file
    os.makedirs('/app/config', exist_ok=True)
    with open('/app/config/accounts.json', 'w') as f:
        json.dump(accounts, f, indent=2)
    
    print(f"Successfully set up account: {account_name}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Set up YouTube account authentication')
    parser.add_argument('--secrets', required=True, help='Path to client_secrets.json file')
    parser.add_argument('--account', required=True, help='Account name for this setup')
    
    args = parser.parse_args()
    setup_account(args.secrets, args.account)