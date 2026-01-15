"""
Roast Schemas - Pydantic V2 Data Models
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TicketStatus(str, Enum):
    """Kanban workflow status."""
    FRESH_ROAST = "fresh_roast"
    FIXING = "fixing"
    DONE = "done"


class Severity(str, Enum):
    """Issue severity level."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RoastReview(BaseModel):
    """A single user review (complaint)."""
    id: UUID = Field(default_factory=uuid4)
    original_text: str
    rating: int
    version: Optional[str] = None  # e.g., 'v2.4'
    device: Optional[str] = None   # e.g., 'Pixel 7'
    sentiment: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RoastCluster(BaseModel):
    """A cluster of similar roasts - becomes a ticket."""
    id: UUID = Field(default_factory=uuid4)
    title: str
    status: TicketStatus = TicketStatus.FRESH_ROAST
    severity: Severity = Severity.MEDIUM
    evidence: list[RoastReview] = Field(default_factory=list)
    
    # RCA (Root Cause Analysis) fields - populated by LLM
    rca_title: Optional[str] = Field(default=None, description="AI-generated ticket title")
    rca_hypothesis: Optional[str] = Field(default=None, description="AI root cause hypothesis")
    rca_steps: list[str] = Field(default_factory=list, description="AI reproduction steps")
    rca_fix: Optional[str] = Field(default=None, description="AI suggested fix")
    ai_analyzed: bool = Field(default=False, description="Whether AI analysis completed")


class IngestStats(BaseModel):
    """Stats returned after CSV processing."""
    processed: int = 0
    merged: int = 0
    new_issues: int = 0
    ai_analyzed: int = 0
    ai_failed: int = 0
    processing_time_ms: float = 0.0
