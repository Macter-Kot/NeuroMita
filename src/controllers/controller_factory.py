from typing import Any
from core.event_bus import EventBus
from managers.lifecycle_manager import LifecycleManager
from core.app_coordinator import AppCoordinator

class ControllerFactory:
    """Фабрика для создания контроллеров с внедрением зависимостей"""
    
    def __init__(self, event_bus: EventBus, lifecycle: LifecycleManager, coordinator: AppCoordinator):
        self.event_bus = event_bus
        self.lifecycle = lifecycle
        self.coordinator = coordinator
        
    def create_settings_controller(self):
        from controllers.settings_controller import SettingsController
        return SettingsController(self.event_bus, self.coordinator)
        
    def create_audio_controller(self):
        from controllers.audio_controller import AudioController
        settings = self.coordinator.get_controller("settings")
        return AudioController(self.event_bus, settings)
        
    # И так далее для остальных контроллеров...