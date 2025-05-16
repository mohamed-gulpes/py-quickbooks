from quickbooks.objects.account import Account
from quickbooks.batch import batch_create
import logging
from typing import List, Dict
from qb_client import QuickBooksClient
import json
from quickbooks.exceptions import QuickbooksException
import time

logger = logging.getLogger(__name__)

class AccountTransfer(QuickBooksClient):
    """Transfer chart of accounts from source to target company"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_mapping['Account'] = {}
        self.existing_accounts = {}  # Store existing accounts by name

    def _is_default_account(self, account: Account) -> bool:
        """Check if an account is a default QuickBooks account"""
        # Default accounts typically have system-assigned IDs and specific patterns
        default_patterns = [
            "Accounts Payable",
            "Accounts Receivable",
            "Opening Balance Equity",
            "Retained Earnings",
            "Sales of Product Income",
            "Undeposited Funds",
            "Inventory Asset"
        ]
        return any(pattern in account.Name for pattern in default_patterns)

    def _is_active_account(self, account: Account) -> bool:
        """Check if an account is active"""
        return getattr(account, 'Active', False)

    def _get_existing_accounts(self) -> Dict[str, Account]:
        """Get all existing accounts from target company"""
        try:
            accounts = Account.all(qb=self.target_client)
            # Create a dictionary of accounts by name
            return {account.Name: account for account in accounts}
        except Exception as e:
            logger.error(f"Error getting existing accounts: {str(e)}")
            return {}

    def _account_exists(self, account_name: str) -> bool:
        """Check if an account with this name already exists"""
        return account_name in self.existing_accounts

    def _has_positive_balance(self, account: Account) -> bool:
        """Check if account has a positive balance"""
        balance = getattr(account, 'CurrentBalance', 0) or 0
        balance_with_subs = getattr(account, 'CurrentBalanceWithSubAccounts', 0) or 0
        return balance > 0 or balance_with_subs > 0

    def _copy_account_attributes(self, source_account: Account, new_account: Account) -> None:
        """Copy all available attributes from source account to new account"""
        # Core attributes that must be set
        new_account.Name = source_account.Name
        new_account.AccountType = source_account.AccountType
        
        # All possible Account attributes
        attributes = [
            'AcctNum',
            'AccountSubType',
            'Description',
            'Active',
            'Classification',
            'SubAccount',
            'CurrencyRef',
            'ExchangeRate',
            'TaxCodeRef',
            'AccountAlias',
            'FullyQualifiedName',
            'MetaData',
            'domain',
            'sparse',
            'Status',
            'TxnLocationType',
        ]
        
        # Copy all available attributes
        for attr in attributes:
            value = getattr(source_account, attr, None)
            if value is not None:
                setattr(new_account, attr, value)
                logger.debug(f"Copied attribute {attr}: {value}")
        
        # Handle special references
        if getattr(source_account, 'ParentRef', None):
            if source_account.ParentRef.value in self.id_mapping['Account']:
                new_account.ParentRef = {
                    'value': self.id_mapping['Account'][source_account.ParentRef.value],
                    'name': getattr(source_account.ParentRef, 'name', None)
                }
            else:
                logger.warning(f"Parent account {source_account.ParentRef.value} not found in mapping")

        # Handle Currency Reference
        if getattr(source_account, 'CurrencyRef', None):
            new_account.CurrencyRef = {
                'value': getattr(source_account.CurrencyRef, 'value', None),
                'name': getattr(source_account.CurrencyRef, 'name', None)
            }

        # Handle Tax Code Reference
        if getattr(source_account, 'TaxCodeRef', None):
            new_account.TaxCodeRef = {
                'value': getattr(source_account.TaxCodeRef, 'value', None),
                'name': getattr(source_account.TaxCodeRef, 'name', None)
            }

    def _verify_account_exists(self, account_id: str, account_name: str) -> bool:
        """Verify that an account exists in the target company"""
        try:
            # Query for the account by ID
            query = f"select * from Account where Id = '{account_id}'"
            accounts = Account.query(query, qb=self.target_client)
            
            if not accounts:
                logger.error(f"Account {account_name} (ID: {account_id}) not found in target company")
                return False
                
            account = accounts[0]
            logger.info(f"Verified account exists in target company:")
            logger.info(f"  Name: {account.Name}")
            logger.info(f"  ID: {account.Id}")
            logger.info(f"  Type: {account.AccountType}")
            logger.info(f"  AcctNum: {getattr(account, 'AcctNum', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"Error verifying account {account_name}: {str(e)}")
            return False

    def _create_single_account(self, account: Account) -> bool:
        """Try to create a single account and return success status"""
        try:
            # Check if account already exists
            if self._account_exists(account.Name):
                existing_account = self.existing_accounts[account.Name]
                logger.info(f"Account '{account.Name}' already exists with ID {existing_account.Id}")
                # Store the mapping for existing account
                self.id_mapping['Account'][account.Id] = existing_account.Id
                return True

            # Create new account object for target
            new_account = Account()
            self._copy_account_attributes(account, new_account)
            
            # Log the account data being sent
            logger.info(f"Attempting to create account:")
            logger.info(f"  Name: {new_account.Name}")
            logger.info(f"  Type: {new_account.AccountType}")
            logger.info(f"  SubType: {getattr(new_account, 'AccountSubType', 'N/A')}")
            logger.info(f"  AcctNum: {getattr(new_account, 'AcctNum', 'N/A')}")
            logger.info(f"  Classification: {getattr(new_account, 'Classification', 'N/A')}")
            if hasattr(new_account, 'CurrencyRef'):
                logger.info(f"  Currency: {json.dumps(new_account.CurrencyRef, indent=2)}")
            
            # Try to save the account
            created_account = new_account.save(qb=self.target_client)
            
            # If successful, store the mapping and verify
            if created_account and created_account.Id:
                self.id_mapping['Account'][account.Id] = created_account.Id
                # Add to existing accounts
                self.existing_accounts[new_account.Name] = created_account
                logger.info(f"Successfully created account {new_account.Name} with ID {created_account.Id}")
                return True
                    
        except QuickbooksException as qb_error:
            logger.error(f"QuickBooks API Error for account {account.Name}:")
            logger.error(f"  Message: {qb_error.message}")
            logger.error(f"  Error Code: {getattr(qb_error, 'error_code', 'Unknown')}")
            logger.error(f"  Detail: {getattr(qb_error, 'detail', '')}")
            if hasattr(qb_error, 'intuit_tid'):
                logger.error(f"  Intuit TID: {qb_error.intuit_tid}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error creating account {account.Name}: {str(e)}")
            return False

    def transfer_accounts(self) -> None:
        """Transfer chart of accounts from source to target company"""
        logger.info("Starting chart of accounts transfer...")
        try:
            # First, get all existing accounts
            logger.info("Getting existing accounts from target company...")
            self.existing_accounts = self._get_existing_accounts()
            logger.info(f"Found {len(self.existing_accounts)} existing accounts")
            
            # Get all accounts from source
            all_accounts = Account.all(qb=self.source_client)
            
            # Filter accounts based on criteria
            accounts = [
                account for account in all_accounts 
                if not self._is_default_account(account) and self._is_active_account(account)
            ]
            
            total_accounts = len(accounts)
            logger.info(f"Found {total_accounts} active non-default accounts")
            logger.info(f"Filtered out {len(all_accounts) - total_accounts} accounts (inactive or default)")
            
            # Print source accounts
            print(f"\n=== Source Accounts Details ({total_accounts} accounts) ===")
            for index, account in enumerate(accounts, 1):
                balance = getattr(account, 'CurrentBalance', 0) or 0
                balance_with_subs = getattr(account, 'CurrentBalanceWithSubAccounts', 0) or 0
                
                print(f"\nAccount #{index} of {total_accounts}")
                print(f"Account Number: {getattr(account, 'AcctNum', 'N/A')}")
                print(f"ID: {account.Id}")
                print(f"Name: {account.Name}")
                print(f"Type: {account.AccountType}")
                print(f"SubType: {getattr(account, 'AccountSubType', 'N/A')}")
                print(f"Classification: {getattr(account, 'Classification', 'N/A')}")
                print(f"Description: {getattr(account, 'Description', 'N/A')}")
                print(f"Fully Qualified Name: {getattr(account, 'FullyQualifiedName', 'N/A')}")
                print(f"Active: {getattr(account, 'Active', 'N/A')}")
                print(f"Sub Account: {getattr(account, 'SubAccount', False)}")
                
                currency_ref = getattr(account, 'CurrencyRef', None)
                if currency_ref:
                    print(f"Currency: {getattr(currency_ref, 'name', 'N/A')} ({getattr(currency_ref, 'value', 'N/A')})")
                    print(f"Exchange Rate: {getattr(account, 'ExchangeRate', 'N/A')}")
                
                parent_ref = getattr(account, 'ParentRef', None)
                if parent_ref and hasattr(parent_ref, 'value'):
                    print(f"Parent Account ID: {parent_ref.value}")
                    print(f"Parent Account Name: {getattr(parent_ref, 'name', 'N/A')}")
                else:
                    print("Parent Account: None")
                
                print(f"Current Balance: {balance:,.2f}")
                print(f"Current Balance With Subs: {balance_with_subs:,.2f}")
                print("-" * 50)
            
            # Try to create accounts one by one
            logger.info("Attempting to create accounts individually...")
            success_count = 0
            skipped_count = 0
            for account in accounts:
                if self._account_exists(account.Name):
                    logger.info(f"Skipping existing account: {account.Name}")
                    skipped_count += 1
                    success_count += 1  # Count as success since we mapped the ID
                elif self._create_single_account(account):
                    success_count += 1
            
            # Print final verification of target accounts
            logger.info("\n=== Transfer Summary ===")
            logger.info(f"Total accounts processed: {total_accounts}")
            logger.info(f"Accounts skipped (already exist): {skipped_count}")
            logger.info(f"New accounts created: {success_count - skipped_count}")
            logger.info(f"Total successful operations: {success_count}")
            
        except Exception as e:
            logger.error(f"Error transferring accounts: {str(e)}")
            if hasattr(e, 'message'):
                logger.error(f"Error message: {e.message}")
            if hasattr(e, 'detail'):
                logger.error(f"Error detail: {e.detail}")
            raise

    def _sort_accounts_by_hierarchy(self, accounts: List[Account]) -> List[Account]:
        """Sort accounts so that parent accounts are created before their children"""
        # Create a dictionary of accounts by ID
        account_dict = {account.Id: account for account in accounts}
        
        # Helper function to get account depth
        def get_account_depth(account):
            depth = 0
            current = account
            while getattr(current, 'ParentRef', None):
                parent_id = current.ParentRef.value
                if parent_id in account_dict:
                    current = account_dict[parent_id]
                    depth += 1
                else:
                    break
            return depth
        
        # Sort accounts by depth (parents first)
        return sorted(accounts, key=get_account_depth)

    def _create_batches(self, items: List, batch_size: int = 30) -> List[List]:
        """Split items into batches of specified size"""
        return [items[i:i + batch_size] for i in range(0, len(items), batch_size)] 