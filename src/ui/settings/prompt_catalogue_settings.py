import os

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
                             QPushButton, QFrame, QMessageBox, QLineEdit, QSizePolicy)
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices

from utils import getTranslationVariant as _
from managers.prompt_catalogue_manager import (
    list_prompt_sets, read_info_json, write_info_json,
    copy_prompt_set, create_new_set, delete_prompt_set
)
from managers.settings_manager import CollapsibleSection

from ui.windows.events import get_event_bus, Events

def setup_prompt_catalogue_controls(gui, parent_layout):
    catalogue_path = "PromptsCatalogue"
    
    prompt_catalogue_section = CollapsibleSection(_("Каталог промптов", "Prompt Catalogue"))
    parent_layout.addWidget(prompt_catalogue_section)

    content_layout = prompt_catalogue_section.content_layout

    # Combobox and Refresh button
    combo_frame = QWidget()
    combo_layout = QHBoxLayout(combo_frame)
    combo_layout.setContentsMargins(0, 0, 0, 0)
    combo_layout.setSpacing(10)
    
    combo_layout.addWidget(QLabel(_("Выберите набор:", "Select set:")))
    prompt_set_combobox = QComboBox()
    prompt_set_combobox.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    combo_layout.addWidget(prompt_set_combobox, 1)
    
    refresh_button = QPushButton(_("Обновить", "Refresh"))
    combo_layout.addWidget(refresh_button)
    content_layout.addWidget(combo_frame)
    
    # Action Buttons
    button_frame = QWidget()
    button_layout = QHBoxLayout(button_frame)
    button_layout.setContentsMargins(0, 5, 0, 5)
    button_layout.setSpacing(10)
    replace_button = QPushButton(_("Заменить", "Replace"))
    create_button = QPushButton(_("Создать", "Create"))
    open_folder_button = QPushButton(_("Открыть папку", "Open Folder"))
    delete_button = QPushButton(_("Удалить", "Delete"))
    button_layout.addWidget(replace_button)
    button_layout.addWidget(create_button)
    button_layout.addWidget(open_folder_button)
    button_layout.addWidget(delete_button)
    content_layout.addWidget(button_frame)

    # Info editing section
    info_json_frame = QFrame()
    info_json_frame.setObjectName("InfoFrame") # Можно стилизовать, если нужно
    info_layout = QVBoxLayout(info_json_frame)
    info_layout.setSpacing(4)
    info_layout.setContentsMargins(0, 5, 0, 5)
    info_layout.addWidget(QLabel(_("Информация о наборе", "Set Information")))
    
    gui.info_json_entries = {}
    
    def create_info_field(parent_layout, label_text, key):
        field_layout = QHBoxLayout()
        field_layout.setSpacing(10)
        label = QLabel(label_text)
        label.setMinimumWidth(80)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        field_layout.addWidget(label)
        entry = QLineEdit()
        gui.info_json_entries[key] = entry
        field_layout.addWidget(entry, 1)
        parent_layout.addLayout(field_layout)

    create_info_field(info_layout, _("Папка:", "Folder:"), "folder")
    create_info_field(info_layout, _("Персонаж:", "Character:"), "character")
    create_info_field(info_layout, _("Автор:", "Author:"), "author")
    create_info_field(info_layout, _("Версия:", "Version:"), "version")
    create_info_field(info_layout, _("Описание:", "Description:"), "description")

    save_info_button = QPushButton(_("Сохранить информацию", "Save Information"))
    
    save_button_layout = QHBoxLayout()
    save_button_layout.addStretch()
    save_button_layout.addWidget(save_info_button)
    save_button_layout.addStretch()
    
    info_layout.addLayout(save_button_layout)
    content_layout.addWidget(info_json_frame)

    def update_prompt_set_combobox():
        current_text = prompt_set_combobox.currentText()
        prompt_set_combobox.blockSignals(True)
        prompt_set_combobox.clear()
        sets = list_prompt_sets(catalogue_path)
        if sets:
            prompt_set_combobox.addItems(sets)
            if current_text in sets:
                prompt_set_combobox.setCurrentText(current_text)
            else:
                prompt_set_combobox.setCurrentIndex(0)
        prompt_set_combobox.blockSignals(False)
        on_prompt_set_selected(prompt_set_combobox.currentText())

    def on_prompt_set_selected(selected_set_name):
        if selected_set_name:
            set_path = os.path.join(catalogue_path, selected_set_name)
            load_info_json(set_path)

    def load_info_json(set_path):
        info_data = read_info_json(set_path)
        folder_name = os.path.basename(set_path)
        clear_info_json_fields()
        if info_data:
            for key, entry in gui.info_json_entries.items():
                entry.setText(info_data.get(key, ""))
        gui.info_json_entries["folder"].setText(folder_name)

    def clear_info_json_fields():
        for entry in gui.info_json_entries.values():
            entry.clear()
            
    def save_info_json_action():
        selected_set_name = prompt_set_combobox.currentText()
        if not selected_set_name:
            QMessageBox.warning(gui, _("Внимание", "Warning"), _("Набор промптов не выбран для сохранения.", "No prompt set selected for saving."))
            return

        current_set_path = os.path.join(catalogue_path, selected_set_name)
        new_folder_name = gui.info_json_entries["folder"].text().strip()
        
        if new_folder_name and new_folder_name != selected_set_name:
            new_set_path = os.path.join(catalogue_path, new_folder_name)
            if os.path.exists(new_set_path):
                QMessageBox.critical(gui, _("Ошибка", "Error"), _(f"Папка с именем '{new_folder_name}' уже существует.", f"Folder with name '{new_folder_name}' already exists."))
                return
            try:
                os.rename(current_set_path, new_set_path)
                current_set_path = new_set_path
            except OSError as e:
                QMessageBox.critical(gui, _("Ошибка", "Error"), _(f"Не удалось переименовать папку: {e}", f"Failed to rename folder: {e}"))
                return
        
        info_data = {key: entry.text() for key, entry in gui.info_json_entries.items() if key != 'folder'}
        if write_info_json(current_set_path, info_data):
            QMessageBox.information(gui, _("Успех", "Success"), _("Информация о наборе сохранена.", "Set information saved."))
            update_prompt_set_combobox()

    def replace_prompt_set_action():
        selected_set_name = prompt_set_combobox.currentText()
        if not selected_set_name:
            QMessageBox.warning(gui, _("Внимание", "Warning"), _("Набор промптов не выбран для замены.", "No prompt set selected for replacement."))
            return
        set_path = os.path.join(catalogue_path, selected_set_name)
        if gui.model.current_character and gui.model.current_character.char_id:
             character_prompts_path = os.path.join("Prompts", gui.model.current_character.char_id)
             if copy_prompt_set(set_path, character_prompts_path):
                 QMessageBox.information(gui, _("Успех", "Success"), _("Набор промптов успешно применен к текущему персонажу.", "Prompt set successfully applied to the current character."))
                 if hasattr(gui.model.current_character, 'reload_character_data'):
                     gui.model.current_character.reload_character_data()
             else:
                 QMessageBox.critical(gui, _("Ошибка", "Error"), _("Не удалось применить набор промптов.", "Failed to apply prompt set."))
        else:
             QMessageBox.warning(gui, _("Внимание", "Warning"), _("Персонаж не выбран. Не удалось применить набор промптов.", "No character selected. Failed to apply prompt set."))

    def create_new_set_action():
        event_bus = get_event_bus()
        current_char_data = event_bus.emit_and_wait(Events.GET_CURRENT_CHARACTER, timeout=1.0)
        
        if current_char_data and current_char_data[0]:
            char_data = current_char_data[0]
            character_name = "Cartridges" if char_data.get('is_cartridge') else char_data.get('char_id')
            if character_name:
                prompts_path = os.path.join("Prompts", character_name)
                new_set_path = create_new_set(character_name, catalogue_path, prompts_path)
                if new_set_path:
                    QMessageBox.information(gui, _("Успех", "Success"), _(f"Новый набор создан из текущих промптов персонажа: {os.path.basename(new_set_path)}", f"New set created from current character prompts: {os.path.basename(new_set_path)}"))
                    update_prompt_set_combobox()
                    prompt_set_combobox.setCurrentText(os.path.basename(new_set_path))
                else:
                    QMessageBox.critical(gui, _("Ошибка", "Error"), _("Не удалось создать новый набор промптов.", "Failed to create new prompt set."))
            else:
                QMessageBox.warning(gui, _("Внимание", "Warning"), _("Персонаж не выбран. Не удалось создать новый набор промптов.", "No character selected. Failed to create new prompt set."))
        else:
            QMessageBox.warning(gui, _("Внимание", "Warning"), _("Персонаж не выбран. Не удалось создать новый набор промптов.", "No character selected. Failed to create new prompt set."))
    
    def open_set_folder_action():
        selected_set_name = prompt_set_combobox.currentText()
        if selected_set_name:
            set_path = os.path.join(catalogue_path, selected_set_name)
            if os.path.exists(set_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(set_path)))
            else:
                QMessageBox.warning(gui, _("Внимание", "Warning"), _("Папка набора не найдена.", "Set folder not found."))
        else:
            QMessageBox.warning(gui, _("Внимание", "Warning"), _("Набор промптов не выбран.", "No prompt set selected."))

    def delete_set_action():
        selected_set_name = prompt_set_combobox.currentText()
        if selected_set_name:
            set_path = os.path.join(catalogue_path, selected_set_name)
            if delete_prompt_set(set_path, gui):
                QMessageBox.information(gui, _("Успех", "Success"), _("Набор промптов успешно удален.", "Prompt set deleted successfully."))
                update_prompt_set_combobox()
        else:
            QMessageBox.warning(gui, _("Внимание", "Warning"), _("Набор промптов не выбран.", "No prompt set selected."))

    prompt_set_combobox.currentTextChanged.connect(on_prompt_set_selected)
    refresh_button.clicked.connect(update_prompt_set_combobox)
    replace_button.clicked.connect(replace_prompt_set_action)
    create_button.clicked.connect(create_new_set_action)
    open_folder_button.clicked.connect(open_set_folder_action)
    delete_button.clicked.connect(delete_set_action)
    save_info_button.clicked.connect(save_info_json_action)

    update_prompt_set_combobox()