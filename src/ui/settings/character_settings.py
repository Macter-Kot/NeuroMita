import os
import asyncio
import hashlib

from PyQt6.QtWidgets import QMessageBox, QLabel
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

from ui.gui_templates import create_settings_direct
from ui.settings.prompt_catalogue_settings import list_prompt_sets
from managers.prompt_catalogue_manager import copy_prompt_set, get_prompt_catalogue_folder_name
from main_logger import logger
from utils import getTranslationVariant as _
from core.events import get_event_bus, Events


# ─── Вспомогательные функции ────────────────────────────────────────────────
def _prompt_set_key(char_name: str) -> str:
    """Ключ Settings для конкретного персонажа"""
    return f"PROMPT_SET_{char_name}"

def _dir_file_hashes(folder: str, exclude=None) -> dict:
    """Возвращает словарь {relative_path: sha256} по всем файлам в папке.
    Исключаем info.json, системный мусор и всё, что передано в exclude.
    """
    result = {}
    if not os.path.isdir(folder):
        return result

    base_exclude = {"info.json", ".DS_Store", "Thumbs.db", "desktop.ini"}
    if exclude:
        base_exclude |= set(exclude)

    for root, dirnames, files in os.walk(folder):
        dirnames.sort()
        for f in sorted(files):
            if f in base_exclude:
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, folder).replace(os.sep, "/")

            sha = hashlib.sha256()
            try:
                with open(path, "rb") as fp:
                    for chunk in iter(lambda: fp.read(8192), b""):
                        sha.update(chunk)
                result[rel] = sha.hexdigest()
            except Exception as e:
                logger.warning(f"Не удалось прочитать файл {path}: {e}")

    return result

def _prompts_match(char_name: str, set_name: str, gui=None) -> bool:
    """True, если состав и содержимое файлов в Prompts/<char> совпадают с PromptsCatalogue/<set> (пофайлово).
    Особый случай: если в наборе НЕТ config.json, игнорируем наличие/содержимое config.json в Prompts/<char>.
    Если в наборе ЕСТЬ config.json — он заменяет существующий и должен совпадать.
    Логи-уведомления (logger.notify) выводятся только если включён чекбокс SHOW_PROMPT_SYNC_LOGS.
    """
    # Локальный флажок показа логов
    show_logs = False
    try:
        if gui and hasattr(gui, "settings"):
            show_logs = bool(gui.settings.get("SHOW_PROMPT_SYNC_LOGS", False))
    except Exception:
        show_logs = False

    def notify(msg: str):
        if show_logs:
            try:
                logger.notify(msg)
            except Exception:
                logger.info(msg)

    if not char_name or not set_name:
        return False

    char_dir = os.path.join("Prompts", char_name)
    set_dir = os.path.join("PromptsCatalogue", set_name)

    if not os.path.isdir(char_dir) or not os.path.isdir(set_dir):
        parts = []
        if not os.path.isdir(char_dir):
            parts.append(f"нет папки персонажа: {os.path.abspath(char_dir)}")
        if not os.path.isdir(set_dir):
            parts.append(f"нет папки набора: {os.path.abspath(set_dir)}")
        notify("Промпты отличаются: " + "; ".join(parts))
        return False

    # Считаем хеши пофайлово
    char_hashes = _dir_file_hashes(char_dir)
    set_hashes = _dir_file_hashes(set_dir)

    # Если в наборе нет config.json — игнорируем его в папке персонажа
    if "config.json" not in set_hashes:
        char_hashes.pop("config.json", None)

    char_keys = set(char_hashes.keys())
    set_keys = set(set_hashes.keys())

    # Состав файлов (пути) должен совпадать
    if char_keys != set_keys:
        missing_in_char = sorted(set_keys - char_keys)
        extra_in_char = sorted(char_keys - set_keys)

        lines = ["Промпты отличаются: состав файлов не совпадает."]
        if missing_in_char:
            lines.append("Отсутствуют в Prompts/<char> (есть в наборе):")
            lines += [f"  - {p}" for p in missing_in_char]
        if extra_in_char:
            lines.append("Лишние в Prompts/<char> (нет в наборе):")
            lines += [f"  - {p}" for p in extra_in_char]
        notify("\n".join(lines))
        return False

    # Содержимое совпадает?
    diffs = []
    for rel in sorted(char_keys):
        if char_hashes[rel] != set_hashes[rel]:
            diffs.append((rel, char_hashes[rel], set_hashes[rel]))

    if diffs:
        lines = ["Следующие файлы по хешу не совпадают:"]
        lines += [f"- {rel}: char={h1}, set={h2}" for rel, h1, h2 in diffs]
        notify("\n".join(lines))
        return False

    return True

