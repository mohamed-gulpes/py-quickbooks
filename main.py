import os
import logging
from qb_account import AccountTransfer
from qb_employee import EmployeeTransfer
from qb_customer import CustomerTransfer
from qb_journal import JournalEntryTransfer
from qb_class import ClassTransfer
from qb_vendor import VendorTransfer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    credentials_path = os.path.join(script_dir, 'credentials.yml')
    
    # First transfer chart of accounts
    logger.info("Starting chart of accounts transfer...")
    account_transfer = AccountTransfer(credentials_file=credentials_path)
    account_transfer.transfer_accounts()

    # Then transfer employees
    logger.info("Starting employees transfer...")
    employee_transfer = EmployeeTransfer(credentials_file=credentials_path)
    employee_transfer.transfer_employees()
    
    # Then transfer customers
    logger.info("Starting customers transfer...")
    customer_transfer = CustomerTransfer(credentials_file=credentials_path)
    customer_transfer.transfer_customers()

    # Then transfer classes
    logger.info("Starting classes transfer...")
    class_transfer = ClassTransfer(credentials_file=credentials_path)
    class_transfer.transfer_classes()

    # Then transfer vendors
    logger.info("Starting vendors transfer...")
    vendor_transfer = VendorTransfer(credentials_file=credentials_path)
    vendor_transfer.transfer_vendors()

    # Then transfer journal entries
    logger.info("Starting journal entries transfer...")
    journal_transfer = JournalEntryTransfer(credentials_file=credentials_path)
    journal_transfer.transfer_journals()

    logger.info("Data transfer completed successfully")

if __name__ == "__main__":
    main() 