"""
Process-wide EventBus provider.

BulkProcessingPipeline already publishes domain events at every stage
(UploadStageCompletedEvent, UploadCompletedEvent, ClusterCreatedEvent —
see src/domain/events.py), but every call site passed event_bus=None, so
those publishes were dead code and the Kafka backend was never actually
exercised. This module is the missing piece: one bus per process, built
from config, injected wherever the pipeline is constructed.

The bus is a singleton because the Kafka producer holds TCP connections
and an internal batching buffer — constructing one per request would
defeat batching and leak sockets.
"""

import asyncio
import logging
from typing import Optional

from .event_bus import EventBus, create_event_bus

logger = logging.getLogger(__name__)

_bus: Optional[EventBus] = None
_lock = asyncio.Lock()


async def get_event_bus() -> EventBus:
    """
    Return the process-wide EventBus, constructing it on first use from
    Config.EVENT_BUS_BACKEND ("memory" | "redis" | "kafka").
    """
    global _bus
    if _bus is None:
        async with _lock:
            if _bus is None:  # re-check inside the lock
                from app.core.config import config

                backend = config.EVENT_BUS_BACKEND
                _bus = create_event_bus(backend, **config.event_bus_kwargs())
                logger.info(f"EventBus initialized with backend={backend}")
    return _bus


async def shutdown_event_bus() -> None:
    """
    Flush and close the bus. Must be called on app shutdown — an
    un-stopped Kafka producer can drop messages still sitting in its
    linger buffer.
    """
    global _bus
    if _bus is not None:
        await _bus.stop()
        _bus = None
        logger.info("EventBus shut down")
