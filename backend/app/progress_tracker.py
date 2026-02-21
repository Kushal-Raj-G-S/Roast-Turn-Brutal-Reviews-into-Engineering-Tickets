"""
Progress Tracker for CSV Upload Processing
===========================================
Tracks progress and allows real-time updates via WebSocket
"""

from typing import Dict, Optional
from datetime import datetime
import asyncio


class ProgressTracker:
    """Track upload processing progress."""
    
    def __init__(self):
        self._progress: Dict[int, Dict] = {}  # upload_id -> progress data
        self._locks: Dict[int, asyncio.Lock] = {}
    
    def start_tracking(self, upload_id: int, total_reviews: int):
        """Start tracking progress for an upload."""
        self._progress[upload_id] = {
            "upload_id": upload_id,
            "status": "starting",
            "stage": "initializing",
            "progress": 0,
            "total": total_reviews,
            "current": 0,
            "message": "Preparing to process reviews...",
            "started_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        self._locks[upload_id] = asyncio.Lock()
    
    async def update(
        self,
        upload_id: int,
        stage: Optional[str] = None,
        current: Optional[int] = None,
        message: Optional[str] = None,
        status: Optional[str] = None
    ):
        """Update progress for an upload."""
        if upload_id not in self._progress:
            return
        
        async with self._locks.get(upload_id, asyncio.Lock()):
            progress_data = self._progress[upload_id]
            
            if stage:
                progress_data["stage"] = stage
            if current is not None:
                progress_data["current"] = current
                progress_data["progress"] = int((current / progress_data["total"]) * 100)
            if message:
                progress_data["message"] = message
            if status:
                progress_data["status"] = status
            
            progress_data["updated_at"] = datetime.utcnow().isoformat()
    
    def get_progress(self, upload_id: int) -> Optional[Dict]:
        """Get current progress for an upload."""
        return self._progress.get(upload_id)
    
    def complete(self, upload_id: int, success: bool = True, message: str = "Processing complete"):
        """Mark upload as complete."""
        if upload_id in self._progress:
            self._progress[upload_id].update({
                "status": "completed" if success else "failed",
                "stage": "done",
                "progress": 100 if success else self._progress[upload_id]["progress"],
                "message": message,
                "completed_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            })
    
    def cleanup(self, upload_id: int):
        """Remove progress tracking data (call after some time)."""
        if upload_id in self._progress:
            del self._progress[upload_id]
        if upload_id in self._locks:
            del self._locks[upload_id]


# Global progress tracker instance
progress_tracker = ProgressTracker()
