"""
Supabase authentication utilities and dependencies.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from sqlalchemy.orm import Session

from app.database.supabase_client import supabase
from app.database.database import get_db
from app.models.models_supabase import Profile

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Profile:
    """
    Verify Supabase JWT token and return current user profile.
    
    Usage:
        @app.get("/protected")
        def protected_route(user: Profile = Depends(get_current_user)):
            return {"user_id": str(user.id), "email": user.email}
    """
    token = credentials.credentials
    
    try:
        # Verify token with Supabase
        user_response = supabase.auth.get_user(token)
        
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        auth_user = user_response.user
        
        # Get or create profile in database
        profile = db.query(Profile).filter(Profile.id == auth_user.id).first()
        
        if not profile:
            # Create profile if doesn't exist (first login)
            profile = Profile(
                id=auth_user.id,
                email=auth_user.email,
                full_name=auth_user.user_metadata.get("full_name"),
                avatar_url=auth_user.user_metadata.get("avatar_url"),
                provider=auth_user.app_metadata.get("provider", "email")
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)
        
        return profile
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db)
) -> Optional[Profile]:
    """
    Get current user if authenticated, None otherwise.
    Use for endpoints that work both with and without authentication.
    
    Usage:
        @app.get("/public-or-private")
        def route(user: Optional[Profile] = Depends(get_optional_user)):
            if user:
                return {"message": f"Hello {user.email}"}
            return {"message": "Hello anonymous"}
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
