from main_logger import logger
from core.events import get_event_bus

class BaseController:
    def __init__(self, main_controller, view):
        self.main_controller = main_controller
        self.view = view
        self.event_bus = get_event_bus()
        self.subscribe_to_events()
        
    def subscribe_to_events(self):
        pass