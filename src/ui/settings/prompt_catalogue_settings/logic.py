import os
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

from utils import getTranslationVariant as _
from core.events import get_event_bus, Events
from managers.prompt_catalogue_manager import (
    list_prompt_sets, read_info_json, write_info_json, delete_prompt_set
)


def _prompt_set_key(char_name: str) -> str:
    """Ключ Settings для конкретного персонажа (как в character_settings)"""
    return f"PROMPT_SET_{char_name}"


def _update_sync_indicator(gui):
    """Обновляет индикатор синхронизации у вкладки Персонажи (если есть)."""
    try:
        from ui.settings.character_settings.logic import _update_sync_indicator as _upd
        _upd(gui)
    except Exception:
        pass


def wire_prompt_catalogue_logic(self):
    catalogue_path = "PromptsCatalogue"
    bus = get_event_bus()

    def update_prompt_set_combobox():
        current_text = self.prompt_set_combobox.currentText()
        self.prompt_set_combobox.blockSignals(True)
        try:
            self.prompt_set_combobox.clear()
            sets = list_prompt_sets(catalogue_path)
            if sets:
                self.prompt_set_combobox.addItems(sets)
                if current_text in sets:
                    self.prompt_set_combobox.setCurrentText(current_text)
                else:
                    self.prompt_set_combobox.setCurrentIndex(0)
        finally:
            self.prompt_set_combobox.blockSignals(False)
        on_prompt_set_selected(self.prompt_set_combobox.currentText())

    def on_prompt_set_selected(selected_set_name: str):
        if selected_set_name:
            set_path = os.path.join(catalogue_path, selected_set_name)
            load_info_json(set_path)

    def load_info_json(set_path: str):
        info_data = read_info_json(set_path)
        folder_name = os.path.basename(set_path)
        clear_info_json_fields()
        if info_data:
            for key, entry in self.info_json_entries.items():
                entry.setText(info_data.get(key, ""))
        # Поле "Папка" всегда совпадает с именем папки (редактируемое для переименования)
        self.info_json_entries["folder"].setText(folder_name)

    def clear_info_json_fields():
        for entry in self.info_json_entries.values():
            entry.clear()

    def save_info_json_action():
        selected_set_name = self.prompt_set_combobox.currentText()
        if not selected_set_name:
            QMessageBox.warning(self, _("Внимание", "Warning"),
                                _("Набор промптов не выбран для сохранения.", "No prompt set selected for saving."))
            return

        current_set_path = os.path.join(catalogue_path, selected_set_name)
        new_folder_name = self.info_json_entries["folder"].text().strip()

        # Переименование папки набора
        if new_folder_name and new_folder_name != selected_set_name:
            new_set_path = os.path.join(catalogue_path, new_folder_name)
            if os.path.exists(new_set_path):
                QMessageBox.critical(self, _("Ошибка", "Error"),
                                     _(f"Папка с именем '{new_folder_name}' уже существует.",
                                       f"Folder with name '{new_folder_name}' already exists."))
                return
            try:
                os.rename(current_set_path, new_set_path)
                current_set_path = new_set_path
            except OSError as e:
                QMessageBox.critical(self, _("Ошибка", "Error"),
                                     _(f"Не удалось переименовать папку: {e}", f"Failed to rename folder: {e}"))
                return

        # Пишем info.json (без ключа folder)
        info_data = {key: entry.text() for key, entry in self.info_json_entries.items() if key != 'folder'}
        if write_info_json(current_set_path, info_data):
            QMessageBox.information(self, _("Успех", "Success"),
                                    _("Информация о наборе сохранена.", "Set information saved."))
            update_prompt_set_combobox()

    def open_set_folder_action():
        selected_set_name = self.prompt_set_combobox.currentText()
        if selected_set_name:
            set_path = os.path.join(catalogue_path, selected_set_name)
            if os.path.exists(set_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(set_path)))
            else:
                QMessageBox.warning(self, _("Внимание", "Warning"),
                                    _("Папка набора не найдена.", "Set folder not found."))
        else:
            QMessageBox.warning(self, _("Внимание", "Warning"),
                                _("Набор промптов не выбран.", "No prompt set selected."))

    def delete_set_action():
        selected_set_name = self.prompt_set_combobox.currentText()
        if selected_set_name:
            set_path = os.path.join(catalogue_path, selected_set_name)
            if delete_prompt_set(set_path):
                QMessageBox.information(self, _("Успех", "Success"),
                                        _("Набор промптов успешно удален.", "Prompt set deleted successfully."))
                update_prompt_set_combobox()
        else:
            QMessageBox.warning(self, _("Внимание", "Warning"),
                                _("Набор промптов не выбран.", "No prompt set selected."))

    # Wiring
    self.prompt_set_combobox.currentTextChanged.connect(on_prompt_set_selected)
    self.prompt_refresh_button.clicked.connect(update_prompt_set_combobox)
    self.pc_open_folder_button.clicked.connect(open_set_folder_action)
    self.pc_delete_button.clicked.connect(delete_set_action)
    self.pc_save_info_button.clicked.connect(save_info_json_action)

    # Первичное заполнение
    update_prompt_set_combobox()