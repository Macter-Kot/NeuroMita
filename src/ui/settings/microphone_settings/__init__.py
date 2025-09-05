from .ui import build_microphone_settings_ui
from .logic import wire_microphone_settings_logic, on_mic_selected, load_mic_settings

def setup_microphone_controls(self, parent_layout):
    """
    Собирает UI и подключает логику.
    self — это ваш MainView (или аналог), передаётся извне.
    parent_layout — QVBoxLayout контейнера для вкладки Микрофон.
    """
    build_microphone_settings_ui(self, parent_layout)
    wire_microphone_settings_logic(self)


__all__ = ["setup_microphone_controls", "on_mic_selected", "load_mic_settings"]