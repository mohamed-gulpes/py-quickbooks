from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from quickbooks import QuickBooks
import yaml
import logging
import os
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_credentials(file_path='credentials.yml'):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

def save_credentials(creds, file_path='credentials.yml'):
    with open(file_path, 'w') as f:
        yaml.dump(creds, f)

class QuickBooksClient:
    """Base class for QuickBooks clients"""
    def __init__(
        self,
        credentials_file: str = 'credentials.yml',
        source_company: str = 'source',
        target_company: str = 'target'
    ):
        # Load credentials
        self.credentials_file = credentials_file
        self.source_company = source_company
        self.target_company = target_company
        self.creds = load_credentials(credentials_file)
        
        # Initialize source QuickBooks client
        self.source_auth_client = AuthClient(
            client_id=self.creds['client_id'],
            client_secret=self.creds['client_secret'],
            environment=self.creds[source_company]['environment'],
            redirect_uri=self.creds[source_company]['redirect_uri'],
            access_token=self.creds[source_company]['access_token']
        )
        
        self.source_client = QuickBooks(
            auth_client=self.source_auth_client,
            refresh_token=self.creds[source_company]['refresh_token'],
            company_id=self.creds[source_company]['company_id']
        )

        # Initialize target QuickBooks client
        self.target_auth_client = AuthClient(
            client_id=self.creds['client_id'],
            client_secret=self.creds['client_secret'],
            environment=self.creds[target_company]['environment'],
            redirect_uri=self.creds[target_company]['redirect_uri'],
            access_token=self.creds[target_company]['access_token']
        )
        
        self.target_client = QuickBooks(
            auth_client=self.target_auth_client,
            refresh_token=self.creds[target_company]['refresh_token'],
            company_id=self.creds[target_company]['company_id']
        )

        # Dictionary to store mapping between source and target IDs
        self.id_mapping = {}

    def refresh_tokens(self, company: str) -> None:
        """Refresh OAuth tokens for the specified company"""
        try:
            # Create a new auth client for the refresh
            auth_client = AuthClient(
                client_id=self.creds['client_id'],
                client_secret=self.creds['client_secret'],
                environment=self.creds[company]['environment'],
                redirect_uri=self.creds[company]['redirect_uri']
            )
            
            logger.info(f"Attempting to refresh tokens for {company}")
            logger.info(f"Current refresh token: {self.creds[company]['refresh_token'][:10]}...")
            
            # Refresh the tokens
            refresh_response = auth_client.refresh(refresh_token=self.creds[company]['refresh_token'])
            
            if not refresh_response:
                logger.error(f"Token refresh failed for {company} - no response received")
                logger.error(f"Auth client state - environment: {auth_client.environment}, redirect_uri: {auth_client.redirect_uri}")
                raise Exception("Token refresh failed - null response")
            
            logger.info(f"Refresh response received: {str(refresh_response)[:100]}...")
            
            # Update the credentials in memory
            self.creds[company]['access_token'] = refresh_response['access_token']
            self.creds[company]['refresh_token'] = refresh_response['refresh_token']
            
            # Reinitialize the client with new tokens
            if company == self.source_company:
                self.source_auth_client = auth_client
                self.source_client = QuickBooks(
                    auth_client=auth_client,
                    refresh_token=refresh_response['refresh_token'],
                    company_id=self.creds[company]['company_id']
                )
            else:
                self.target_auth_client = auth_client
                self.target_client = QuickBooks(
                    auth_client=auth_client,
                    refresh_token=refresh_response['refresh_token'],
                    company_id=self.creds[company]['company_id']
                )
            
            # Save updated tokens to credentials file
            save_credentials(self.creds, self.credentials_file)
                
            logger.info(f"Successfully refreshed tokens for {company}")
            logger.info(f"New access token: {refresh_response['access_token'][:10]}...")
            
        except Exception as e:
            logger.error(f"Error refreshing tokens for {company}: {str(e)}")
            logger.error("Please verify your OAuth credentials and ensure refresh tokens are valid")
            raise

    def save_id_mapping(self, filename: str = 'id_mapping.json') -> None:
        """Save the ID mapping to a file"""
        with open(filename, 'w') as f:
            json.dump(self.id_mapping, f)

    def load_id_mapping(self, filename: str = 'id_mapping.json') -> None:
        """Load the ID mapping from a file"""
        try:
            with open(filename, 'r') as f:
                self.id_mapping = json.load(f)
        except FileNotFoundError:
            logger.warning(f"Mapping file {filename} not found") 