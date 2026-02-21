"""
Pydantic schemas for Supabase authentication.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


# =============================================================================
# AUTH SCHEMAS
# =============================================================================

class UserSignup(BaseModel):
    """User registration with email/password."""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    """User login credentials."""
    email: EmailStr
    password: str


class GoogleAuthCallback(BaseModel):
    """Google OAuth callback data."""
    id_token: str


class TokenResponse(BaseModel):
    """Authentication response with tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserResponse"


class UserResponse(BaseModel):
    """User profile data."""
    id: UUID
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    provider: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# =============================================================================
# UPLOAD SCHEMAS
# =============================================================================

class UploadResponse(BaseModel):
    """CSV upload response."""
    id: int
    user_id: UUID
    filename: str
    file_size_bytes: Optional[int] = None
    total_reviews: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    processed_reviews: Optional[int] = None
    filtered_noise: Optional[int] = None
    clusters_created: Optional[int] = None
    ai_analyzed_count: Optional[int] = None
    processing_time_ms: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# =============================================================================
# CLUSTER SCHEMAS
# =============================================================================

class ClusterResponse(BaseModel):
    """Cluster summary response."""
    id: int
    cluster_uuid: str
    title: str
    severity: str
    status: str
    review_count: Optional[int] = None
    assigned_to: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ClusterDetailResponse(BaseModel):
    """Detailed cluster with RCA."""
    id: int
    cluster_uuid: str
    title: str
    severity: str
    status: str
    rca_title: Optional[str] = None
    rca_hypothesis: Optional[str] = None
    rca_steps: Optional[str] = None
    rca_fix: Optional[str] = None
    ai_analyzed: Optional[bool] = None
    affected_versions: Optional[List[str]] = None
    affected_devices: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    review_count: Optional[int] = None
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ReviewResponse(BaseModel):
    """Review data."""
    id: int
    original_text: str
    rating: Optional[int] = None
    version: Optional[str] = None
    device: Optional[str] = None
    review_date: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
