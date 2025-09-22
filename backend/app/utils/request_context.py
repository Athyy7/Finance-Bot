import uuid
from contextvars import ContextVar
from typing import Optional

# Context variable to store the request ID
request_id_var: ContextVar[Optional[str]] = ContextVar(
    "request_id", default=None
)


def generate_request_id() -> str:
    """
    Generate a new UUID for request tracking.

    Returns:
        str: A new UUID string
    """
    return str(uuid.uuid4())


def set_request_id(request_id: str) -> None:
    """
    Set the request ID in the current context.

    Args:
        request_id (str): The request ID to set
    """
    request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """
    Get the current request ID from context.

    Returns:
        Optional[str]: The current request ID, or None if not set
    """
    return request_id_var.get()


def get_or_generate_request_id() -> str:
    """
    Get the current request ID, or generate a new one if not set.

    Returns:
        str: The current or newly generated request ID
    """
    current_id = get_request_id()
    if current_id is None:
        current_id = generate_request_id()
        set_request_id(current_id)
    return current_id
