import json
import logging
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