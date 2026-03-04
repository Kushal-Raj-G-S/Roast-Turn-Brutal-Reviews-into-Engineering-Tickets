"""
Resource Metrics Tracker

Lightweight CPU and memory monitoring for migration decisions.
Tracks processing efficiency without heavy dependencies.
"""

import logging
import time
import psutil
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ResourceSnapshot:
    """Resource usage snapshot."""
    timestamp: float
    cpu_percent: float  # Total across all cores
    cpu_percent_per_core: float  # Normalized by core count
    memory_mb: float
    memory_percent: float
    num_cores: int


class ResourceTracker:
    """
    Lightweight resource monitoring.
    
    Tracks:
    - CPU usage
    - Memory usage
    - Processing latency
    
    No external dependencies beyond psutil.
    """
    
    def __init__(self):
        self.process = psutil.Process()
        self.start_snapshot: Optional[ResourceSnapshot] = None
        self.end_snapshot: Optional[ResourceSnapshot] = None
        self.start_time: float = 0
        self.end_time: float = 0
    
    def start(self):
        """Start tracking resources."""
        self.start_time = time.time()
        self.start_snapshot = self._take_snapshot()
        logger.debug(f"Resource tracking started: CPU={self.start_snapshot.cpu_percent:.1f}%, Memory={self.start_snapshot.memory_mb:.1f}MB")
    
    def stop(self):
        """Stop tracking resources."""
        self.end_time = time.time()
        self.end_snapshot = self._take_snapshot()
        logger.debug(f"Resource tracking stopped: CPU={self.end_snapshot.cpu_percent:.1f}%, Memory={self.end_snapshot.memory_mb:.1f}MB")
    
    def _take_snapshot(self) -> ResourceSnapshot:
        """Take current resource snapshot."""
        memory_info = self.process.memory_info()
        cpu_total = self.process.cpu_percent()
        num_cores = psutil.cpu_count()
        cpu_per_core = cpu_total / num_cores if num_cores > 0 else cpu_total
        
        return ResourceSnapshot(
            timestamp=time.time(),
            cpu_percent=cpu_total,
            cpu_percent_per_core=cpu_per_core,
            memory_mb=memory_info.rss / 1024 / 1024,
            memory_percent=self.process.memory_percent(),
            num_cores=num_cores
        )
    
    def get_summary(self) -> dict:
        """Get resource usage summary."""
        if not self.start_snapshot or not self.end_snapshot:
            return {}
        
        duration_s = self.end_time - self.start_time
        cpu_delta = self.end_snapshot.cpu_percent - self.start_snapshot.cpu_percent
        cpu_per_core_delta = self.end_snapshot.cpu_percent_per_core - self.start_snapshot.cpu_percent_per_core
        memory_delta_mb = self.end_snapshot.memory_mb - self.start_snapshot.memory_mb
        
        return {
            "duration_seconds": duration_s,
            "num_cores": self.end_snapshot.num_cores,
            "cpu_start_pct": self.start_snapshot.cpu_percent,
            "cpu_end_pct": self.end_snapshot.cpu_percent,
            "cpu_delta_pct": cpu_delta,
            "cpu_per_core_start_pct": self.start_snapshot.cpu_percent_per_core,
            "cpu_per_core_end_pct": self.end_snapshot.cpu_percent_per_core,
            "cpu_per_core_delta_pct": cpu_per_core_delta,
            "memory_start_mb": self.start_snapshot.memory_mb,
            "memory_end_mb": self.end_snapshot.memory_mb,
            "memory_delta_mb": memory_delta_mb,
            "memory_peak_mb": self.end_snapshot.memory_mb
        }
    
    def log_summary(self, log_prefix: str = ""):
        """Log resource usage summary.
        
        Args:
            log_prefix: Optional prefix for structured logging (e.g., "[v1:a3f2]")
        """
        summary = self.get_summary()
        if summary:
            # Show per-core CPU first (more intuitive), then context
            prefix = f"{log_prefix} " if log_prefix else ""
            logger.info(
                f"{prefix}📊 Resources: Duration={summary['duration_seconds']:.1f}s, "
                f"CPU={summary['cpu_per_core_end_pct']:.1f}% per-core ({summary['num_cores']} cores), "
                f"Memory={summary['memory_end_mb']:.1f}MB ({summary['memory_delta_mb']:+.1f}MB)"
            )


# Global instance for easy access
_global_tracker = ResourceTracker()


def start_tracking():
    """Start global resource tracking."""
    _global_tracker.start()


def stop_tracking():
    """Stop global resource tracking."""
    _global_tracker.stop()


def get_summary() -> dict:
    """Get global tracker summary."""
    return _global_tracker.get_summary()


def log_summary():
    """Log global tracker summary."""
    _global_tracker.log_summary()
