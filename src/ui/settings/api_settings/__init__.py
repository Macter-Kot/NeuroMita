from .ui import build_api_settings_ui
from .logic import wire_api_settings_logic

def setup_api_controls(self, parent_layout):
    """
    Собирает UI и подключает логику.
    self — это ваш MainView (или аналог), передаётся извне.
    parent_layout — QVBoxLayout контейнера настроек для вкладки API.
    """
    build_api_settings_ui(self, parent_layout)
    wire_api_settings_logic(self)