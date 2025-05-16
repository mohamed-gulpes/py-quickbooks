from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from quickbooks import QuickBooks
from quickbooks.objects.customer import Customer
from quickbooks.objects.invoice import Invoice
from quickbooks.objects.item import Item
from quickbooks.objects.account import Account
from quickbooks.batch import batch_create
from typing import List, Dict
import logging
import json
import yaml
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_credentials(file_path='credentials.yml'):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

class QBDataTransfer:
    def __init__(
        self,
        credentials_file: str = 'credentials.yml',
        source_company: str = 'mali-unicef',
        target_company: str = 'mali'
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
        self.id_mapping = {
            'Customer': {},
            'Item': {},
            'Account': {}
        }

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
            
            # Get the authorization URL
            scopes = [
                Scopes.ACCOUNTING,
                Scopes.OPENID,
                Scopes.EMAIL,
                Scopes.PROFILE,
            ]
            
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
            with open(self.credentials_file, 'w') as f:
                yaml.dump(self.creds, f)
                
            logger.info(f"Successfully refreshed tokens for {company}")
            logger.info(f"New access token: {refresh_response['access_token'][:10]}...")
            
        except Exception as e:
            logger.error(f"Error refreshing tokens for {company}: {str(e)}")
            logger.error("Please verify your OAuth credentials and ensure refresh tokens are valid")
            raise

    def transfer_customers(self) -> None:
        """Transfer all customers from source to target company"""
        logger.info("Starting customer transfer...")
        try:
            # Get all customers from source
            customers = Customer.all(qb=self.source_client)
            print("Customers:", customers)
            
            new_customers = []

            for customer in customers:
                # Create new customer object for target
                new_customer = Customer()
                new_customer.DisplayName = customer.DisplayName
                new_customer.CompanyName = getattr(customer, 'CompanyName', '')
                new_customer.GivenName = getattr(customer, 'GivenName', '')
                new_customer.FamilyName = getattr(customer, 'FamilyName', '')
                new_customer.Active = True

                print("New customer:", new_customer)

            #     if hasattr(customer, 'BillAddr'):
            #         new_customer.BillAddr = customer.BillAddr

            #     if hasattr(customer, 'PrimaryEmailAddr'):
            #         new_customer.PrimaryEmailAddr = customer.PrimaryEmailAddr

            #     if hasattr(customer, 'PrimaryPhone'):
            #         new_customer.PrimaryPhone = customer.PrimaryPhone

            #     new_customers.append(new_customer)

            # # Batch create customers in target company
            # results = batch_create(new_customers, qb=self.target_client)
            
            # # Store ID mapping
            # for i, result in enumerate(results.successes):
            #     self.id_mapping['Customer'][customers[i].Id] = result.Id
                
            # logger.info(f"Successfully transferred {len(results.successes)} customers")
            # if results.faults:
            #     logger.warning(f"Failed to transfer {len(results.faults)} customers")
        except Exception as e:
            logger.error(f"Error fetching customers: {str(e)}")
            raise

    def transfer_items(self) -> None:
        """Transfer all items from source to target company"""
        logger.info("Starting item transfer...")
        
        # Get all items from source
        items = Item.all(qb=self.source_client)
        new_items = []

        for item in items:
            # Create new item object for target
            new_item = Item()
            new_item.Name = item.Name
            new_item.Description = getattr(item, 'Description', '')
            new_item.Active = True
            new_item.Type = item.Type
            new_item.UnitPrice = item.UnitPrice

            if hasattr(item, 'IncomeAccountRef'):
                # You'll need to map the account IDs between companies
                new_item.IncomeAccountRef = item.IncomeAccountRef

            new_items.append(new_item)

        # Batch create items in target company
        results = batch_create(new_items, qb=self.target_client)
        
        # Store ID mapping
        for i, result in enumerate(results.successes):
            self.id_mapping['Item'][items[i].Id] = result.Id
            
        logger.info(f"Successfully transferred {len(results.successes)} items")
        if results.faults:
            logger.warning(f"Failed to transfer {len(results.faults)} items")

    def transfer_invoices(self) -> None:
        """Transfer all invoices from source to target company"""
        logger.info("Starting invoice transfer...")
        
        # Get all invoices from source
        invoices = Invoice.all(qb=self.source_client)
        new_invoices = []

        for invoice in invoices:
            # Create new invoice object for target
            new_invoice = Invoice()
            
            # Map the customer ID from source to target
            if invoice.CustomerRef.value in self.id_mapping['Customer']:
                new_invoice.CustomerRef = {
                    'value': self.id_mapping['Customer'][invoice.CustomerRef.value]
                }
            else:
                logger.warning(f"Customer mapping not found for invoice {invoice.Id}")
                continue

            new_invoice.DueDate = invoice.DueDate
            new_invoice.TxnDate = invoice.TxnDate
            
            # Transfer line items
            new_invoice.Line = []
            for line in invoice.Line:
                new_line = {
                    'Description': line.Description,
                    'Amount': line.Amount,
                    'DetailType': line.DetailType
                }
                
                if hasattr(line, 'SalesItemLineDetail'):
                    if line.SalesItemLineDetail.ItemRef.value in self.id_mapping['Item']:
                        new_line['SalesItemLineDetail'] = {
                            'ItemRef': {
                                'value': self.id_mapping['Item'][line.SalesItemLineDetail.ItemRef.value]
                            }
                        }
                
                new_invoice.Line.append(new_line)

            new_invoices.append(new_invoice)

        # Batch create invoices in target company
        results = batch_create(new_invoices, qb=self.target_client)
        
        logger.info(f"Successfully transferred {len(results.successes)} invoices")
        if results.faults:
            logger.warning(f"Failed to transfer {len(results.faults)} invoices")

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

    def transfer_all(self) -> None:
        """Transfer all data from source to target company"""
        logger.info("Starting full data transfer...")
        
        # Transfer in the correct order to maintain relationships
        self.transfer_customers()
        # self.transfer_items()
        # self.transfer_invoices()
        
        # # Save the ID mapping for future reference
        # self.save_id_mapping()
        
        logger.info("Data transfer completed")

def main():
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    credentials_path = os.path.join(script_dir, 'credentials.yml')
    
    # Create transfer instance with credentials from yml
    transfer = QBDataTransfer(
        credentials_file=credentials_path,
        source_company='mali-unicef',  # Source company
        target_company='mali'          # Target company
    )
    
    transfer.transfer_all()

if __name__ == "__main__":
    main() 