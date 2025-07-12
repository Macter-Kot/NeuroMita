from typing import Dict, List, Callable, Any
from dataclasses import dataclass
from enum import Enum, auto
import asyncio
from main_logger import logger

class EventType(Enum):
    # Audio events
    VOICE_TEXT_READY = auto()
    VOICEOVER_COMPLETED = auto()
    
    # Model events  
    MODEL_RESPONSE_READY = auto()
    MODEL_LOADING_STARTED = auto()
    MODEL_LOADING_COMPLETED = auto()
    
    # UI events
    USER_MESSAGE_SENT = auto()
    SCREEN_CAPTURE_REQUESTED = auto()
    
    # Connection events
    GAME_CONNECTED = auto()
    GAME_DISCONNECTED = auto()
    TELEGRAM_CONNECTED = auto()
    
    # System events
    SETTINGS_CHANGED = auto()
    APP_CLOSING = auto()

@dataclass
class Event:
    type: EventType
    data: Dict[str, Any]
    source: str = ""

class EventBus:
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._async_subscribers: Dict[EventType, List[Callable]] = {}
        self._event_queue = asyncio.Queue()
        
    def subscribe(self, event_type: EventType, handler: Callable, is_async: bool = False):
        """Подписаться на событие"""
        if is_async:
            if event_type not in self._async_subscribers:
                self._async_subscribers[event_type] = []
            self._async_subscribers[event_type].append(handler)
        else:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)
            
    def publish(self, event: Event):
        """Опубликовать событие синхронно"""
        logger.debug(f"Publishing event: {event.type} from {event.source}")
        
        # Синхронные обработчики
        for handler in self._subscribers.get(event.type, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler: {e}", exc_info=True)
                
    async def publish_async(self, event: Event):
        """Опубликовать событие асинхронно"""
        await self._event_queue.put(event)
        
    async def process_events(self):
        """Обработчик асинхронных событий"""
        while True:
            event = await self._event_queue.get()
            for handler in self._async_subscribers.get(event.type, []):
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(f"Error in async event handler: {e}", exc_info=True)