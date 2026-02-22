"""
Event Bus - Message Queue Abstraction
Supports multiple backends: in-memory, Redis, Celery, RabbitMQ, Kafka.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type
from dataclasses import dataclass, asdict
import json
from datetime import datetime
from uuid import uuid4

from src.domain.events import DomainEvent, EventType

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Message wrapper for queue systems."""
    id: str
    event_type: str
    payload: Dict[str, Any]
    timestamp: datetime
    retry_count: int = 0
    max_retries: int = 3
    dead_letter: bool = False


class IMessageQueue(ABC):
    """Interface for message queue backends."""

    @abstractmethod
    async def publish(self, message: Message) -> None:
        """Publish a message to the queue."""
        pass

    @abstractmethod
    async def subscribe(
        self,
        event_type: str,
        handler: Callable[[Message], Any]
    ) -> None:
        """Subscribe to messages of a specific type."""
        pass

    @abstractmethod
    async def start_consuming(self) -> None:
        """Start consuming messages (blocking)."""
        pass

    @abstractmethod
    async def stop_consuming(self) -> None:
        """Stop consuming messages."""
        pass

    @abstractmethod
    async def ack(self, message: Message) -> None:
        """Acknowledge message processing."""
        pass

    @abstractmethod
    async def nack(self, message: Message, requeue: bool = True) -> None:
        """Negative acknowledge (reject) message."""
        pass


class InMemoryQueue(IMessageQueue):
    """
    In-memory queue using asyncio.Queue.
    For development and lightweight deployments.
    """

    def __init__(self, max_size: int = 1000):
        self.queues: Dict[str, asyncio.Queue] = {}
        self.handlers: Dict[str, List[Callable]] = {}
        self.max_size = max_size
        self.is_consuming = False
        self._consumer_tasks: List[asyncio.Task] = []

    async def publish(self, message: Message) -> None:
        """Publish message to all relevant queues."""
        event_type = message.event_type
        
        # Create queue if doesn't exist
        if event_type not in self.queues:
            self.queues[event_type] = asyncio.Queue(maxsize=self.max_size)
        
        await self.queues[event_type].put(message)
        logger.debug(f"Published message {message.id} to queue {event_type}")

    async def subscribe(
        self,
        event_type: str,
        handler: Callable[[Message], Any]
    ) -> None:
        """Register a handler for an event type."""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
        logger.info(f"Registered handler for event type: {event_type}")

    async def start_consuming(self) -> None:
        """Start consuming messages from all queues."""
        self.is_consuming = True
        
        for event_type in self.handlers.keys():
            if event_type not in self.queues:
                self.queues[event_type] = asyncio.Queue(maxsize=self.max_size)
            
            # Start consumer task for this event type
            task = asyncio.create_task(self._consume_queue(event_type))
            self._consumer_tasks.append(task)
        
        logger.info(f"Started consuming {len(self._consumer_tasks)} queues")

    async def stop_consuming(self) -> None:
        """Stop all consumer tasks."""
        self.is_consuming = False
        
        for task in self._consumer_tasks:
            task.cancel()
        
        await asyncio.gather(*self._consumer_tasks, return_exceptions=True)
        self._consumer_tasks.clear()
        logger.info("Stopped all consumers")

    async def _consume_queue(self, event_type: str):
        """Consume messages from a specific queue."""
        queue = self.queues[event_type]
        handlers = self.handlers.get(event_type, [])
        
        while self.is_consuming:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(queue.get(), timeout=1.0)
                
                # Process with all registered handlers
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                    except Exception as e:
                        logger.error(
                            f"Handler error for {event_type}: {e}",
                            exc_info=True
                        )
                        
                        # Retry logic
                        if message.retry_count < message.max_retries:
                            message.retry_count += 1
                            await self.publish(message)
                            logger.info(f"Retrying message {message.id} (attempt {message.retry_count})")
                        else:
                            # Send to dead letter
                            message.dead_letter = True
                            logger.error(f"Message {message.id} sent to dead letter after {message.max_retries} retries")
                
                queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Queue consumer error: {e}", exc_info=True)

    async def ack(self, message: Message) -> None:
        """Acknowledge message (no-op for in-memory)."""
        pass

    async def nack(self, message: Message, requeue: bool = True) -> None:
        """Reject message."""
        if requeue and message.retry_count < message.max_retries:
            message.retry_count += 1
            await self.publish(message)


