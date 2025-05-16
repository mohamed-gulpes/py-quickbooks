from quickbooks.objects.journalentry import JournalEntry, JournalEntryLine
from quickbooks.objects.account import Account
from quickbooks.objects.trackingclass import Class
import logging
from typing import List, Dict
from qb_client import QuickBooksClient
from quickbooks.exceptions import QuickbooksException
from datetime import datetime
from quickbooks.objects.employee import Employee
from quickbooks.objects.vendor import Vendor
logger = logging.getLogger(__name__)

class JournalEntryTransfer(QuickBooksClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_mapping['JournalEntry'] = {}
        self.id_mapping['Account'] = {}
        self.id_mapping['Class'] = {}  # Add class mapping
        self.id_mapping['Employee'] = {}  # Add employee mapping
        self.existing_journals = {}
        self.existing_accounts = {}
        self.existing_classes = {}  # Store existing classes
        self.source_classes = {}  # Cache for source classes
        self.existing_employees = {}  # Store existing employees
        self.existing_vendors = {}  # Store existing vendors

    def _get_journal_identifier(self, journal: JournalEntry) -> str:
        """Get a unique identifier for a journal entry (date + number)"""
        txn_date = getattr(journal, 'TxnDate', '')
        doc_number = getattr(journal, 'DocNumber', '')
        return f"{txn_date}_{doc_number}".strip()

    def _get_existing_accounts(self) -> Dict[str, Account]:
        """Get all existing accounts from target company"""
        try:
            accounts = Account.all(qb=self.target_client)
            # Create a dictionary of accounts by number_name combination
            account_dict = {}
            for acc in accounts:
                number = getattr(acc, 'AcctNum', '').strip()
                name = getattr(acc, 'Name', '').strip()
                key = f"{number}_{name}"
                account_dict[key] = acc
                # Also store by name only as fallback
                account_dict[name] = acc
                # Store the ID mapping
                source_id = getattr(acc, 'Id', None)
                if source_id:
                    self.id_mapping['Account'][source_id] = acc.Id
            logger.info(f"Retrieved {len(accounts)} accounts from target company")
            return account_dict
        except Exception as e:
            logger.error(f"Error getting existing accounts: {str(e)}")
            return {}

    def _get_existing_classes(self) -> Dict[str, Class]:
        """Get all existing classes from target company"""
        try:
            class_dict = {}
            start_position = 1
            max_results = 1000
            more_records = True

            while more_records:
                query = f"SELECT * FROM Class STARTPOSITION {start_position} MAXRESULTS {max_results}"
                classes = Class.query(query, qb=self.target_client)
                
                if not classes:
                    break
                
                for cls in classes:
                    name = getattr(cls, 'Name', '').strip()
                    fully_qualified_name = getattr(cls, 'FullyQualifiedName', '').strip()
                    
                    # Store by both name and fully qualified name
                    class_dict[name] = cls
                    if fully_qualified_name:
                        class_dict[fully_qualified_name] = cls
                        
                        # Also store by each level of the hierarchy
                        parts = fully_qualified_name.split(':')
                        for i in range(len(parts)):
                            partial_name = ':'.join(parts[:i+1])
                            if partial_name not in class_dict:
                                class_dict[partial_name] = cls
                    
                    # Store the ID mapping
                    source_id = getattr(cls, 'Id', None)
                    if source_id:
                        self.id_mapping['Class'][source_id] = cls.Id
                
                # Check if we need to fetch more
                if len(classes) < max_results:
                    more_records = False
                else:
                    start_position += max_results
                
                logger.info(f"Retrieved {len(classes)} classes from position {start_position-max_results}")
            
            logger.info(f"Total classes retrieved from target company: {len(class_dict)}")
            return class_dict
        except Exception as e:
            logger.error(f"Error getting existing classes: {str(e)}")
            return {}

    def _get_source_classes(self) -> Dict[str, dict]:
        """Get all classes from source company and cache them"""
        try:
            class_dict = {}
            start_position = 1
            max_results = 1000
            more_records = True

            while more_records:
                query = f"SELECT * FROM Class STARTPOSITION {start_position} MAXRESULTS {max_results}"
                classes = Class.query(query, qb=self.source_client)
                
                if not classes:
                    break
                
                for cls in classes:
                    class_dict[cls.Id] = {
                        'Name': getattr(cls, 'Name', '').strip(),
                        'FullyQualifiedName': getattr(cls, 'FullyQualifiedName', '').strip(),
                        'Id': cls.Id
                    }
                
                # Check if we need to fetch more
                if len(classes) < max_results:
                    more_records = False
                else:
                    start_position += max_results
                
                logger.info(f"Retrieved {len(classes)} classes from position {start_position-max_results}")
            
            logger.info(f"Total classes retrieved from source company: {len(class_dict)}")
            return class_dict
        except Exception as e:
            logger.error(f"Error getting source classes: {str(e)}")
            return {}

    def _get_existing_employees(self) -> Dict[str, dict]:
        """Get all existing employees from target company"""
        try:
            employee_dict = {}
            employees = Employee.all(qb=self.target_client)
            
            for emp in employees:
                name = f"{getattr(emp, 'GivenName', '').strip()} {getattr(emp, 'FamilyName', '').strip()}".strip()
                if name:
                    employee_dict[name] = emp
                    # Store the ID mapping
                    source_id = getattr(emp, 'Id', None)
                    if source_id:
                        self.id_mapping['Employee'][source_id] = emp.Id
            
            logger.info(f"Retrieved {len(employee_dict)} employees from target company")
            return employee_dict
        except Exception as e:
            logger.error(f"Error getting existing employees: {str(e)}")
            return {}

    def _get_existing_vendors(self) -> Dict[str, dict]:
        """Get all existing vendors from target company"""
        try:
            vendor_dict = {}
            vendors = Vendor.all(qb=self.target_client)
            
            for vendor in vendors:
                name = getattr(vendor, 'DisplayName', '').strip()
                if name:
                    vendor_dict[name] = vendor
                    # Store the ID mapping
                    source_id = getattr(vendor, 'Id', None)
                    if source_id:
                        self.id_mapping['Vendor'][source_id] = vendor.Id
            
            logger.info(f"Retrieved {len(vendor_dict)} vendors from target company")
            return vendor_dict
        except Exception as e:
            logger.error(f"Error getting existing vendors: {str(e)}")
            return {}

    def _map_account_reference(self, account_ref: dict) -> dict:
        """Map account reference from source to target company"""
        if not account_ref:
            return None
            
        # Handle both dictionary and Ref object cases
        account_id = getattr(account_ref, 'value', None) if hasattr(account_ref, 'value') else account_ref.get('value')
        account_name = getattr(account_ref, 'name', '').strip() if hasattr(account_ref, 'name') else account_ref.get('name', '').strip()
        
        logger.info(f"Account ID: {account_id}")
        logger.info(f"Account name: {account_name}")
        # Get the account number from the source account
        source_account = self.source_client.get_single_object('Account', account_id)
        # Extract account details from the nested response
        if isinstance(source_account, dict) and 'Account' in source_account:
            source_account = source_account['Account']
        account_number = getattr(source_account, 'AcctNum', '') if not isinstance(source_account, dict) else source_account.get('AcctNum', '')
        account_number = account_number.strip() if account_number else ''
        # Try to find the account in target company by number and name
        account_key = f"{account_number}_{account_name}"
        logger.info(f"Account key: {account_key}")
        target_account = self.existing_accounts.get(account_key)
        logger.info(f"Target account: {target_account}")
        # Fallback to name-only match if number_name combination not found
        if not target_account:
            target_account = self.existing_accounts.get(account_name)
            if target_account:
                logger.warning(f"Account matched by name only (no matching number): {account_name} (Number: {account_number})")
        
        if target_account:
            return {
                'value': target_account.Id,
                'name': target_account.Name
            }
        else:
            logger.error(f"Account not found in target company: {account_name} (Number: {account_number}, ID: {account_id})")
            return None

    def _map_class_reference(self, class_ref: dict) -> dict:
        """Map class reference from source to target company"""
        if not class_ref:
            return None
            
        # Handle both dictionary and Ref object cases
        class_id = getattr(class_ref, 'value', None) if hasattr(class_ref, 'value') else class_ref.get('value')
        class_name = getattr(class_ref, 'name', '').strip() if hasattr(class_ref, 'name') else class_ref.get('name', '').strip()
        
        logger.debug(f"Attempting to map class: {class_name} (ID: {class_id})")
        
        # Get class details from cache
        source_class = self.source_classes.get(class_id)
        if not source_class:
            logger.error(f"Source class not found in cache: {class_id}")
            return None
        
        # Try different name variations for matching
        names_to_try = []
        
        # First try the last part of the hierarchy (most specific)
        fully_qualified_name = source_class.get('FullyQualifiedName', '').strip()
        if fully_qualified_name:
            parts = fully_qualified_name.split(':')
            if len(parts) > 0:
                last_part = parts[-1].strip()
                names_to_try.append(last_part)
                logger.debug(f"Trying to match by last part: {last_part}")
            
            # Then try the full hierarchy
            names_to_try.append(fully_qualified_name)
            logger.debug(f"Trying to match by full name: {fully_qualified_name}")
            
            # Then try each level of the hierarchy from most specific to least
            for i in range(len(parts)-1, -1, -1):
                partial_name = ':'.join(parts[max(0, i-1):i+1])
                if partial_name and partial_name not in names_to_try:
                    names_to_try.append(partial_name)
                    logger.debug(f"Trying to match by partial name: {partial_name}")
        
        # Add the simple name as last resort
        simple_name = source_class.get('Name', '').strip()
        if simple_name and simple_name not in names_to_try:
            names_to_try.append(simple_name)
            logger.debug(f"Trying to match by simple name: {simple_name}")
        
        # Try each name variation
        for name in names_to_try:
            if name in self.existing_classes:
                target_class = self.existing_classes[name]
                logger.info(f"Successfully mapped class '{class_name}' to target class '{target_class.Name}' using variation '{name}'")
                return {
                    'value': target_class.Id,
                    'name': target_class.Name
                }
            else:
                logger.debug(f"No match found for variation: {name}")
        
        # If we get here, no match was found
        logger.error(f"Failed to map class: {class_name} (ID: {class_id})")
        logger.error(f"Tried the following variations: {', '.join(names_to_try)}")
        return None

    def _map_employee_reference(self, employee_ref: dict) -> dict:
        """Map employee reference from source to target company"""
        if not employee_ref:
            return None
            
        # Handle Ref object case
        if hasattr(employee_ref, 'value'):
            employee_id = employee_ref.value
            employee_name = getattr(employee_ref, 'name', '').strip()
        # Handle dictionary case
        else:
            employee_id = employee_ref.get('value')
            employee_name = employee_ref.get('name', '').strip()
        
        logger.info(f"Attempting to map employee reference: {employee_ref.__dict__ if hasattr(employee_ref, '__dict__') else employee_ref}")
        logger.info(f"Employee ID: {employee_id}, Name: {employee_name}")
        
        # Get employee details from source company
        try:
            source_employee = Employee.get(employee_id, qb=self.source_client)
            if not source_employee:
                logger.error(f"Source employee not found: {employee_id}")
                return None
            
            logger.info(f"Source employee details: {source_employee.__dict__ if hasattr(source_employee, '__dict__') else source_employee}")
            
            # Get the full name using the same method as in EmployeeTransfer
            given_name = getattr(source_employee, 'GivenName', '').strip()
            family_name = getattr(source_employee, 'FamilyName', '').strip()
            display_name = getattr(source_employee, 'DisplayName', '').strip()
            
            logger.info(f"Source employee names - Given: {given_name}, Family: {family_name}, Display: {display_name}")
            
            # Try different name combinations
            names_to_try = []
            
            # First try the full name
            full_name = f"{given_name} {family_name}".strip()
            if full_name:
                names_to_try.append(full_name)
            
            # Then try display name
            if display_name:
                names_to_try.append(display_name)
            
            # Then try the original name from the reference
            if employee_name:
                names_to_try.append(employee_name)
            
            logger.info(f"Trying employee names: {names_to_try}")
            
            # Try each name variation
            for name in names_to_try:
                target_employee = self.existing_employees.get(name)
                if target_employee:
                    logger.info(f"Found matching employee in target company: {name}")
                    return {
                        'value': target_employee.Id,
                        'name': name
                    }
            
            logger.error(f"Employee not found in target company. Tried names: {', '.join(names_to_try)}")
            return None
                
        except Exception as e:
            logger.error(f"Error mapping employee {employee_name} (ID: {employee_id}): {str(e)}")
            return None

    def _map_entity_reference(self, entity_ref: dict) -> dict:
        """Map entity reference (Employee or Vendor) from source to target company"""
        if not entity_ref:
            return None
            
        # Get the entity type and reference
        entity_type = getattr(entity_ref, 'Type', None)
        if not entity_type:
            logger.warning("Entity reference found but no Type specified")
            return None

        # Get the nested EntityRef
        ref = getattr(entity_ref, 'EntityRef', None)
        if not ref:
            logger.warning(f"Entity of type {entity_type} has no EntityRef")
            return None

        logger.info(f"Mapping entity of type {entity_type}")
        logger.info(f"Entity reference: {ref.__dict__ if hasattr(ref, '__dict__') else ref}")

        if entity_type == 'Employee':
            new_ref = self._map_employee_reference(ref)
        elif entity_type == 'Vendor':
            new_ref = self._map_vendor_reference(ref)
        else:
            logger.warning(f"Unsupported entity type: {entity_type}")
            return None

        if new_ref:
            return {
                'Type': entity_type,
                'EntityRef': new_ref
            }
        return None

    def _map_vendor_reference(self, vendor_ref: dict) -> dict:
        """Map vendor reference from source to target company"""
        if not vendor_ref:
            return None
            
        # Handle Ref object case
        if hasattr(vendor_ref, 'value'):
            vendor_id = vendor_ref.value
            vendor_name = getattr(vendor_ref, 'name', '').strip()
        # Handle dictionary case
        else:
            vendor_id = vendor_ref.get('value')
            vendor_name = vendor_ref.get('name', '').strip()
        
        logger.info(f"Attempting to map vendor reference: {vendor_ref.__dict__ if hasattr(vendor_ref, '__dict__') else vendor_ref}")
        logger.info(f"Vendor ID: {vendor_id}, Name: {vendor_name}")
        
        # Get vendor details from source company
        try:
            source_vendor = Vendor.get(vendor_id, qb=self.source_client)
            if not source_vendor:
                logger.error(f"Source vendor not found: {vendor_id}")
                return None
            
            # Get the display name using the same method as in VendorTransfer
            display_name = getattr(source_vendor, 'DisplayName', '').strip()
            
            # Try to find the vendor in target company
            target_vendor = self.existing_vendors.get(display_name)
            if target_vendor:
                logger.info(f"Found matching vendor in target company: {display_name}")
                return {
                    'value': target_vendor.Id,
                    'name': display_name
                }
            
            logger.error(f"Vendor not found in target company: {display_name}")
            return None
                
        except Exception as e:
            logger.error(f"Error mapping vendor {vendor_name} (ID: {vendor_id}): {str(e)}")
            return None

    def _get_existing_journals(self) -> Dict[str, JournalEntry]:
        """Get all existing journal entries from target company"""
        try:
            journals = JournalEntry.all(qb=self.target_client, max_results=1000)
            # Create a dictionary of journals by identifier
            return {self._get_journal_identifier(je): je for je in journals}
        except Exception as e:
            logger.error(f"Error getting existing journal entries: {str(e)}")
            return {}

    def _journal_exists(self, journal_id: str) -> bool:
        """Check if a journal entry with this identifier already exists"""
        return journal_id in self.existing_journals

    def _copy_journal_line_attributes(self, source_line: JournalEntryLine, new_line: JournalEntryLine) -> None:
        """Copy attributes from source journal line to new journal line"""
        # Copy basic attributes
        basic_attributes = [
            'Description',
            'Amount',
            'TaxAmount',
            'BillableStatus'
        ]
        
        for attr in basic_attributes:
            value = getattr(source_line, attr, None)
            if value is not None:
                setattr(new_line, attr, value)
                logger.debug(f"Copied line attribute {attr}: {value}")

        # Handle references that need mapping
        source_detail = getattr(source_line, 'JournalEntryLineDetail', None)
        if source_detail:
            logger.info(f"Processing line detail: {source_detail.__dict__ if hasattr(source_detail, '__dict__') else source_detail}")
            new_detail = {}
            
            # Copy PostingType (required field)
            posting_type = getattr(source_detail, 'PostingType', None)
            if posting_type:
                new_detail['PostingType'] = posting_type
            else:
                # Default to Debit if amount is positive, Credit if negative
                amount = float(getattr(source_line, 'Amount', 0))
                new_detail['PostingType'] = 'Debit' if amount >= 0 else 'Credit'
            
            # Map AccountRef
            account_ref = getattr(source_detail, 'AccountRef', None)
            if account_ref:
                new_account_ref = self._map_account_reference(account_ref)
                if new_account_ref:
                    new_detail['AccountRef'] = new_account_ref
                else:
                    logger.error(f"Failed to map account reference: {account_ref}")
                    return False

            # Map ClassRef
            class_ref = getattr(source_detail, 'ClassRef', None)
            if class_ref:
                new_class_ref = self._map_class_reference(class_ref)
                if new_class_ref:
                    new_detail['ClassRef'] = new_class_ref
                else:
                    logger.warning(f"Failed to map class reference: {class_ref} - continuing without class")

            # Handle Entity reference (can be Employee or Vendor)
            entity = getattr(source_detail, 'Entity', None)
            if entity:
                logger.info(f"Found entity reference: {entity.__dict__ if hasattr(entity, '__dict__') else entity}")
                new_entity = self._map_entity_reference(entity)
                if new_entity:
                    new_detail['Entity'] = new_entity
                    logger.info(f"Successfully mapped entity reference: {new_entity}")
                else:
                    logger.warning(f"Failed to map entity reference: {entity} - continuing without entity")

            # Copy other references as is
            for ref in ['TaxCodeRef', 'DepartmentRef']:
                ref_value = getattr(source_detail, ref, None)
                if ref_value:
                    new_detail[ref] = ref_value

            new_line.JournalEntryLineDetail = new_detail

        return True

    def _copy_journal_attributes(self, source_journal: JournalEntry, new_journal: JournalEntry) -> None:
        """Copy all available attributes from source journal to new journal"""
        # Core attributes that must be set
        new_journal.TxnDate = getattr(source_journal, 'TxnDate', datetime.now().strftime('%Y-%m-%d'))
        
        # All possible JournalEntry attributes
        attributes = [
            'DocNumber',
            'PrivateNote',
            'TxnTaxDetail',
            'ExchangeRate',
            'CurrencyRef',
            'DepartmentRef',
            'PrivateNote',
            'TxnStatus',
            'MetaData'
        ]
        
        # Copy all available attributes
        for attr in attributes:
            value = getattr(source_journal, attr, None)
            if value is not None:
                setattr(new_journal, attr, value)
                logger.debug(f"Copied attribute {attr}: {value}")

        # Handle Line items separately
        if hasattr(source_journal, 'Line') and source_journal.Line:
            new_journal.Line = []
            for line in source_journal.Line:
                new_line = JournalEntryLine()
                self._copy_journal_line_attributes(line, new_line)
                new_journal.Line.append(new_line)

    def _create_or_update_journal(self, journal: JournalEntry) -> bool:
        """Create a new journal entry or update existing one"""
        try:
            journal_id = self._get_journal_identifier(journal)
            
            # Check if journal already exists
            existing_journal = None
            if self._journal_exists(journal_id):
                existing_journal = self.existing_journals[journal_id]
                logger.info(f"Journal entry '{journal_id}' already exists with ID {existing_journal.Id}")
                new_journal = existing_journal
            else:
                new_journal = JournalEntry()

            # Copy attributes to new or existing journal
            self._copy_journal_attributes(journal, new_journal)
            
            # Log the journal data being sent
            logger.info(f"{'Updating' if existing_journal else 'Creating'} journal entry:")
            logger.info(f"  Identifier: {journal_id}")
            logger.info(f"  Date: {getattr(new_journal, 'TxnDate', 'N/A')}")
            logger.info(f"  Number: {getattr(new_journal, 'DocNumber', 'N/A')}")
            if hasattr(new_journal, 'Line'):
                logger.info(f"  Number of lines: {len(new_journal.Line)}")
            
            # Try to save the journal entry
            if existing_journal:
                created_journal = new_journal.save(qb=self.target_client)
                logger.info(f"Successfully updated journal entry {journal_id}")
            else:
                created_journal = new_journal.save(qb=self.target_client)
                logger.info(f"Successfully created journal entry {journal_id}")
            
            # If successful, store the mapping
            if created_journal and created_journal.Id:
                self.id_mapping['JournalEntry'][journal.Id] = created_journal.Id
                # Add or update in existing journals
                self.existing_journals[journal_id] = created_journal
                logger.info(f"Journal entry {journal_id} saved with ID {created_journal.Id}")
                return True
                    
        except QuickbooksException as qb_error:
            logger.error(f"QuickBooks API Error for journal entry {journal_id}:")
            logger.error(f"  Message: {qb_error.message}")
            logger.error(f"  Error Code: {getattr(qb_error, 'error_code', 'Unknown')}")
            logger.error(f"  Detail: {getattr(qb_error, 'detail', '')}")
            if hasattr(qb_error, 'intuit_tid'):
                logger.error(f"  Intuit TID: {qb_error.intuit_tid}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error {'updating' if existing_journal else 'creating'} journal entry {journal_id}: {str(e)}")
            return False

    def transfer_journals(self) -> None:
        """Transfer journal entries from source to target company"""
        logger.info("Starting journal entry transfer...")
        try:
            # First, get all existing accounts for mapping
            logger.info("Getting existing accounts from target company...")
            self.existing_accounts = self._get_existing_accounts()
            logger.info(f"Found {len(self.existing_accounts)} existing accounts")

            # Get all source classes and cache them
            logger.info("Getting classes from source company...")
            self.source_classes = self._get_source_classes()
            logger.info(f"Cached {len(self.source_classes)} source classes")

            # Get existing classes from target
            logger.info("Getting existing classes from target company...")
            self.existing_classes = self._get_existing_classes()
            logger.info(f"Found {len(self.existing_classes)} existing classes")

            # Get existing employees
            logger.info("Getting existing employees from target company...")
            self.existing_employees = self._get_existing_employees()
            logger.info(f"Found {len(self.existing_employees)} existing employees")

            # Get existing vendors
            logger.info("Getting existing vendors from target company...")
            self.existing_vendors = self._get_existing_vendors()
            logger.info(f"Found {len(self.existing_vendors)} existing vendors")

            # Then get existing journals
            logger.info("Getting existing journal entries from target company...")
            self.existing_journals = self._get_existing_journals()
            logger.info(f"Found {len(self.existing_journals)} existing journal entries")
            
            # Get all journals from source
            all_journals = JournalEntry.all(qb=self.source_client, max_results=1000)
            logger.info(f"Retrieved {len(all_journals)} total journal entries from source")
            
            # Print source journals with detailed information
            print(f"\n=== Source Journal Entries Details ({len(all_journals)} entries) ===")
            
            # Try to create/update journals one by one
            logger.info("Attempting to process journal entries individually...")
            success_count = 0
            update_count = 0
            create_count = 0
            for journal in all_journals:
                journal_id = self._get_journal_identifier(journal)
                exists = self._journal_exists(journal_id)
                
                if self._create_or_update_journal(journal):
                    success_count += 1
                    if exists:
                        update_count += 1
                    else:
                        create_count += 1
            
            # Print final summary
            logger.info("\n=== Transfer Summary ===")
            logger.info(f"Total journal entries processed: {len(all_journals)}")
            logger.info(f"Journal entries updated: {update_count}")
            logger.info(f"New journal entries created: {create_count}")
            logger.info(f"Total successful operations: {success_count}")
            
        except Exception as e:
            logger.error(f"Error transferring journal entries: {str(e)}")
            if hasattr(e, 'message'):
                logger.error(f"Error message: {e.message}")
            if hasattr(e, 'detail'):
                logger.error(f"Error detail: {e.detail}")
            raise 