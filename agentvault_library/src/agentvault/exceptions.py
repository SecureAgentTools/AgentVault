"""
Custom exception hierarchy for the AgentVault library.
"""

from typing import Optional, Any

class AgentVaultError(Exception):
    """Base exception for all AgentVault specific errors."""
    pass

# --- Configuration Error ---
class ConfigurationError(AgentVaultError):
    """Exception raised for configuration-related errors (e.g., missing settings, invalid setup)."""
    pass

# --- Agent Card Errors ---

class AgentCardError(AgentVaultError):
    """Base exception for errors related to Agent Cards."""
    pass

class AgentCardValidationError(AgentCardError):
    """Exception raised for Agent Card validation errors."""
    pass

class AgentCardFetchError(AgentCardError):
    """Exception raised when fetching an Agent Card fails."""
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[Any] = None # Can be str, dict, etc.
    ):
        """
        Initializes the AgentCardFetchError.

        Args:
            message: The error message.
            status_code: The HTTP status code returned by the remote agent, if available.
            response_body: The body of the error response from the remote agent, if available.
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        """Provides a more informative string representation."""
        base_str = super().__str__()
        details = []
        if self.status_code is not None:
            details.append(f"status_code={self.status_code}")
        if self.response_body is not None:
            # Truncate long response bodies for display
            body_repr = repr(self.response_body)
            if len(body_repr) > 100:
                body_repr = body_repr[:100] + "..."
            details.append(f"response_body={body_repr}")

        if details:
            return f"{base_str} ({', '.join(details)})"
        else:
            return base_str


# --- A2A Protocol Errors ---

class A2AError(AgentVaultError):
    """Base exception for errors related to the A2A protocol."""
    pass

class A2AConnectionError(A2AError):
    """Exception raised for errors during A2A connection attempts."""
    pass

class A2AAuthenticationError(A2AError):
    """Exception raised for A2A authentication failures."""
    pass

class A2ARemoteAgentError(A2AError):
    """
    Exception raised when the remote agent returns an error response
    during an A2A operation.
    """
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[Any] = None # Can be str, dict, etc.
    ):
        """
        Initializes the A2ARemoteAgentError.

        Args:
            message: The error message.
            status_code: The HTTP status code returned by the remote agent, if available.
            response_body: The body of the error response from the remote agent, if available.
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        """Provides a more informative string representation."""
        base_str = super().__str__()
        details = []
        if self.status_code is not None:
            details.append(f"status_code={self.status_code}")
        if self.response_body is not None:
            # Truncate long response bodies for display
            body_repr = repr(self.response_body)
            if len(body_repr) > 100:
                body_repr = body_repr[:100] + "..."
            details.append(f"response_body={body_repr}")

        if details:
            return f"{base_str} ({', '.join(details)})"
        else:
            return base_str


class A2ATimeoutError(A2AConnectionError):
    """Exception raised when an A2A operation times out."""
    pass

class A2AMessageError(A2AError):
    """Exception raised for errors related to A2A message formatting or content."""
    pass

# --- Key Management Errors ---

class KeyManagementError(AgentVaultError):
    """Base exception for errors related to local key management."""
    pass
