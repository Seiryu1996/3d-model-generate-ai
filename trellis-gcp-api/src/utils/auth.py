"""
Simple authentication and API key management for development.
"""
import hashlib
import secrets
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import HTTPException, status, Header, Depends
import structlog

logger = structlog.get_logger(__name__)

# Development mode - simple in-memory storage
DEV_API_KEYS = {
    "dev-key-123": {
        "user_id": "dev-user",
        "name": "Development Key",
        "created_at": datetime.utcnow(),
        "active": True
    }
}

class SimpleAPIKeyManager:
    """Simple API key manager for development."""
    
    def __init__(self):
        self.api_keys = DEV_API_KEYS.copy()
    
    def generate_api_key(self, user_id: str, name: str) -> str:
        """Generate a new API key."""
        api_key = f"trellis_{secrets.token_urlsafe(32)}"
        
        self.api_keys[api_key] = {
            "user_id": user_id,
            "name": name,
            "created_at": datetime.utcnow(),
            "active": True,
            "last_used": None
        }
        
        return api_key
    
    def validate_api_key(self, api_key: str) -> Optional[Dict]:
        """Validate API key and return key info."""
        key_info = self.api_keys.get(api_key)
        if key_info and key_info["active"]:
            # Update last used
            key_info["last_used"] = datetime.utcnow()
            return key_info
        return None
    
    def list_user_keys(self, user_id: str) -> List[Dict]:
        """List all keys for a user."""
        keys = []
        for api_key, info in self.api_keys.items():
            if info["user_id"] == user_id and info["active"]:
                keys.append({
                    "key": api_key[:16] + "...",  # Masked key
                    "name": info["name"],
                    "created_at": info["created_at"],
                    "last_used": info.get("last_used"),
                    "active": info["active"]
                })
        return keys
    
    def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key."""
        if api_key in self.api_keys:
            self.api_keys[api_key]["active"] = False
            return True
        return False


# Global instance
_api_key_manager = SimpleAPIKeyManager()


def get_api_key_manager() -> SimpleAPIKeyManager:
    """Get API key manager instance."""
    return _api_key_manager


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verify API key from header."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )
    
    key_info = _api_key_manager.validate_api_key(x_api_key)
    if not key_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return key_info["user_id"]


async def get_current_user_id() -> str:
    """Get current user ID - development version always returns dev-user."""
    return "dev-user"


# Optional dependency for API routes that can work without auth in dev
async def optional_verify_api_key(x_api_key: Optional[str] = Header(None)) -> Optional[str]:
    """Optional API key verification - returns None if no key provided."""
    if not x_api_key:
        return None
    
    key_info = _api_key_manager.validate_api_key(x_api_key)
    if key_info:
        return key_info["user_id"]
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key"
    )

async def rate_limit_check(user_id: str = Depends(get_current_user_id)) -> None:
    """Simple rate limiting check - always passes for development."""
    # In development, we skip rate limiting
    logger.info("Rate limit check passed", user_id=user_id)
    return None
