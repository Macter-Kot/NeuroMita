from .ui import build_prompt_catalogue_ui
from .logic import wire_prompt_catalogue_logic

# re-export, чтобы сохранилась совместимость:
# from ui.settings.prompt_catalogue_settings import list_prompt_sets
from managers.prompt_catalogue_manager import list_prompt_sets

def setup_prompt_catalogue_controls(self, parent_layout):
    """
    Собирает UI и подключает логику.
    self — это ваш MainView (или аналог), передаётся извне.
    parent_layout — QVBoxLayout контейнера для вкладки Каталога промптов.
    """
    build_prompt_catalogue_ui(self, parent_layout)
    wire_prompt_catalogue_logic(self)

__all__ = ["setup_prompt_catalogue_controls", "list_prompt_sets"]