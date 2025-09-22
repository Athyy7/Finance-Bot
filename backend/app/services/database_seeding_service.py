import json
import os
from typing import List, Dict, Any
from fastapi import HTTPException

from backend.app.config.database import mongodb_database
from backend.app.utils.logging_utils import get_logger


class DatabaseSeedingService:
    """Service for seeding database collections with initial data."""
    
    def __init__(self):
        self.mongodb = mongodb_database
        self.logger = get_logger("database_seeding")
        
    async def seed_financial_data_collection(self) -> bool:
        """
        Seeds the financial_data_collection with data from financial_data.json.
        
        Returns:
            bool: True if seeding was successful or collection already has data, False otherwise.
        """
        try:
            # Get the financial data collection
            collection = self.mongodb.get_financial_data_collection()
            
            # Check if collection already has data
            document_count = await collection.count_documents({})
            if document_count > 0:
                self.logger.info(f"Financial data collection already contains {document_count} documents. Skipping seeding.")
                return True
            
            # Load data from JSON file
            financial_data = await self._load_financial_data()
            if not financial_data:
                self.logger.warning("No financial data found to seed.")
                return False
            
            # Insert data in batches for better performance
            await self._batch_insert_data(collection, financial_data)
            
            # Verify insertion
            final_count = await collection.count_documents({})
            self.logger.info(f"Successfully seeded financial data collection with {final_count} documents.")
            
            # Create useful indexes for better query performance
            await self._create_indexes(collection)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error seeding financial data collection: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to seed financial data collection: {str(e)}"
            )
    
    async def _load_financial_data(self) -> List[Dict[str, Any]]:
        """
        Loads financial data from the JSON file.
        
        Returns:
            List[Dict[str, Any]]: List of financial data records.
        """
        try:
            # Get the path to the financial data JSON file
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            json_file_path = os.path.join(project_root, "data", "financial_data.json")
            
            if not os.path.exists(json_file_path):
                self.logger.error(f"Financial data file not found at: {json_file_path}")
                return []
            
            with open(json_file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                
            self.logger.info(f"Loaded {len(data)} records from financial_data.json")
            return data
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Error parsing JSON file: {str(e)}")
            return []
        except Exception as e:
            self.logger.error(f"Error loading financial data file: {str(e)}")
            return []
    
    async def _batch_insert_data(self, collection, data: List[Dict[str, Any]], batch_size: int = 1000):
        """
        Inserts data in batches for better performance.
        
        Args:
            collection: MongoDB collection instance
            data: List of documents to insert
            batch_size: Number of documents to insert per batch
        """
        try:
            total_records = len(data)
            inserted_count = 0
            
            # Process data in batches
            for i in range(0, total_records, batch_size):
                batch = data[i:i + batch_size]
                result = await collection.insert_many(batch)
                inserted_count += len(result.inserted_ids)
                
                self.logger.info(f"Inserted batch {i//batch_size + 1}: {len(result.inserted_ids)} documents ({inserted_count}/{total_records})")
            
            self.logger.info(f"Completed batch insertion: {inserted_count} total documents inserted.")
            
        except Exception as e:
            self.logger.error(f"Error during batch insertion: {str(e)}")
            raise
    
    async def _create_indexes(self, collection):
        """
        Creates useful indexes on the financial data collection for better query performance.
        
        Args:
            collection: MongoDB collection instance
        """
        try:
            # Create indexes on commonly queried fields
            indexes_to_create = [
                ("User_ID", 1),
                ("Age", 1),
                ("Gender", 1),
                ("Country", 1),
                ("Annual_Income", 1),
                ("Risk_Tolerance", 1),
                ("Investment_Type", 1),
                ("Transaction_Date", 1),
                ("Suspicious_Flag", 1),
                ("Financial_Goals", 1),
                ("Employment_Status", 1),
                ("Marital_Status", 1)
            ]
            
            for field, order in indexes_to_create:
                await collection.create_index([(field, order)])
                self.logger.debug(f"Created index on field: {field}")
            
            # Create compound indexes for common query patterns
            compound_indexes = [
                [("User_ID", 1), ("Transaction_Date", -1)],  # User transactions by date
                [("Country", 1), ("Age", 1)],  # Demographics
                [("Risk_Tolerance", 1), ("Investment_Type", 1)],  # Investment profile
                [("Annual_Income", 1), ("Age", 1)],  # Income demographics
            ]
            
            for compound_index in compound_indexes:
                await collection.create_index(compound_index)
                self.logger.debug(f"Created compound index: {compound_index}")
            
            self.logger.info("Successfully created indexes on financial data collection.")
            
        except Exception as e:
            self.logger.warning(f"Error creating indexes (non-critical): {str(e)}")
            # Don't raise exception for index creation failures as they're not critical
    
    async def check_collection_status(self) -> Dict[str, Any]:
        """
        Checks the status of the financial data collection.
        
        Returns:
            Dict[str, Any]: Collection status information.
        """
        try:
            collection = self.mongodb.get_financial_data_collection()
            document_count = await collection.count_documents({})
            
            status = {
                "collection_exists": True,
                "document_count": document_count,
                "has_data": document_count > 0
            }
            
            if document_count > 0:
                # Get sample document to show structure
                sample_doc = await collection.find_one({})
                status["sample_fields"] = list(sample_doc.keys()) if sample_doc else []
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error checking collection status: {str(e)}")
            return {
                "collection_exists": False,
                "document_count": 0,
                "has_data": False,
                "error": str(e)
            }


# Instantiate the seeding service
database_seeding_service = DatabaseSeedingService()
