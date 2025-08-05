"""
Authentication and API key management endpoints.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
import structlog

from ...models.api import APIKeyResponse, CreateAPIKeyRequest, APIKeyListResponse
from ...utils.auth import get_api_key_manager, get_current_user_id

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post(
    "/auth/api-keys",
    response_model=APIKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API Key",
    description="Create a new API key for the authenticated user."
)
async def create_api_key(
    request: CreateAPIKeyRequest,
    user_id: str = Depends(get_current_user_id)
) -> APIKeyResponse:
    """Create new API key."""
    api_key_manager = get_api_key_manager()
    
    try:
        api_key = api_key_manager.generate_api_key(
            user_id=user_id,
            name=request.name
        )
        
        logger.info(
            "API key created",
            user_id=user_id,
            key_name=request.name
        )
        
        return APIKeyResponse(
            api_key=api_key,
            name=request.name,
            message="API key created successfully"
        )
        
    except Exception as e:
        logger.error("Failed to create API key", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create API key"
        )


@router.get(
    "/auth/api-keys",
    response_model=APIKeyListResponse,
    summary="List API Keys",  
    description="List all API keys for the authenticated user."
)
async def list_api_keys(
    user_id: str = Depends(get_current_user_id)
) -> APIKeyListResponse:
    """List user's API keys."""
    api_key_manager = get_api_key_manager()
    
    try:
        keys = api_key_manager.list_user_keys(user_id)
        
        return APIKeyListResponse(
            api_keys=keys,
            total=len(keys)
        )
        
    except Exception as e:
        logger.error("Failed to list API keys", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list API keys"
        )


@router.delete(
    "/auth/api-keys/{api_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke API Key",
    description="Revoke an API key."
)
async def revoke_api_key(
    api_key: str,
    user_id: str = Depends(get_current_user_id)
) -> None:
    """Revoke API key."""
    api_key_manager = get_api_key_manager()
    
    try:
        # Validate that key belongs to user
        key_info = api_key_manager.validate_api_key(api_key)
        if not key_info or key_info["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        success = api_key_manager.revoke_api_key(api_key)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        logger.info(
            "API key revoked",
            user_id=user_id,
            key=api_key[:16] + "..."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to revoke API key", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke API key"
        )