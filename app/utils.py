import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

def validate_accounts_file():
    """Validate the accounts.json file and its contents."""
    config_path = Path('/app/config/accounts.json')
    
    if not config_path.exists():
        logger.error("accounts.json file not found in /app/config/")
        return False
        
    try:
        with open(config_path) as f:
            accounts = json.load(f)
            
        required_fields = ['client_id', 'client_secret', 'refresh_token', 'token']
        
        for account, details in accounts.items():
            missing_fields = [field for field in required_fields if field not in details]
            if missing_fields:
                logger.error(f"Account {account} is missing required fields: {missing_fields}")
                return False
                
        logger.info(f"Found {len(accounts)} valid account(s): {', '.join(accounts.keys())}")
        return True
        
    except json.JSONDecodeError:
        logger.error("accounts.json is not valid JSON")
        return False
    except Exception as e:
        logger.error(f"Error validating accounts file: {str(e)}")
        return False


def update_account_token(account_name, token, expiry=None):
    """Update the token for a specific account in accounts.json"""
    config_path = Path('/app/config/accounts.json')
    
    if not config_path.exists():
        logger.error("accounts.json file not found in /app/config/")
        return False
    
    try:
        with open(config_path, 'r') as f:
            accounts = json.load(f)
        
        if account_name not in accounts:
            logger.error(f"Account {account_name} not found in accounts.json")
            return False
        
        # Update the token
        accounts[account_name]['token'] = token
        
        # Update token_expiry if provided
        if expiry:
            accounts[account_name]['token_expiry'] = expiry
        
        # Write back to file
        # First create a backup
        backup_path = config_path.with_suffix('.json.bak')
        if config_path.exists():
            os.replace(config_path, backup_path)
        
        with open(config_path, 'w') as f:
            json.dump(accounts, f, indent=2)
        
        logger.info(f"Updated token for account {account_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating account token: {str(e)}")
        return False