from quickbooks.objects.customer import Customer
import logging
from typing import List, Dict
from qb_client import QuickBooksClient
from quickbooks.exceptions import QuickbooksException

logger = logging.getLogger(__name__)

class CustomerTransfer(QuickBooksClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_mapping['Customer'] = {}
        self.existing_customers = {}  # Store existing customers by name

    def _get_customer_display_name(self, customer: Customer) -> str:
        """Get the display name of a customer in a consistent format"""
        return getattr(customer, 'DisplayName', '').strip()

    def _is_active_customer(self, customer: Customer) -> bool:
        """Check if a customer is active"""
        active_status = getattr(customer, 'Active', True)  # Default to True if not specified
        logger.debug(f"Customer {getattr(customer, 'DisplayName', 'Unknown')}: Active status = {active_status}")
        return active_status

    def _get_existing_customers(self) -> Dict[str, Customer]:
        """Get all existing customers from target company"""
        try:
            customers = Customer.all(qb=self.target_client)
            # Create a dictionary of customers by display name
            return {self._get_customer_display_name(cust): cust for cust in customers}
        except Exception as e:
            logger.error(f"Error getting existing customers: {str(e)}")
            return {}

    def _customer_exists(self, customer_name: str) -> bool:
        """Check if a customer with this name already exists"""
        return customer_name in self.existing_customers

    def _copy_customer_attributes(self, source_customer: Customer, new_customer: Customer) -> None:
        """Copy all available attributes from source customer to new customer"""
        # All possible Customer attributes
        attributes = [
            'DisplayName',
            'Title',
            'GivenName',
            'MiddleName',
            'FamilyName',
            'Suffix',
            'CompanyName',
            'Active',
            'PrimaryPhone',
            'AlternatePhone',
            'Mobile',
            'Fax',
            'PrimaryEmailAddr',
            'WebAddr',
            'BillAddr',
            'ShipAddr',
            'Notes',
            'Balance',
            'OpenBalanceDate',
            'BalanceWithJobs',
            'PreferredDeliveryMethod',
            'ResaleNum',
            'JobStatus',
            'PrintOnCheckName',
            'DefaultTaxCodeRef',
            'CurrencyRef',
            'MetaData'
        ]
        
        # Copy all available attributes
        for attr in attributes:
            value = getattr(source_customer, attr, None)
            if value is not None:
                setattr(new_customer, attr, value)
                logger.debug(f"Copied attribute {attr}: {value}")

    def _create_single_customer(self, customer: Customer) -> bool:
        """Try to create a single customer and return success status"""
        try:
            customer_name = self._get_customer_display_name(customer)
            
            # Check if customer already exists
            if self._customer_exists(customer_name):
                existing_customer = self.existing_customers[customer_name]
                logger.info(f"Customer '{customer_name}' already exists with ID {existing_customer.Id}")
                # Store the mapping for existing customer
                self.id_mapping['Customer'][customer.Id] = existing_customer.Id
                return True

            # Create new customer object for target
            new_customer = Customer()
            self._copy_customer_attributes(customer, new_customer)
            
            # Log the customer data being sent
            logger.info(f"Attempting to create customer:")
            logger.info(f"  Display Name: {customer_name}")
            logger.info(f"  Company Name: {getattr(new_customer, 'CompanyName', 'N/A')}")
            logger.info(f"  Email: {getattr(new_customer, 'PrimaryEmailAddr', 'N/A')}")
            logger.info(f"  Phone: {getattr(new_customer, 'PrimaryPhone', 'N/A')}")
            
            # Try to save the customer
            created_customer = new_customer.save(qb=self.target_client)
            
            # If successful, store the mapping
            if created_customer and created_customer.Id:
                self.id_mapping['Customer'][customer.Id] = created_customer.Id
                # Add to existing customers
                self.existing_customers[customer_name] = created_customer
                logger.info(f"Successfully created customer {customer_name} with ID {created_customer.Id}")
                return True
                    
        except QuickbooksException as qb_error:
            logger.error(f"QuickBooks API Error for customer {customer_name}:")
            logger.error(f"  Message: {qb_error.message}")
            logger.error(f"  Error Code: {getattr(qb_error, 'error_code', 'Unknown')}")
            logger.error(f"  Detail: {getattr(qb_error, 'detail', '')}")
            if hasattr(qb_error, 'intuit_tid'):
                logger.error(f"  Intuit TID: {qb_error.intuit_tid}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error creating customer {customer_name}: {str(e)}")
            return False

    def transfer_customers(self) -> None:
        """Transfer customers from source to target company"""
        logger.info("Starting customer transfer...")
        try:
            # First, get all existing customers
            logger.info("Getting existing customers from target company...")
            self.existing_customers = self._get_existing_customers()
            logger.info(f"Found {len(self.existing_customers)} existing customers")
            
            # Get all customers from source
            all_customers = Customer.all(qb=self.source_client)
            logger.info(f"Retrieved {len(all_customers)} total customers from source")
            
            # Debug print first customer's attributes
            if all_customers:
                first_customer = all_customers[0]
                logger.info("First customer attributes:")
                for attr in ['DisplayName', 'Active', 'Id']:
                    logger.info(f"  {attr}: {getattr(first_customer, attr, 'Not set')}")
            
            # Filter customers based on criteria
            customers = [
                customer for customer in all_customers 
                if self._is_active_customer(customer)
            ]
            
            total_customers = len(customers)
            logger.info(f"Found {total_customers} active customers")
            logger.info(f"Filtered out {len(all_customers) - total_customers} inactive customers")
            
            # Print source customers
            print(f"\n=== Source Customers Details ({total_customers} customers) ===")
            for index, customer in enumerate(customers, 1):
                print(f"\nCustomer #{index} of {total_customers}")
                print(f"ID: {customer.Id}")
                print(f"Display Name: {self._get_customer_display_name(customer)}")
                print(f"Company Name: {getattr(customer, 'CompanyName', 'N/A')}")
                print(f"Active: {getattr(customer, 'Active', 'N/A')}")
                
                # Print contact information
                print(f"Primary Phone: {getattr(customer, 'PrimaryPhone', 'N/A')}")
                print(f"Email: {getattr(customer, 'PrimaryEmailAddr', 'N/A')}")
                print(f"Web Address: {getattr(customer, 'WebAddr', 'N/A')}")
                
                # Print balance information
                print(f"Balance: {getattr(customer, 'Balance', 'N/A')}")
                print(f"Balance With Jobs: {getattr(customer, 'BalanceWithJobs', 'N/A')}")
                print("-" * 50)
            
            # Try to create customers one by one
            logger.info("Attempting to create customers individually...")
            success_count = 0
            skipped_count = 0
            for customer in customers:
                customer_name = self._get_customer_display_name(customer)
                if self._customer_exists(customer_name):
                    logger.info(f"Skipping existing customer: {customer_name}")
                    skipped_count += 1
                    success_count += 1  # Count as success since we mapped the ID
                elif self._create_single_customer(customer):
                    success_count += 1
            
            # Print final summary
            logger.info("\n=== Transfer Summary ===")
            logger.info(f"Total customers processed: {total_customers}")
            logger.info(f"Customers skipped (already exist): {skipped_count}")
            logger.info(f"New customers created: {success_count - skipped_count}")
            logger.info(f"Total successful operations: {success_count}")
            
        except Exception as e:
            logger.error(f"Error transferring customers: {str(e)}")
            if hasattr(e, 'message'):
                logger.error(f"Error message: {e.message}")
            if hasattr(e, 'detail'):
                logger.error(f"Error detail: {e.detail}")
            raise 