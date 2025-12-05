"""
Authentication API Endpoints

Endpoints for user login, logout, and token validation.
"""

import logging
from typing import Optional
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.models.auth_model import LoginRequest, LoginResponse, TokenData
from app.services.auth.auth_service import get_auth_service, AuthService, ACCESS_TOKEN_EXPIRE_HOURS

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    """
    Dependency to get current authenticated user from JWT token.
    
    Args:
        credentials: HTTP Authorization header with Bearer token
        
    Returns:
        TokenData with user information
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials
    token_data = AuthService.decode_access_token(token)
    
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_data


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return access token.
    
    Args:
        request: Login credentials (username and password)
        
    Returns:
        LoginResponse with access token and user info
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        auth_service = get_auth_service()
        
        # Authenticate user
        user = await auth_service.authenticate_user(request.username, request.password)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create access token
        token_data = TokenData(
            user_id=user.user_id,
            role=user.role,
            member_id=user.member_id
        )
        access_token = AuthService.create_access_token(
            data=token_data,
            expires_delta=timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
        )
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user_id=user.user_id,
            full_name=user.full_name,
            role=user.role,
            member_id=user.member_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/logout")
async def logout(current_user: TokenData = Depends(get_current_user)):
    """
    Logout user (client should discard token).
    
    Note: Since we're using stateless JWT tokens, actual logout happens on client side.
    This endpoint is mainly for logging purposes.
    """
    logger.info(f"User logged out: {current_user.user_id}")
    return {
        "status": "success",
        "message": "Logged out successfully"
    }


@router.get("/me")
async def get_current_user_info(current_user: TokenData = Depends(get_current_user)):
    """
    Get current user information from token.
    
    Returns:
        Current user's information
    """
    return {
        "user_id": current_user.user_id,
        "role": current_user.role,
        "member_id": current_user.member_id
    }


@router.get("/verify")
async def verify_token(current_user: TokenData = Depends(get_current_user)):
    """
    Verify if token is valid.
    
    Returns:
        Verification status
    """
    return {
        "valid": True,
        "user_id": current_user.user_id
    }