def _update_sync_indicator(gui):
    """Красим точку индикатора (создаём при первом вызове)"""
    if not hasattr(gui, "prompt_sync_label"):
        gui.prompt_sync_label = QLabel("●")  # маленькая точка
        gui.prompt_sync_label.setToolTip(_("Индикатор соответствия промптов", "Prompts sync indicator"))
        
        # Вставляем рядом с combobox
        if hasattr(gui, 'prompt_pack_combobox'):
            parent = gui.prompt_pack_combobox.parent()
            if parent and parent.layout():
                parent.layout().addWidget(gui.prompt_sync_label)
    
    if not hasattr(gui, 'character_combobox') or not hasattr(gui, 'prompt_pack_combobox'):
        return
    
    char_name = gui.character_combobox.currentText()
    set_name = gui.prompt_pack_combobox.currentText()
    
    ok = _prompts_match(char_name, set_name, gui=gui)
    color = "#2ecc71" if ok else "#e74c3c"  # зелёный / красный
    gui.prompt_sync_label.setStyleSheet(f"color: {color}; font-size: 16px;")
    
    tooltip = _("Промпты синхронизированы", "Prompts are synchronized") if ok else _(
        "Промпты отличаются от выбранного набора", "Prompts differ from selected set")
    gui.prompt_sync_label.setToolTip(tooltip)

def setup_mita_controls(gui, parent_layout):
    event_bus = get_event_bus()
    
    all_characters = event_bus.emit_and_wait(Events.Model.GET_ALL_CHARACTERS, timeout=1.0)
    character_list = all_characters[0] if all_characters else ["Crazy"]

    presets_meta = event_bus.emit_and_wait(Events.ApiPresets.GET_PRESET_LIST, timeout=1.0)
    provider_names = [_("Текущий", "Current")]
    if presets_meta and presets_meta[0]:
        all_presets = presets_meta[0].get('custom', [])
        for preset in all_presets:
            provider_names.append(preset.name)

    current_char_data = event_bus.emit_and_wait(Events.Model.GET_CURRENT_CHARACTER, timeout=1.0)
    current_char_id = current_char_data[0]['char_id'] if current_char_data and current_char_data[0] else "Crazy"

    mita_config = [
        {'label': 'Персонажи', 'key': 'CHARACTER', 'type': 'combobox', 'options': character_list, 
         'default': "Crazy", 'widget_name': "character_combobox", 
         'command': lambda: change_character_actions(gui)},
        {'label': 'Набор промтов', 'type': 'combobox',  # без 'key'
         'options': list_prompt_sets("PromptsCatalogue", current_char_id), 
         'default': _("Выберите", "Choose"), 'widget_name': 'prompt_pack_combobox'},
        {'label': _('Провайдер для персонажа', 'Provider for character'),
         'key': 'CHAR_PROVIDER', 'type': 'combobox',
         'options': provider_names,
         'default': _("Текущий", "Current"),
         'widget_name': 'char_provider_combobox'},
        {'label': _('Показывать логи сравнения промптов', 'Show prompt comparison logs'),
         'key': 'SHOW_PROMPT_SYNC_LOGS',
         'type': 'checkbutton',
         'default_checkbutton': False,
         'widget_name': 'show_prompt_sync_logs_check',
         'tooltip': _('Отображать уведомления logger.notify при сравнении промптов',
                      'Show logger.notify notifications during prompt comparison')},

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
    ]

    create_settings_direct(gui, parent_layout, mita_config, 
                          title=_("Настройки персонажей", "Characters settings"))

    if hasattr(gui, 'prompt_pack_combobox'):
        gui.prompt_pack_combobox.currentTextChanged.connect(lambda: on_prompt_set_changed(gui))

    if hasattr(gui, 'character_combobox'):
        current_char = gui.settings.get("CHARACTER", "Crazy")
        change_character_actions(gui, current_char)

    if hasattr(gui, 'char_provider_combobox'):
        gui.char_provider_combobox.currentTextChanged.connect(lambda text: save_character_provider(gui, text))
        
