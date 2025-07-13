from typing import Dict, Optional, Any
from core.event_bus import EventBus, Event, EventType
from core.lifecycle_manager import LifecycleManager
from main_logger import logger

class AppCoordinator:
    """Координирует взаимодействие между контроллерами через события"""
    
    def __init__(self, event_bus: EventBus, lifecycle_manager: LifecycleManager):
        self.event_bus = event_bus
        self.lifecycle = lifecycle_manager
        self.controllers: Dict[str, Any] = {}
        
        # Подписываемся на системные события
        self.event_bus.subscribe(EventType.APP_CLOSING, self._handle_app_closing)
        self.event_bus.subscribe(EventType.SETTINGS_CHANGED, self._handle_settings_changed)
        
    def register_controller(self, name: str, controller: Any):
        """Регистрация контроллера"""
        self.controllers[name] = controller
        logger.info(f"Registered controller: {name}")
        
    def get_controller(self, name: str) -> Optional[Any]:
        """Получить контроллер по имени"""
        return self.controllers.get(name)
        
    def _handle_app_closing(self, event: Event):
        """Обработка закрытия приложения"""
        logger.info("Coordinator handling app closing...")
        # Каждый контроллер сам подписан на это событие и выполнит cleanup
        
    def _handle_settings_changed(self, event: Event):
        """Обработка изменения настроек"""
        setting_key = event.data.get("key")
        setting_value = event.data.get("value")
        logger.debug(f"Settings changed: {setting_key} = {setting_value}")