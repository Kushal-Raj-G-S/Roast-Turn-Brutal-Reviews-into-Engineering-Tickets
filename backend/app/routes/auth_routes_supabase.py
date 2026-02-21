"""
Authentication routes using Supabase Auth.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.supabase_client import supabase
from app.schemas_supabase import (
    UserSignup,
    UserLogin,
    GoogleAuthCallback,
    TokenResponse,
    UserResponse
)
from app.auth_supabase import get_current_user
from app.models_supabase import Profile

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(user_data: UserSignup, db: Session = Depends(get_db)):
    """
    Register a new user with email and password using Supabase Auth.
    
    This automatically:
    - Creates user in auth.users table
    - Sends verification email (if enabled in Supabase)
    - Returns JWT access token and refresh token
    """
    try:
        # Sign up with Supabase Auth
        response = supabase.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password,
            "options": {
                "data": {
                    "full_name": user_data.full_name
                }
            }
        })
        
        if not response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user"
            )
        
        # Create profile in public.profiles table
        profile = Profile(
            id=response.user.id,
            email=response.user.email,
            full_name=user_data.full_name,
            provider="email"
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        
        return TokenResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            token_type="bearer",
            expires_in=response.session.expires_in,
            user=UserResponse(
                id=profile.id,
                email=profile.email,
                full_name=profile.full_name,
                avatar_url=profile.avatar_url,
                provider=profile.provider,
                created_at=profile.created_at
            )
        )
        
    except Exception as e:
        db.rollback()
        # Check if it's a duplicate email error
        if "already registered" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Signup failed: {str(e)}"
        )


@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin):
    """
    Login with email and password using Supabase Auth.
    
    Returns JWT access token and refresh token.
    """
    try:
        response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
        
        if not response.user or not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        return TokenResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            token_type="bearer",
            expires_in=response.session.expires_in,
            user=UserResponse(
                id=response.user.id,
                email=response.user.email,
                full_name=response.user.user_metadata.get("full_name"),
                avatar_url=response.user.user_metadata.get("avatar_url"),
                provider=response.user.app_metadata.get("provider", "email"),
                created_at=response.user.created_at
            )
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Login failed: {str(e)}"
        )


@router.post("/google", response_model=TokenResponse)
def google_auth(callback_data: GoogleAuthCallback, db: Session = Depends(get_db)):
    """
    Authenticate with Google OAuth.
    
    Frontend should handle Google OAuth flow and send id_token here.
    """
    try:
        # Exchange Google ID token for Supabase session
        response = supabase.auth.sign_in_with_id_token({
            "provider": "google",
            "token": callback_data.id_token
        })
        
        if not response.user or not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google authentication failed"
            )
        
        # Get or create profile
        profile = db.query(Profile).filter(Profile.id == response.user.id).first()
        if not profile:
            profile = Profile(
                id=response.user.id,
                email=response.user.email,
                full_name=response.user.user_metadata.get("full_name"),
                avatar_url=response.user.user_metadata.get("avatar_url"),
                provider="google"
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)
        
        return TokenResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            token_type="bearer",
            expires_in=response.session.expires_in,
            user=UserResponse(
                id=profile.id,
                email=profile.email,
                full_name=profile.full_name,
                avatar_url=profile.avatar_url,
                provider=profile.provider,
                created_at=profile.created_at
            )
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google auth failed: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
def get_me(user: Profile = Depends(get_current_user)):
    """
    Get current authenticated user profile.
    
    Requires Authorization: Bearer <token> header.
    """
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        provider=user.provider,
        created_at=user.created_at
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(refresh_token: str):
    """
    Refresh access token using refresh token.
    """
    try:
        response = supabase.auth.refresh_session(refresh_token)
        
        if not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        return TokenResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            token_type="bearer",
            expires_in=response.session.expires_in,
            user=UserResponse(
                id=response.user.id,
                email=response.user.email,
                full_name=response.user.user_metadata.get("full_name"),
                avatar_url=response.user.user_metadata.get("avatar_url"),
                provider=response.user.app_metadata.get("provider", "email"),
                created_at=response.user.created_at
            )
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token refresh failed: {str(e)}"
        )


@router.post("/logout")
def logout():
    """
    Logout user (invalidate session).
    
    Note: With Supabase, logout is typically handled client-side.
    This endpoint is provided for consistency.
    """
    try:
        supabase.auth.sign_out()
        return {"message": "Successfully logged out"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Logout failed: {str(e)}"
        )