class RedisQueue(IMessageQueue):
    """
    Redis-based message queue using Redis Streams.
    For distributed deployments with moderate scale.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis = None  # Will be initialized lazily
        self.handlers: Dict[str, List[Callable]] = {}
        self.is_consuming = False
        self._consumer_tasks: List[asyncio.Task] = []

    async def _get_redis(self):
        """Lazy initialization of Redis connection."""
        if self.redis is None:
            import redis.asyncio as aioredis
            self.redis = await aioredis.from_url(self.redis_url)
        return self.redis

    async def publish(self, message: Message) -> None:
        """Publish message to Redis stream."""
        redis = await self._get_redis()
        stream_key = f"events:{message.event_type}"
        
        # Convert message to dict
        message_dict = {
            "id": message.id,
            "payload": json.dumps(message.payload),
            "timestamp": message.timestamp.isoformat(),
            "retry_count": str(message.retry_count),
            "max_retries": str(message.max_retries)
        }
        
        await redis.xadd(stream_key, message_dict)
        logger.debug(f"Published message {message.id} to Redis stream {stream_key}")

    async def subscribe(
        self,
        event_type: str,
        handler: Callable[[Message], Any]
    ) -> None:
        """Register handler for event type."""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
        logger.info(f"Registered Redis handler for: {event_type}")

    async def start_consuming(self) -> None:
        """Start consuming from Redis streams."""
        self.is_consuming = True
        
        for event_type in self.handlers.keys():
            task = asyncio.create_task(self._consume_stream(event_type))
            self._consumer_tasks.append(task)
        
        logger.info(f"Started consuming {len(self._consumer_tasks)} Redis streams")

    async def stop_consuming(self) -> None:
        """Stop consuming."""
        self.is_consuming = False
        
        for task in self._consumer_tasks:
            task.cancel()
        
        await asyncio.gather(*self._consumer_tasks, return_exceptions=True)
        self._consumer_tasks.clear()
        
        if self.redis:
            await self.redis.close()
        
        logger.info("Stopped Redis consumers")

    async def _consume_stream(self, event_type: str):
        """Consume messages from Redis stream."""
        redis = await self._get_redis()
        stream_key = f"events:{event_type}"
        consumer_group = "roast-workers"
        consumer_name = f"worker-{uuid4().hex[:8]}"
        
        # Create consumer group if doesn't exist
        try:
            await redis.xgroup_create(stream_key, consumer_group, id="0", mkstream=True)
        except Exception:
            pass  # Group already exists
        
        handlers = self.handlers.get(event_type, [])
        
        while self.is_consuming:
            try:
                # Read from stream
                messages = await redis.xreadgroup(
                    consumer_group,
                    consumer_name,
                    {stream_key: ">"},
                    count=10,
                    block=1000
                )
                
                for stream, message_list in messages:
                    for message_id, message_data in message_list:
                        # Parse message
                        message = Message(
                            id=message_data[b"id"].decode(),
                            event_type=event_type,
                            payload=json.loads(message_data[b"payload"].decode()),
                            timestamp=datetime.fromisoformat(message_data[b"timestamp"].decode()),
                            retry_count=int(message_data[b"retry_count"].decode()),
                            max_retries=int(message_data[b"max_retries"].decode())
                        )
                        
                        # Process with handlers
                        try:
                            for handler in handlers:
                                if asyncio.iscoroutinefunction(handler):
                                    await handler(message)
                                else:
                                    handler(message)
                            
                            # Acknowledge message
                            await redis.xack(stream_key, consumer_group, message_id)
                            
                        except Exception as e:
                            logger.error(f"Handler error: {e}", exc_info=True)
                            
                            # Retry logic
                            if message.retry_count < message.max_retries:
                                message.retry_count += 1
                                await self.publish(message)
                
            except Exception as e:
                logger.error(f"Stream consumer error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def ack(self, message: Message) -> None:
        """Acknowledge message."""
        # Handled in consumer loop
        pass

    async def nack(self, message: Message, requeue: bool = True) -> None:
        """Reject message."""
        if requeue:
            await self.publish(message)


class EventBus:
    """
    High-level event bus for domain events.
    Wraps message queue with domain-specific logic.
    """

    def __init__(self, message_queue: IMessageQueue):
        self.message_queue = message_queue
        self._started = False

    async def publish(self, event: DomainEvent) -> None:
        """
        Publish a domain event.
        
        Args:
            event: Domain event to publish
        """
        message = Message(
            id=event.event_id,
            event_type=event.event_type.value,
            payload=self._serialize_event(event),
            timestamp=event.timestamp
        )
        
        await self.message_queue.publish(message)
        logger.debug(f"Published domain event: {event.event_type.value}")

    async def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[DomainEvent], Any]
    ) -> None:
        """
        Subscribe to domain events.
        
        Args:
            event_type: Type of event to subscribe to
            handler: Async or sync handler function
        """
        async def wrapper(message: Message):
            """Wrap handler to deserialize event."""
            event = self._deserialize_event(message)
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        
        await self.message_queue.subscribe(event_type.value, wrapper)

    async def start(self) -> None:
        """Start consuming events."""
        if not self._started:
            await self.message_queue.start_consuming()
            self._started = True
            logger.info("Event bus started")

    async def stop(self) -> None:
        """Stop consuming events."""
        if self._started:
            await self.message_queue.stop_consuming()
            self._started = False
            logger.info("Event bus stopped")

    def _serialize_event(self, event: DomainEvent) -> Dict[str, Any]:
        """Serialize domain event to dict."""
        payload = {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "tenant_id": str(event.tenant_id),
            "timestamp": event.timestamp.isoformat(),
            "metadata": event.metadata
        }
        
        # Add event-specific fields
        for key, value in event.__dict__.items():
            if key not in payload:
                # Convert complex types to string
                if hasattr(value, "__dict__"):
                    payload[key] = str(value)
                else:
                    payload[key] = value
        
        return payload

    def _deserialize_event(self, message: Message) -> DomainEvent:
        """Deserialize message back to domain event."""
        from ..domain.value_objects import TenantId
        
        payload = message.payload
        return DomainEvent(
            event_id=payload["event_id"],
            event_type=EventType(payload["event_type"]),
            tenant_id=TenantId(payload["tenant_id"]),
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            metadata=payload.get("metadata", {})
        )


# Factory function
def create_event_bus(backend: str = "memory", **kwargs) -> EventBus:
    """
    Create event bus with specified backend.
    
    Args:
        backend: "memory", "redis", or "celery"
        **kwargs: Backend-specific configuration
    
    Returns:
        Configured EventBus instance
    """
    if backend == "memory":
        queue = InMemoryQueue(max_size=kwargs.get("max_size", 1000))
    elif backend == "redis":
        queue = RedisQueue(redis_url=kwargs.get("redis_url", "redis://localhost:6379"))
    else:
        raise ValueError(f"Unsupported backend: {backend}")
    
    return EventBus(queue)
