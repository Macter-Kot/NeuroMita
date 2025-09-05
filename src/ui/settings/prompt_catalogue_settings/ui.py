from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFrame, QLineEdit, QSizePolicy, QToolButton
)
import qtawesome as qta

from utils import getTranslationVariant as _
from ui.gui_templates import create_section_header


def _make_info_field(self, parent_layout, label_text, key, label_min_w=90):
    row = QWidget()
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(8)

    lbl = QLabel(label_text)
    lbl.setMinimumWidth(label_min_w)
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    hl.addWidget(lbl, 0)

    entry = QLineEdit()
    self.info_json_entries[key] = entry
    hl.addWidget(entry, 1)

    parent_layout.addWidget(row)


def build_prompt_catalogue_ui(self, parent_layout):
    # Небольшой правый отступ, чтобы контент не уезжал под сайдбар
    sidebar_w = getattr(self, "SETTINGS_SIDEBAR_WIDTH", 50)
    right_pad = max(8, min(14, int(sidebar_w * 0.22)))  # ~11px при 50px

    container = QWidget()
    container_lay = QVBoxLayout(container)
    container_lay.setContentsMargins(0, 0, right_pad, 0)
    container_lay.setSpacing(6)

    # Заголовок
    create_section_header(container_lay, _("Каталог промптов", "Prompt Catalogue"))

    # Верхняя строка: список наборов + компактная кнопка обновления
    top_row = QWidget()
    top_lay = QHBoxLayout(top_row)
    top_lay.setContentsMargins(0, 0, 0, 0)
    top_lay.setSpacing(8)

    lbl = QLabel(_("Выберите набор:", "Select set:"))
    top_lay.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)

    self.prompt_set_combobox = QComboBox()
    self.prompt_set_combobox.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    self.prompt_set_combobox.setMinimumWidth(220)
    top_lay.addWidget(self.prompt_set_combobox, 1)

    self.prompt_refresh_button = QToolButton()
    self.prompt_refresh_button.setIcon(qta.icon('fa5s.sync'))
    self.prompt_refresh_button.setToolTip(_("Обновить", "Refresh"))
    self.prompt_refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
    top_lay.addWidget(self.prompt_refresh_button, 0)

    container_lay.addWidget(top_row)

    # Блок действий: 1 ряд, 2 кнопки
    actions_row = QWidget()
    actions_lay = QHBoxLayout(actions_row)
    actions_lay.setContentsMargins(0, 2, 0, 2)
    actions_lay.setSpacing(8)

    self.pc_open_folder_button = QPushButton(_("Открыть папку", "Open Folder"))
    self.pc_open_folder_button.setObjectName("SecondaryButton")
    self.pc_open_folder_button.setIcon(qta.icon('fa5s.folder-open', color='#ffffff'))
    self.pc_open_folder_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    actions_lay.addWidget(self.pc_open_folder_button, 1)

    self.pc_delete_button = QPushButton(_("Удалить", "Delete"))
    self.pc_delete_button.setObjectName("SecondaryDangerButton")
    self.pc_delete_button.setIcon(qta.icon('fa5s.trash', color='#ffffff'))
    self.pc_delete_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    actions_lay.addWidget(self.pc_delete_button, 1)

    container_lay.addWidget(actions_row)

    # Информационная карточка (info.json)
    info_card = QFrame()
    info_card.setObjectName("InfoFrame")
    info_lay = QVBoxLayout(info_card)
    info_lay.setSpacing(6)
    info_lay.setContentsMargins(8, 8, 8, 8)

    title = QLabel(_("Информация о наборе", "Set Information"))
    title.setStyleSheet("font-weight: 600;")
    info_lay.addWidget(title)

    # Поля редактирования info.json
    self.info_json_entries = {}

    overlay_w = getattr(self, "SETTINGS_PANEL_WIDTH", 400)
    label_min_w = max(90, min(140, int(overlay_w * 0.28)))

    _make_info_field(self, info_lay, _("Папка:", "Folder:"), "folder", label_min_w)
    _make_info_field(self, info_lay, _("Персонаж:", "Character:"), "character", label_min_w)
    _make_info_field(self, info_lay, _("Автор:", "Author:"), "author", label_min_w)
    _make_info_field(self, info_lay, _("Версия:", "Version:"), "version", label_min_w)
    _make_info_field(self, info_lay, _("Описание:", "Description:"), "description", label_min_w)

    # Кнопка сохранения по центру
    save_row = QWidget()
    save_lay = QHBoxLayout(save_row)
    save_lay.setContentsMargins(0, 0, 0, 0)
    save_lay.addStretch()

    self.pc_save_info_button = QPushButton(_("Сохранить информацию", "Save Information"))
    self.pc_save_info_button.setObjectName("SecondaryButton")
    self.pc_save_info_button.setIcon(qta.icon('fa5s.save', color='#ffffff'))
    save_lay.addWidget(self.pc_save_info_button, 0)

    save_lay.addStretch()
    info_lay.addWidget(save_row)

    container_lay.addWidget(info_card)

    # Вставляем контейнер во вкладку
    parent_layout.addWidget(container)