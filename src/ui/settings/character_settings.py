import os
import asyncio

from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

from gui_templates import create_settings_section
from ui.settings.prompt_catalogue_settings import list_prompt_sets
from utils.prompt_catalogue_manager import copy_prompt_set, get_prompt_catalogue_folder_name
from main_logger import logger
from utils import getTranslationVariant as _

def setup_mita_controls(gui, parent_layout):
    mita_config = [
        {'label': 'Персонажи', 'key': 'CHARACTER', 'type': 'combobox', 'options': gui.model.get_all_mitas(), 'default': "Crazy", 'widget_name': "character_combobox", 'command': lambda: change_character_actions(gui)},
        {'label': 'Набор промтов', 'key': 'PROMPT_SET', 'type': 'combobox', 'options': list_prompt_sets("PromptsCatalogue", gui.model.current_character.char_id), 'default': _("Выберите", "Choose"), 'widget_name': 'prompt_pack_combobox'},
        
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

    section = create_settings_section(gui, parent_layout, _("Настройки персонажей", "Characters settings"), mita_config)

    if hasattr(gui, 'prompt_pack_combobox'):
        gui.prompt_pack_combobox.currentTextChanged.connect(lambda: apply_prompt_set(gui))

    if hasattr(gui, 'character_combobox'):
        # Initial setup based on saved settings
        current_char = gui.settings.get("CHARACTER", "Crazy")
        change_character_actions(gui, current_char)

def set_default_prompt_pack(gui, combobox):
    character_name = gui.character_combobox.currentText()
    character_prompts_path = os.path.join("Prompts", character_name)
    folder_name = get_prompt_catalogue_folder_name(character_prompts_path)
    combobox.setCurrentText(folder_name)
    
def change_character_actions(gui, character=None):
    if character:
        selected_character = character
    elif hasattr(gui, 'character_combobox'):
        selected_character = gui.character_combobox.currentText()
    else:
        return

    gui.model.current_character_to_change = selected_character
    gui.model.check_change_current_character()

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
        apply_prompt_set(gui, force_apply=False) # Update prompts without confirmation dialog on char change

def apply_prompt_set(gui, force_apply=True):
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
            if hasattr(gui.model.current_character, 'reload_character_data'):
                gui.model.current_character.reload_character_data()
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
    if gui.model.current_character and gui.model.current_character.char_id:
        character_name = gui.model.current_character.char_id
        character_folder_path = os.path.join("Prompts", character_name)
        if os.path.exists(character_folder_path):
            open_folder(character_folder_path)
        else:
            QMessageBox.warning(gui, _("Внимание", "Warning"), _("Папка персонажа не найдена: ", "Character folder not found: ") + character_folder_path)
    else:
        QMessageBox.information(gui, _("Информация", "Information"), _("Персонаж не выбран или его имя недоступно.", "No character selected or its name is not available."))

def open_character_history_folder(gui):
    if gui.model.current_character and gui.model.current_character.char_id:
        character_name = gui.model.current_character.char_id
        history_folder_path = os.path.join("Histories", character_name)
        if os.path.exists(history_folder_path):
            open_folder(history_folder_path)
        else:
            QMessageBox.warning(gui, _("Внимание", "Warning"), _("Папка истории персонажа не найдена: ", "Character history folder not found: ") + history_folder_path)
    else:
        QMessageBox.information(gui, _("Информация", "Information"), _("Персонаж не выбран или его имя недоступно.", "No character selected or its name is not available."))

def clear_history(gui):
    gui.model.current_character.clear_history()
    gui.clear_chat_display()
    gui.update_debug_info()

def clear_history_all(gui):
    for character in gui.model.characters.values():
        character.clear_history()
    gui.clear_chat_display()
    gui.update_debug_info()

def reload_prompts(gui):
    reply = QMessageBox.question(gui, _("Подтверждение", "Confirmation"),
                                 _("Это удалит текущие промпты! Продолжить?", "This will delete the current prompts! Continue?"),
                                 QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    if reply == QMessageBox.StandardButton.Ok:
        gui._show_loading_popup(_("Загрузка промптов...", "Downloading prompts..."))
        if gui.loop and gui.loop.is_running():
            asyncio.run_coroutine_threadsafe(async_reload_prompts(gui), gui.loop)
        else:
            logger.error("Цикл событий asyncio не запущен. Невозможно выполнить асинхронную загрузку промптов.")
            QMessageBox.critical(gui, _("Ошибка", "Error"), _("Не удалось запустить асинхронную загрузку промптов.", "Failed to start asynchronous prompt download."))

async def async_reload_prompts(gui):
    try:
        from utils.prompt_downloader import PromptDownloader
        downloader = PromptDownloader()
        success = await gui.loop.run_in_executor(None, downloader.download_and_replace_prompts)
        if success:
            character = gui.model.characters.get(gui.model.current_character_to_change)
            if character:
                await gui.loop.run_in_executor(None, character.reload_prompts)
            else:
                logger.error("Персонаж для перезагрузки не найден")
            
            QMessageBox.information(gui, _("Успешно", "Success"), _("Промпты успешно скачаны и перезагружены.", "Prompts successfully downloaded and reloaded."))
        else:
            QMessageBox.critical(gui, _("Ошибка", "Error"), _("Не удалось скачать промпты с GitHub. Проверьте подключение к интернету.", "Failed to download prompts from GitHub. Check your internet connection."))
    except Exception as e:
        logger.error(f"Ошибка при обновлении промптов: {e}")
        QMessageBox.critical(gui, _("Ошибка", "Error"), _("Не удалось обновить промпты.", "Failed to update prompts."))
    finally:
        gui._close_loading_popup()