from quickbooks.objects.employee import Employee
import logging
from typing import List, Dict
from qb_client import QuickBooksClient
import json
from quickbooks.exceptions import QuickbooksException
import time

logger = logging.getLogger(__name__)

class EmployeeTransfer(QuickBooksClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_mapping['Employee'] = {}
        self.existing_employees = {}  # Store existing employees by name

    def _get_employee_full_name(self, employee: Employee) -> str:
        """Get the full name of an employee in a consistent format"""
        given_name = getattr(employee, 'GivenName', '')
        family_name = getattr(employee, 'FamilyName', '')
        return f"{given_name} {family_name}".strip()

    def _is_active_employee(self, employee: Employee) -> bool:
        """Check if an employee is active"""
        return getattr(employee, 'Active', False)

    def _get_existing_employees(self) -> Dict[str, Employee]:
        """Get all existing employees from target company"""
        try:
            employees = Employee.all(qb=self.target_client)
            # Create a dictionary of employees by full name
            return {self._get_employee_full_name(emp): emp for emp in employees}
        except Exception as e:
            logger.error(f"Error getting existing employees: {str(e)}")
            return {}

    def _employee_exists(self, employee_name: str) -> bool:
        """Check if an employee with this name already exists"""
        return employee_name in self.existing_employees

    def _copy_employee_attributes(self, source_employee: Employee, new_employee: Employee) -> None:
        """Copy all available attributes from source employee to new employee"""
        # Core attributes that must be set
        new_employee.GivenName = getattr(source_employee, 'GivenName', '')
        new_employee.FamilyName = getattr(source_employee, 'FamilyName', '')
        
        # All possible Employee attributes
        attributes = [
            'Title',
            'MiddleName',
            'Suffix',
            'DisplayName',
            'PrintOnCheckName',
            'Active',
            'PrimaryPhone',
            'Mobile',
            'PrimaryEmailAddr',
            'BillableTime',
            'BillRate',
            'SSN',
            'EmployeeNumber',
            'HiredDate',
            'ReleasedDate',
            'BirthDate',
            'Gender',
            'Organization',
            'Department',
            'JobTitle',
            'CompensationDate',
            'Status',
            'PrimaryAddr',
            'OtherAddr',
            'MetaData'
        ]
        
        # Copy all available attributes
        for attr in attributes:
            value = getattr(source_employee, attr, None)
            if value is not None:
                setattr(new_employee, attr, value)
                logger.debug(f"Copied attribute {attr}: {value}")

    def _create_single_employee(self, employee: Employee) -> bool:
        """Try to create a single employee and return success status"""
        try:
            employee_name = self._get_employee_full_name(employee)
            
            # Check if employee already exists
            if self._employee_exists(employee_name):
                existing_employee = self.existing_employees[employee_name]
                logger.info(f"Employee '{employee_name}' already exists with ID {existing_employee.Id}")
                # Store the mapping for existing employee
                self.id_mapping['Employee'][employee.Id] = existing_employee.Id
                return True

            # Create new employee object for target
            new_employee = Employee()
            self._copy_employee_attributes(employee, new_employee)
            
            # Log the employee data being sent
            logger.info(f"Attempting to create employee:")
            logger.info(f"  Name: {employee_name}")
            logger.info(f"  Display Name: {getattr(new_employee, 'DisplayName', 'N/A')}")
            logger.info(f"  Employee Number: {getattr(new_employee, 'EmployeeNumber', 'N/A')}")
            logger.info(f"  Job Title: {getattr(new_employee, 'JobTitle', 'N/A')}")
            logger.info(f"  Department: {getattr(new_employee, 'Department', 'N/A')}")
            
            # Try to save the employee
            created_employee = new_employee.save(qb=self.target_client)
            
            # If successful, store the mapping
            if created_employee and created_employee.Id:
                self.id_mapping['Employee'][employee.Id] = created_employee.Id
                # Add to existing employees
                self.existing_employees[employee_name] = created_employee
                logger.info(f"Successfully created employee {employee_name} with ID {created_employee.Id}")
                return True
                    
        except QuickbooksException as qb_error:
            logger.error(f"QuickBooks API Error for employee {employee_name}:")
            logger.error(f"  Message: {qb_error.message}")
            logger.error(f"  Error Code: {getattr(qb_error, 'error_code', 'Unknown')}")
            logger.error(f"  Detail: {getattr(qb_error, 'detail', '')}")
            if hasattr(qb_error, 'intuit_tid'):
                logger.error(f"  Intuit TID: {qb_error.intuit_tid}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error creating employee {employee_name}: {str(e)}")
            return False

    def transfer_employees(self) -> None:
        """Transfer employees from source to target company"""
        logger.info("Starting employee transfer...")
        try:
            # First, get all existing employees
            logger.info("Getting existing employees from target company...")
            self.existing_employees = self._get_existing_employees()
            logger.info(f"Found {len(self.existing_employees)} existing employees")
            
            # Get all employees from source
            all_employees = Employee.all(qb=self.source_client)
            
            # Filter employees based on criteria
            employees = [
                employee for employee in all_employees 
                if self._is_active_employee(employee)
            ]
            
            total_employees = len(employees)
            logger.info(f"Found {total_employees} active employees")
            logger.info(f"Filtered out {len(all_employees) - total_employees} inactive employees")
            
            # Print source employees
            print(f"\n=== Source Employees Details ({total_employees} employees) ===")
            for index, employee in enumerate(employees, 1):
                print(f"\nEmployee #{index} of {total_employees}")
                print(f"ID: {employee.Id}")
                print(f"Name: {self._get_employee_full_name(employee)}")
                print(f"Display Name: {getattr(employee, 'DisplayName', 'N/A')}")
                print(f"Employee Number: {getattr(employee, 'EmployeeNumber', 'N/A')}")
                print(f"Job Title: {getattr(employee, 'JobTitle', 'N/A')}")
                print(f"Department: {getattr(employee, 'Department', 'N/A')}")
                print(f"Status: {getattr(employee, 'Status', 'N/A')}")
                print(f"Active: {getattr(employee, 'Active', 'N/A')}")
                
                # Print contact information
                print(f"Primary Phone: {getattr(employee, 'PrimaryPhone', 'N/A')}")
                print(f"Mobile: {getattr(employee, 'Mobile', 'N/A')}")
                print(f"Email: {getattr(employee, 'PrimaryEmailAddr', 'N/A')}")
                
                # Print employment details
                print(f"Hired Date: {getattr(employee, 'HiredDate', 'N/A')}")
                print(f"Released Date: {getattr(employee, 'ReleasedDate', 'N/A')}")
                print(f"Billable Time: {getattr(employee, 'BillableTime', 'N/A')}")
                print(f"Bill Rate: {getattr(employee, 'BillRate', 'N/A')}")
                print("-" * 50)
            
            # Try to create employees one by one
            logger.info("Attempting to create employees individually...")
            success_count = 0
            skipped_count = 0
            for employee in employees:
                employee_name = self._get_employee_full_name(employee)
                if self._employee_exists(employee_name):
                    logger.info(f"Skipping existing employee: {employee_name}")
                    skipped_count += 1
                    success_count += 1  # Count as success since we mapped the ID
                elif self._create_single_employee(employee):
                    success_count += 1
            
            # Print final summary
            logger.info("\n=== Transfer Summary ===")
            logger.info(f"Total employees processed: {total_employees}")
            logger.info(f"Employees skipped (already exist): {skipped_count}")
            logger.info(f"New employees created: {success_count - skipped_count}")
            logger.info(f"Total successful operations: {success_count}")
            
        except Exception as e:
            logger.error(f"Error transferring employees: {str(e)}")
            if hasattr(e, 'message'):
                logger.error(f"Error message: {e.message}")
            if hasattr(e, 'detail'):
                logger.error(f"Error detail: {e.detail}")
            raise 