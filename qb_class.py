from quickbooks.objects.trackingclass import Class
import logging
from typing import List, Dict
from qb_client import QuickBooksClient
from quickbooks.exceptions import QuickbooksException

logger = logging.getLogger(__name__)

class ClassTransfer(QuickBooksClient):
    """Transfer classes from source to target company"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_mapping['Class'] = {}
        self.existing_classes = {}  # Store existing classes by name

    def _get_class_name(self, class_obj: Class) -> str:
        """Get the name of a class in a consistent format"""
        return getattr(class_obj, 'Name', '').strip()

    def _is_active_class(self, class_obj: Class) -> bool:
        """Check if a class is active"""
        return getattr(class_obj, 'Active', True)  # Default to True if not specified

    def _get_existing_classes(self) -> Dict[str, Class]:
        """Get all existing classes from target company"""
        try:
            # Get all classes with a high limit
            classes = Class.all(qb=self.target_client, max_results=1000)  # Increased limit
            logger.info(f"Retrieved {len(classes)} total classes from target company")
            # Create a dictionary of classes by name
            return {self._get_class_name(cls): cls for cls in classes}
        except Exception as e:
            logger.error(f"Error getting existing classes: {str(e)}")
            return {}

    def _class_exists(self, class_name: str) -> bool:
        """Check if a class with this name already exists"""
        return class_name in self.existing_classes

    def _get_hierarchy_level(self, class_obj: Class) -> int:
        """Get the hierarchy level of a class based on its fully qualified name"""
        fully_qualified = getattr(class_obj, 'FullyQualifiedName', '')
        if not fully_qualified:
            return 0
        return len(fully_qualified.split(':'))

    def _copy_class_attributes(self, source_class: Class, new_class: Class) -> None:
        """Copy all available attributes from source class to new class"""
        # All possible Class attributes
        attributes = [
            'Name',
            'SubClass',
            'Active',
            'Division',
            'FullyQualifiedName'
        ]
        
        # Copy all available attributes
        for attr in attributes:
            value = getattr(source_class, attr, None)
            if value is not None:
                setattr(new_class, attr, value)
                logger.debug(f"Copied attribute {attr}: {value}")

        # Handle parent reference separately
        parent_name = None
        fully_qualified = getattr(source_class, 'FullyQualifiedName', '')
        if fully_qualified and ':' in fully_qualified:
            parent_name = ':'.join(fully_qualified.split(':')[:-1])
            if parent_name in self.existing_classes:
                parent_id = self.existing_classes[parent_name].Id
                new_class.ParentRef = {'value': parent_id, 'name': parent_name}
                logger.debug(f"Set parent reference to {parent_name} (ID: {parent_id})")

    def _create_single_class(self, class_obj: Class) -> bool:
        """Try to create a single class and return success status"""
        try:
            class_name = self._get_class_name(class_obj)
            fully_qualified = getattr(class_obj, 'FullyQualifiedName', class_name)
            
            # Check if class already exists
            if self._class_exists(fully_qualified):
                existing_class = self.existing_classes[fully_qualified]
                logger.info(f"Class '{fully_qualified}' already exists with ID {existing_class.Id}")
                # Store the mapping for existing class
                self.id_mapping['Class'][class_obj.Id] = existing_class.Id
                return True

            # Create new class object for target
            new_class = Class()
            self._copy_class_attributes(class_obj, new_class)
            
            # Log the class data being sent
            logger.info(f"Attempting to create class:")
            logger.info(f"  Name: {class_name}")
            logger.info(f"  Fully Qualified Name: {fully_qualified}")
            logger.info(f"  SubClass: {getattr(new_class, 'SubClass', 'N/A')}")
            if hasattr(new_class, 'ParentRef'):
                logger.info(f"  Parent: {new_class.ParentRef}")
            logger.info(f"  Division: {getattr(new_class, 'Division', 'N/A')}")
            
            # Try to save the class
            created_class = new_class.save(qb=self.target_client)
            
            # If successful, store the mapping
            if created_class and created_class.Id:
                self.id_mapping['Class'][class_obj.Id] = created_class.Id
                # Add to existing classes
                self.existing_classes[fully_qualified] = created_class
                logger.info(f"Successfully created class {fully_qualified} with ID {created_class.Id}")
                return True
                    
        except QuickbooksException as qb_error:
            logger.error(f"QuickBooks API Error for class {class_name}:")
            logger.error(f"  Message: {qb_error.message}")
            logger.error(f"  Error Code: {getattr(qb_error, 'error_code', 'Unknown')}")
            logger.error(f"  Detail: {getattr(qb_error, 'detail', '')}")
            if hasattr(qb_error, 'intuit_tid'):
                logger.error(f"  Intuit TID: {qb_error.intuit_tid}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error creating class {class_name}: {str(e)}")
            return False

    def transfer_classes(self) -> None:
        """Transfer classes from source to target company"""
        logger.info("Starting class transfer...")
        try:
            # First, get all existing classes
            logger.info("Getting existing classes from target company...")
            self.existing_classes = self._get_existing_classes()
            logger.info(f"Found {len(self.existing_classes)} existing classes")
            
            # Get all classes from source with higher limit
            all_classes = Class.all(qb=self.source_client, max_results=1000)  # Increased limit
            logger.info(f"Retrieved {len(all_classes)} total classes from source")
            
            # Filter active classes and sort by hierarchy level
            classes = [
                class_obj for class_obj in all_classes 
                if self._is_active_class(class_obj)
            ]
            classes.sort(key=self._get_hierarchy_level)
            
            total_classes = len(classes)
            logger.info(f"Found {total_classes} active classes")
            logger.info(f"Filtered out {len(all_classes) - total_classes} inactive classes")
            
            # Print source classes with detailed information
            print(f"\n=== Source Classes Details ({total_classes} classes) ===")
            for index, class_obj in enumerate(classes, 1):
                print(f"\nClass #{index} of {total_classes}")
                print("=" * 80)
                print("Class Information:")
                print(f"  ID: {class_obj.Id}")
                print(f"  Name: {self._get_class_name(class_obj)}")
                print(f"  Fully Qualified Name: {getattr(class_obj, 'FullyQualifiedName', 'N/A')}")
                print(f"  Hierarchy Level: {self._get_hierarchy_level(class_obj)}")
                print(f"  Active: {getattr(class_obj, 'Active', 'N/A')}")
                print(f"  SubClass: {getattr(class_obj, 'SubClass', 'N/A')}")
                print(f"  Division: {getattr(class_obj, 'Division', 'N/A')}")
                
                # Print metadata if exists
                metadata = getattr(class_obj, 'MetaData', None)
                if metadata:
                    print("  Metadata:")
                    print(f"    Created Time: {getattr(metadata, 'CreateTime', 'N/A')}")
                    print(f"    Last Updated Time: {getattr(metadata, 'LastUpdatedTime', 'N/A')}")
                
                print("-" * 80)
            
            # Try to create classes one by one
            logger.info("Attempting to create classes individually...")
            success_count = 0
            skipped_count = 0
            for class_obj in classes:
                class_name = self._get_class_name(class_obj)
                fully_qualified = getattr(class_obj, 'FullyQualifiedName', class_name)
                if self._class_exists(fully_qualified):
                    logger.info(f"Skipping existing class: {fully_qualified}")
                    skipped_count += 1
                    success_count += 1  # Count as success since we mapped the ID
                elif self._create_single_class(class_obj):
                    success_count += 1
            
            # Print final summary
            logger.info("\n=== Transfer Summary ===")
            logger.info(f"Total classes processed: {total_classes}")
            logger.info(f"Classes skipped (already exist): {skipped_count}")
            logger.info(f"New classes created: {success_count - skipped_count}")
            logger.info(f"Total successful operations: {success_count}")
            
        except Exception as e:
            logger.error(f"Error transferring classes: {str(e)}")
            if hasattr(e, 'message'):
                logger.error(f"Error message: {e.message}")
            if hasattr(e, 'detail'):
                logger.error(f"Error detail: {e.detail}")
            raise 