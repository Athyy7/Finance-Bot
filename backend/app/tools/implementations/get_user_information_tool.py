from typing import Any, Dict
from backend.app.tools.base.tool_base import BaseTool
from backend.app.config.database import mongodb_database
from backend.app.utils.logging_utils import get_logger


class GetUserInformationTool(BaseTool):
    """
    A tool to retrieve complete user information from the financial data collection.
    Takes a User ID and returns all financial and personal data for that user.
    """

    def __init__(self):
        self.logger = get_logger("get_user_information_tool")

    @property
    def get_tool_definition(self) -> Dict[str, Any]:
        """Get the tool definition for LLM API."""
        return {
            "name": "get_user_information",
            "description": "Retrieve complete financial and personal information for a specific user from the financial database. Returns all user data including demographics, financial status, investment details, transaction history, and risk profile.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The unique User ID to search for (e.g., 'U1000', 'U1001', etc.)"
                    }
                },
                "required": ["user_id"]
            }
        }

    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """
        Execute the get user information tool.
        
        Args:
            parameters: Tool parameters containing the user_id
            
        Returns:
            Complete user information or error message
        """
        try:
            user_id = parameters.get("user_id", "").strip()
            
            if not user_id:
                return {
                    "success": False,
                    "error": "No user_id provided",
                    "user_data": None
                }

            self.logger.info(f"Searching for user with ID: {user_id}")
            
            # Get the financial data collection
            collection = mongodb_database.get_financial_data_collection()
            
            # Query for the user by User_ID
            user_document = await collection.find_one({"User_ID": user_id})
            
            if user_document:
                # Remove MongoDB's _id field for cleaner output
                if "_id" in user_document:
                    del user_document["_id"]
                
                self.logger.info(f"Successfully retrieved user information for: {user_id}")
                
                return {
                    "success": True,
                    "user_id": user_id,
                    "user_data": user_document,
                    "message": f"Complete user information retrieved for User ID: {user_id}"
                }
            else:
                self.logger.warning(f"User not found with ID: {user_id}")
                
                # Get some sample user IDs to help with suggestions
                sample_users = []
                async for doc in collection.find({}, {"User_ID": 1}).limit(5):
                    sample_users.append(doc.get("User_ID"))
                
                return {
                    "success": False,
                    "error": f"No user found with ID: {user_id}",
                    "user_data": None,
                    "suggestion": f"User ID not found. Try one of these sample IDs: {sample_users}"
                }
                
        except Exception as e:
            error_msg = f"Error retrieving user information: {str(e)}"
            self.logger.error(error_msg)
            
            return {
                "success": False,
                "error": error_msg,
                "user_data": None
            }

    async def get_sample_user_ids(self, limit: int = 10) -> list:
        """
        Helper method to get sample user IDs for testing or suggestions.
        
        Args:
            limit: Maximum number of user IDs to return
            
        Returns:
            List of sample user IDs
        """
        try:
            collection = mongodb_database.get_financial_data_collection()
            sample_users = []
            
            async for doc in collection.find({}, {"User_ID": 1}).limit(limit):
                sample_users.append(doc.get("User_ID"))
            
            return sample_users
        except Exception as e:
            self.logger.error(f"Error getting sample user IDs: {str(e)}")
            return []

    async def search_users_by_criteria(self, criteria: Dict[str, Any], limit: int = 10) -> list:
        """
        Helper method to search users by various criteria.
        
        Args:
            criteria: Dictionary of search criteria (e.g., {"Country": "Canada", "Age": {"$gte": 30}})
            limit: Maximum number of users to return
            
        Returns:
            List of user documents matching the criteria
        """
        try:
            collection = mongodb_database.get_financial_data_collection()
            users = []
            
            async for doc in collection.find(criteria).limit(limit):
                if "_id" in doc:
                    del doc["_id"]
                users.append(doc)
            
            return users
        except Exception as e:
            self.logger.error(f"Error searching users by criteria: {str(e)}")
            return []