def on_prompt_set_changed(gui):
    """Обработчик изменения выбранного набора промптов"""
    _update_sync_indicator(gui)
    
    if not hasattr(gui, 'character_combobox') or not hasattr(gui, 'prompt_pack_combobox'):
        return
    
    char = gui.character_combobox.currentText()
    set_ = gui.prompt_pack_combobox.currentText()
    
    if not char or not set_:
        return
    
    if not _prompts_match(char, set_, gui=gui):
        reply = QMessageBox.question(
            gui,
            _("Несоответствие промптов", "Prompts differ"),
            _("Промпты персонажа отличаются от выбранного набора.\nЗаменить?", 
              "Character prompts differ from selected set.\nReplace?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            apply_prompt_set(gui)
    else:
        # Просто сохраняем выбор в Settings, чтобы он "запомнился"
        gui.settings.set(_prompt_set_key(char), set_)
        gui.settings.save_settings()

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

    event_bus.emit(Events.Model.SET_CHARACTER_TO_CHANGE, {'character': selected_character})
    event_bus.emit(Events.Model.CHECK_CHANGE_CHARACTER)

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

        saved_key = _prompt_set_key(selected_character)
        saved_prompt = gui.settings.get(saved_key, "")
        if saved_prompt and saved_prompt in new_options:
            gui.prompt_pack_combobox.setCurrentText(saved_prompt)
        else:
            set_default_prompt_pack(gui, gui.prompt_pack_combobox)

        gui.prompt_pack_combobox.blockSignals(False)
        _update_sync_indicator(gui)


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
        if copy_prompt_set(set_path, character_prompts_path, clean_target=True):
            # Сохраняем выбор ТОЛЬКО для этого персонажа
            gui.settings.set(_prompt_set_key(char_from), chat_to)
            gui.settings.save_settings()
            _update_sync_indicator(gui)  # теперь должно стать зелёным
            
            if force_apply:
                QMessageBox.information(gui, _("Успех", "Success"),
                                         _("Набор промптов успешно применен.", "Prompt set applied successfully."))
            event_bus.emit(Events.Model.RELOAD_CHARACTER_DATA)
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
    current_char_data = event_bus.emit_and_wait(Events.Model.GET_CURRENT_CHARACTER, timeout=1.0)
    
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
    current_char_data = event_bus.emit_and_wait(Events.Model.GET_CURRENT_CHARACTER, timeout=1.0)
    
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
    event_bus.emit(Events.Model.CLEAR_CHARACTER_HISTORY)
    gui.clear_chat_display()
    gui.update_debug_info()


def clear_history_all(gui):
    event_bus = get_event_bus()
    event_bus.emit(Events.Model.CLEAR_ALL_HISTORIES)
    gui.clear_chat_display()
    gui.update_debug_info()


def reload_prompts(gui):
    reply = QMessageBox.question(gui, _("Подтверждение", "Confirmation"),
                                 _("Это удалит текущие промпты! Продолжить?", "This will delete the current prompts! Continue?"),
                                 QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    if reply == QMessageBox.StandardButton.Ok:
        gui._show_loading_popup(_("Загрузка промптов...", "Downloading prompts..."))
        
        event_bus = get_event_bus()
        event_bus.emit(Events.Model.RELOAD_PROMPTS_ASYNC)


def save_character_provider(gui, provider: str):
    event_bus = get_event_bus()
    
    selected_character = gui.character_combobox.currentText() if hasattr(gui, 'character_combobox') else None
    if not selected_character:
        QMessageBox.warning(gui, _("Внимание", "Warning"), _("Персонаж не выбран.", "No character selected."))
        return
    provider_key = f"CHAR_PROVIDER_{selected_character}"
    gui.settings.set(provider_key, provider)
    logger.info(f"Saved provider '{provider}' for character '{selected_character}'")
    event_bus.emit(Events.Model.CHECK_CHANGE_CHARACTER)