import os
import asyncio

from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

from presets.api_presets import API_PRESETS
from ui.gui_templates import create_settings_direct
from ui.settings.prompt_catalogue_settings import list_prompt_sets
from managers.prompt_catalogue_manager import copy_prompt_set, get_prompt_catalogue_folder_name
from main_logger import logger
from utils import getTranslationVariant as _
from core.events import get_event_bus, Events

def setup_mita_controls(gui, parent_layout):
    event_bus = get_event_bus()
    
    # Получаем список персонажей через события
    all_characters = event_bus.emit_and_wait(Events.GET_ALL_CHARACTERS, timeout=1.0)
    character_list = all_characters[0] if all_characters else ["Crazy"]

    provider_names = list(API_PRESETS.keys()) + ['Custom', 'Google AI Studio', 'ProxiApi'] + list(gui.settings.get("CUSTOM_API_PRESETS", {}).keys())
    provider_names = list(dict.fromkeys(provider_names))
    provider_names.insert(0, _("Текущий", "Current"))

    # Получаем текущего персонажа для начальной настройки
    current_char_data = event_bus.emit_and_wait(Events.GET_CURRENT_CHARACTER, timeout=1.0)
    current_char_id = current_char_data[0]['char_id'] if current_char_data and current_char_data[0] else "Crazy"

    mita_config = [
        {'label': 'Персонажи', 'key': 'CHARACTER', 'type': 'combobox', 'options': character_list, 'default': "Crazy", 'widget_name': "character_combobox", 'command': lambda: change_character_actions(gui)},
        {'label': 'Набор промтов', 'key': 'PROMPT_SET', 'type': 'combobox', 'options': list_prompt_sets("PromptsCatalogue", current_char_id), 'default': _("Выберите", "Choose"), 'widget_name': 'prompt_pack_combobox'},
        {'label': _('Провайдер для персонажа', 'Provider for character'),
         'key': 'CHAR_PROVIDER', 'type': 'combobox',
         'options': provider_names,
         'default': _("Текущий", "Current"),
         'widget_name': 'char_provider_combobox'},

        {'label': 'Управление персонажем', 'type': 'text'},
        {'type': 'button_group', 'buttons': [
            {'label': 'Открыть папку персонажа', 'command': lambda: open_character_folder(gui)},
            {'label': 'Папку истории', 'command': lambda: open_character_history_folder(gui)},
        ]},
        
        {'label': 'Аккуратно!', 'type': 'text'},
        {'type': 'button_group', 'buttons': [
            {'label': 'Очистить историю', 'command': lambda: clear_history(gui)},
            {'label': 'Очистить все истории', 'command': lambda: clear_history_all(gui)}
        ]},
        {'label': 'Перекачать промпты', 'type': 'button', 'command': lambda: reload_prompts(gui)},
        
        {'label': 'Экспериментальные функции', 'type': 'text'},
        {'label': 'Меню выбора Мит', 'key': 'MITAS_MENU', 'type': 'checkbutton', 'default_checkbutton': False},
        {'label': 'Меню эмоций Мит', 'key': 'EMOTION_MENU', 'type': 'checkbutton', 'default_checkbutton': False},
    ]

    create_settings_direct(gui, parent_layout, mita_config, 
                          title=_("Настройки персонажей", "Characters settings"))

    if hasattr(gui, 'prompt_pack_combobox'):
        gui.prompt_pack_combobox.currentTextChanged.connect(lambda: apply_prompt_set(gui))

    if hasattr(gui, 'character_combobox'):
        current_char = gui.settings.get("CHARACTER", "Crazy")
        change_character_actions(gui, current_char)

    if hasattr(gui, 'char_provider_combobox'):
        gui.char_provider_combobox.currentTextChanged.connect(lambda text: save_character_provider(gui, text))

def set_default_prompt_pack(gui, combobox):
    character_name = gui.character_combobox.currentText()
    character_prompts_path = os.path.join("Prompts", character_name)
    folder_name = get_prompt_catalogue_folder_name(character_prompts_path)
    combobox.setCurrentText(folder_name)
    
def change_character_actions(gui, character=None):
    event_bus = get_event_bus()
    
    if character:
        selected_character = character
    elif hasattr(gui, 'character_combobox'):
        selected_character = gui.character_combobox.currentText()
    else:
        return

    event_bus.emit(Events.SET_CHARACTER_TO_CHANGE, {'character': selected_character})
    event_bus.emit(Events.CHECK_CHANGE_CHARACTER)

    if hasattr(gui, 'char_provider_combobox'):
        provider_key = f"CHAR_PROVIDER_{selected_character}"
        current_provider = gui.settings.get(provider_key, _("Текущий", "Current"))
        gui.char_provider_combobox.blockSignals(True)
        gui.char_provider_combobox.setCurrentText(current_provider)
        gui.char_provider_combobox.blockSignals(False)

    if not selected_character:
        QMessageBox.warning(gui, _("Внимание", "Warning"), _("Персонаж не выбран.", "No character selected."))
        return

    if hasattr(gui, 'prompt_pack_combobox'):
        new_options = list_prompt_sets("PromptsCatalogue", selected_character)
        gui.prompt_pack_combobox.blockSignals(True)
        gui.prompt_pack_combobox.clear()
        gui.prompt_pack_combobox.addItems(new_options)
        set_default_prompt_pack(gui, gui.prompt_pack_combobox)
        gui.prompt_pack_combobox.blockSignals(False)
        apply_prompt_set(gui, force_apply=False)

