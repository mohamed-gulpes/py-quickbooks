from quickbooks.objects.vendor import Vendor
import logging
from typing import List, Dict
from qb_client import QuickBooksClient
import json
from quickbooks.exceptions import QuickbooksException
import time

logger = logging.getLogger(__name__)

class VendorTransfer(QuickBooksClient):
    """Class for transferring vendors between QuickBooks companies"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_mapping['Vendor'] = {}
        self.existing_vendors = {}  # Store existing vendors by name

    def _get_vendor_display_name(self, vendor: Vendor) -> str:
        """Get the display name of a vendor in a consistent format"""
        return getattr(vendor, 'DisplayName', '').strip()

    def _is_active_vendor(self, vendor: Vendor) -> bool:
        """Check if a vendor is active"""
        active_status = getattr(vendor, 'Active', True)  # Default to True if not specified
        logger.debug(f"Vendor {getattr(vendor, 'DisplayName', 'Unknown')}: Active status = {active_status}")
        return active_status

    def _get_existing_vendors(self) -> Dict[str, Vendor]:
        """Get all existing vendors from target company"""
        try:
            vendors = Vendor.all(qb=self.target_client)
            vendor_dict = {}
            
            # Create dictionaries for both display name and ID
            for vendor in vendors:
                name = self._get_vendor_display_name(vendor)
                if name:
                    vendor_dict[name] = vendor
                    # Also store by ID for direct mapping
                    if hasattr(vendor, 'Id'):
                        vendor_dict[vendor.Id] = vendor
            
            logger.info(f"Found {len(vendors)} existing vendors")
            return vendor_dict
        except Exception as e:
            logger.error(f"Error getting existing vendors: {str(e)}")
            return {}

    def _find_existing_vendor(self, vendor_name: str) -> Vendor:
        """Find existing vendor by name or by querying QuickBooks"""
        # First check our cache
        if vendor_name in self.existing_vendors:
            return self.existing_vendors[vendor_name]
            
        try:
            # Try to query QB directly
            query = f"SELECT * FROM Vendor WHERE DisplayName = '{vendor_name}'"
            vendors = Vendor.query(query, qb=self.target_client)
            if vendors:
                vendor = vendors[0]
                # Cache it for future use
                self.existing_vendors[vendor_name] = vendor
                if hasattr(vendor, 'Id'):
                    self.existing_vendors[vendor.Id] = vendor
                return vendor
        except Exception as e:
            logger.debug(f"Error querying for vendor {vendor_name}: {str(e)}")
        
        return None

    def _copy_vendor_attributes(self, source_vendor: Vendor, new_vendor: Vendor) -> None:
        """Copy all available attributes from source vendor to new vendor"""
        # All possible Vendor attributes
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
            'OtherAddr',
            'Notes',
            'Balance',
            'OpenBalanceDate',
            'VendorPaymentBankDetail',
            'TaxIdentifier',
            'AcctNum',
            'Terms',
            'PrintOnCheckName',
            'DefaultTaxCodeRef',
            'CurrencyRef',
            'MetaData',
            'VendorType',
            'T4AEligible',
            'T5018Eligible'
        ]
        
        # Copy all available attributes
        for attr in attributes:
            value = getattr(source_vendor, attr, None)
            if value is not None:
                setattr(new_vendor, attr, value)
                logger.debug(f"Copied attribute {attr}: {value}")

    def _create_single_vendor(self, vendor: Vendor) -> bool:
        """Try to create a single vendor and return success status"""
        try:
            vendor_name = self._get_vendor_display_name(vendor)
            
            # First try to find existing vendor
            existing_vendor = self._find_existing_vendor(vendor_name)
            if existing_vendor:
                logger.info(f"Vendor '{vendor_name}' already exists with ID {existing_vendor.Id}")
                # Store the mapping for existing vendor
                self.id_mapping['Vendor'][vendor.Id] = existing_vendor.Id
                return True

            # Create new vendor object for target
            new_vendor = Vendor()
            self._copy_vendor_attributes(vendor, new_vendor)
            
            # Log the vendor data being sent
            logger.info(f"Attempting to create vendor:")
            logger.info(f"  Display Name: {vendor_name}")
            logger.info(f"  Company Name: {getattr(new_vendor, 'CompanyName', 'N/A')}")
            logger.info(f"  Email: {getattr(new_vendor, 'PrimaryEmailAddr', 'N/A')}")
            logger.info(f"  Phone: {getattr(new_vendor, 'PrimaryPhone', 'N/A')}")
            
            try:
                # Try to save the vendor
                created_vendor = new_vendor.save(qb=self.target_client)
                
                # If successful, store the mapping
                if created_vendor and created_vendor.Id:
                    self.id_mapping['Vendor'][vendor.Id] = created_vendor.Id
                    # Add to existing vendors
                    self.existing_vendors[vendor_name] = created_vendor
                    self.existing_vendors[created_vendor.Id] = created_vendor
                    logger.info(f"Successfully created vendor {vendor_name} with ID {created_vendor.Id}")
                    return True
                    
            except QuickbooksException as qb_error:
                if qb_error.error_code == '6240':  # Name already exists
                    # Try to get the existing vendor's ID from the error message
                    import re
                    id_match = re.search(r'Id=(\d+)', qb_error.detail)
                    if id_match:
                        existing_id = id_match.group(1)
                        logger.info(f"Found existing vendor ID from error: {existing_id}")
                        # Store the mapping
                        self.id_mapping['Vendor'][vendor.Id] = existing_id
                        return True
                    
                logger.error(f"QuickBooks API Error for vendor {vendor_name}:")
                logger.error(f"  Message: {qb_error.message}")
                logger.error(f"  Error Code: {getattr(qb_error, 'error_code', 'Unknown')}")
                logger.error(f"  Detail: {getattr(qb_error, 'detail', '')}")
                if hasattr(qb_error, 'intuit_tid'):
                    logger.error(f"  Intuit TID: {qb_error.intuit_tid}")
                return False
                    
        except Exception as e:
            logger.error(f"Unexpected error creating vendor {vendor_name}: {str(e)}")
            return False

    def transfer_vendors(self) -> None:
        """Transfer vendors from source to target company"""
        logger.info("Starting vendor transfer...")
        try:
            # First, get all existing vendors
            logger.info("Getting existing vendors from target company...")
            self.existing_vendors = self._get_existing_vendors()
            logger.info(f"Found {len(self.existing_vendors)} existing vendors")
            
            # Get all vendors from source
            all_vendors = Vendor.all(qb=self.source_client)
            logger.info(f"Retrieved {len(all_vendors)} vendors from source company")
            
            # Try to create vendors one by one
            logger.info("Attempting to create vendors individually...")
            success_count = 0
            skipped_count = 0
            for vendor in all_vendors:
                vendor_name = self._get_vendor_display_name(vendor)
                if self._find_existing_vendor(vendor_name):
                    logger.info(f"Skipping existing vendor: {vendor_name}")
                    skipped_count += 1
                    success_count += 1  # Count as success since we mapped the ID
                elif self._create_single_vendor(vendor):
                    success_count += 1
            
            # Print final summary
            logger.info("\n=== Transfer Summary ===")
            logger.info(f"Total vendors processed: {len(all_vendors)}")
            logger.info(f"Vendors skipped (already exist): {skipped_count}")
            logger.info(f"New vendors created: {success_count - skipped_count}")
            logger.info(f"Total successful operations: {success_count}")
            
        except Exception as e:
            logger.error(f"Error transferring vendors: {str(e)}")
            raise 