def apply_prompt_set(gui, force_apply=True):
    event_bus = get_event_bus()
    
    chat_to = gui.prompt_pack_combobox.currentText()
    char_from = gui.character_combobox.currentText()
    if not chat_to:
        if force_apply:
            QMessageBox.warning(gui, _("Внимание", "Warning"), _("Набор промптов не выбран.", "No prompt set selected."))
        return

    if force_apply:
        reply = QMessageBox.question(gui, _("Подтверждение", "Confirmation"),
                                     _("Применить набор промптов?", "Apply prompt set?"),
                                     QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Cancel:
            set_default_prompt_pack(gui, gui.prompt_pack_combobox)
            return

    catalogue_path = "PromptsCatalogue"
    set_path = os.path.join(catalogue_path, chat_to)

    if char_from:
        character_prompts_path = os.path.join("Prompts", char_from)
        if copy_prompt_set(set_path, character_prompts_path):
            if force_apply:
                QMessageBox.information(gui, _("Успех", "Success"), _("Набор промптов успешно применен.", "Prompt set applied successfully."))
            event_bus.emit(Events.RELOAD_CHARACTER_DATA)
        else:
            if force_apply:
                QMessageBox.critical(gui, _("Ошибка", "Error"), _("Не удалось применить набор промптов.", "Failed to apply prompt set."))
    else:
        if force_apply:
            QMessageBox.warning(gui, _("Внимание", "Warning"), _("Персонаж не выбран.", "No character selected."))

def open_folder(path):
    if not os.path.exists(path):
        logger.error(f"Path does not exist: {path}")
        return
    url = QUrl.fromLocalFile(os.path.abspath(path))
    QDesktopServices.openUrl(url)

def open_character_folder(gui):
    event_bus = get_event_bus()
    current_char_data = event_bus.emit_and_wait(Events.GET_CURRENT_CHARACTER, timeout=1.0)
    
    if current_char_data and current_char_data[0]:
        char_data = current_char_data[0]
        character_name = char_data.get('char_id')
        if character_name:
            character_folder_path = os.path.join("Prompts", character_name)
            if os.path.exists(character_folder_path):
                open_folder(character_folder_path)
            else:
                QMessageBox.warning(gui, _("Внимание", "Warning"), _("Папка персонажа не найдена: ", "Character folder not found: ") + character_folder_path)
        else:
            QMessageBox.information(gui, _("Информация", "Information"), _("Персонаж не выбран или его имя недоступно.", "No character selected or its name is not available."))
    else:
        QMessageBox.information(gui, _("Информация", "Information"), _("Персонаж не выбран или его имя недоступно.", "No character selected or its name is not available."))

def open_character_history_folder(gui):
    event_bus = get_event_bus()
    current_char_data = event_bus.emit_and_wait(Events.GET_CURRENT_CHARACTER, timeout=1.0)
    
    if current_char_data and current_char_data[0]:
        char_data = current_char_data[0]
        character_name = char_data.get('char_id')
        if character_name:
            history_folder_path = os.path.join("Histories", character_name)
            if os.path.exists(history_folder_path):
                open_folder(history_folder_path)
            else:
                QMessageBox.warning(gui, _("Внимание", "Warning"), _("Папка истории персонажа не найдена: ", "Character history folder not found: ") + history_folder_path)
        else:
            QMessageBox.information(gui, _("Информация", "Information"), _("Персонаж не выбран или его имя недоступно.", "No character selected or its name is not available."))
    else:
        QMessageBox.information(gui, _("Информация", "Information"), _("Персонаж не выбран или его имя недоступно.", "No character selected or its name is not available."))

def clear_history(gui):
    event_bus = get_event_bus()
    event_bus.emit(Events.CLEAR_CHARACTER_HISTORY)
    gui.clear_chat_display()
    gui.update_debug_info()

def clear_history_all(gui):
    event_bus = get_event_bus()
    event_bus.emit(Events.CLEAR_ALL_HISTORIES)
    gui.clear_chat_display()
    gui.update_debug_info()

def reload_prompts(gui):
    reply = QMessageBox.question(gui, _("Подтверждение", "Confirmation"),
                                 _("Это удалит текущие промпты! Продолжить?", "This will delete the current prompts! Continue?"),
                                 QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    if reply == QMessageBox.StandardButton.Ok:
        gui._show_loading_popup(_("Загрузка промптов...", "Downloading prompts..."))
        
        event_bus = get_event_bus()
        event_bus.emit(Events.RELOAD_PROMPTS_ASYNC)

def save_character_provider(gui, provider: str):
    event_bus = get_event_bus()
    
    selected_character = gui.character_combobox.currentText() if hasattr(gui, 'character_combobox') else None
    if not selected_character:
        QMessageBox.warning(gui, _("Внимание", "Warning"), _("Персонаж не выбран.", "No character selected."))
        return
    provider_key = f"CHAR_PROVIDER_{selected_character}"
    gui.settings.set(provider_key, provider)
    logger.info(f"Saved provider '{provider}' for character '{selected_character}'")
    event_bus.emit(Events.CHECK_CHANGE_CHARACTER)