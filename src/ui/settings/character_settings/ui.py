from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox,
    QPushButton, QSizePolicy, QFrame, QCheckBox, QSpacerItem, QSizePolicy
)
import qtawesome as qta

from ui.gui_templates import create_section_header
from utils import getTranslationVariant as _


def _make_row(label_text: str, field_widget: QWidget, label_w: int) -> QWidget:
    row = QWidget()
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(6)

    lbl = QLabel(label_text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    lbl.setFixedWidth(label_w)
    hl.addWidget(lbl, 0)

    hl.addWidget(field_widget, 1)
    return row


def build_character_settings_ui(self, parent_layout):
    # Контейнер с правым отступом (защита от перекрытия сайдбаром)
    right_pad = getattr(self, "SETTINGS_SIDEBAR_WIDTH", 50) + 8

    container = QWidget()
    container_lay = QVBoxLayout(container)
    container_lay.setContentsMargins(0, 0, right_pad, 0)
    container_lay.setSpacing(6)

    # Заголовок секции
    create_section_header(container_lay, _("Настройки персонажей", "Characters Settings"))

    # Расчёт ширины колонки меток
    overlay_w = getattr(self, "SETTINGS_PANEL_WIDTH", 400)
    label_w = max(90, min(120, int(overlay_w * 0.3)))
    self.mic_label_width = label_w

    root = QWidget()
    lay = QVBoxLayout(root)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)

    # --- Персонажи
    character_field = QWidget()
    ch_h = QHBoxLayout(character_field)
    ch_h.setContentsMargins(0, 0, 0, 0)
    ch_h.setSpacing(6)

    self.character_combobox = QComboBox()
    self.character_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    ch_h.addWidget(self.character_combobox, 1)

    lay.addWidget(_make_row(_("Персонажи", "Characters"), character_field, label_w))

    # --- Набор промтов (+ индикатор)
    prompt_field = QWidget()
    pr_h = QHBoxLayout(prompt_field)
    pr_h.setContentsMargins(0, 0, 0, 0)
    pr_h.setSpacing(6)

    self.prompt_pack_combobox = QComboBox()
    self.prompt_pack_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    pr_h.addWidget(self.prompt_pack_combobox, 1)

    self.prompt_sync_label = QLabel("●")
    self.prompt_sync_label.setToolTip(_("Индикатор соответствия промптов", "Prompts sync indicator"))
    self.prompt_sync_label.setStyleSheet("color: #bdc3c7; font-size: 16px;")
    pr_h.addWidget(self.prompt_sync_label, 0, Qt.AlignmentFlag.AlignVCenter)

    lay.addWidget(_make_row(_("Набор промтов", "Prompt set"), prompt_field, label_w))

    # --- Провайдер для персонажа
    provider_field = QWidget()
    pv_h = QHBoxLayout(provider_field)
    pv_h.setContentsMargins(0, 0, 0, 0)
    pv_h.setSpacing(6)

    self.char_provider_combobox = QComboBox()
    self.char_provider_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    pv_h.addWidget(self.char_provider_combobox, 1)

    lay.addWidget(_make_row(_("Провайдер для персонажа", "Provider for character"), provider_field, label_w))

    # --- Показ логов сравнения промптов
    self.show_prompt_sync_logs_check = QCheckBox(_("Показывать логи сравнения промптов", "Show prompt comparison logs"))
    lay.addWidget(_make_row(_("Логи", "Logs"), self.show_prompt_sync_logs_check, label_w))

    # --- Управление персонажем (подзаголовок)
    sub_title1 = QLabel(_("Управление персонажем", "Character management"))
    sub_title1.setStyleSheet("font-weight: 600;")
    lay.addWidget(sub_title1)

    mgmt_row = QWidget()
    mg_h = QHBoxLayout(mgmt_row)
    mg_h.setContentsMargins(0, 0, 0, 0)
    mg_h.setSpacing(6)

    self.btn_open_character_folder = QPushButton(_("Открыть папку персонажа", "Open character folder"))
    self.btn_open_character_folder.setObjectName("SecondaryButton")
    self.btn_open_character_folder.setIcon(qta.icon('fa5s.folder-open', color='#ffffff'))
    mg_h.addWidget(self.btn_open_character_folder, 1)

    self.btn_open_history_folder = QPushButton(_("Папку истории", "History folder"))
    self.btn_open_history_folder.setObjectName("SecondaryButton")
    self.btn_open_history_folder.setIcon(qta.icon('fa5s.clock', color='#ffffff'))
    mg_h.addWidget(self.btn_open_history_folder, 1)

    lay.addWidget(mgmt_row)

    # --- Опасные действия
    sub_title2 = QLabel(_("Аккуратно!", "Be careful!"))
    sub_title2.setStyleSheet("font-weight: 600;")
    lay.addWidget(sub_title2)

    danger_row = QWidget()
    dn_h = QHBoxLayout(danger_row)
    dn_h.setContentsMargins(0, 0, 0, 0)
    dn_h.setSpacing(6)

    self.btn_clear_history = QPushButton(_("Очистить историю", "Clear history"))
    self.btn_clear_history.setObjectName("SecondaryButton")
    self.btn_clear_history.setIcon(qta.icon('fa5s.trash', color='#ffffff'))
    dn_h.addWidget(self.btn_clear_history, 1)

    self.btn_clear_all_histories = QPushButton(_("Очистить все истории", "Clear all histories"))
    self.btn_clear_all_histories.setObjectName("SecondaryButton")
    self.btn_clear_all_histories.setIcon(qta.icon('fa5s.trash-alt', color='#ffffff'))
    dn_h.addWidget(self.btn_clear_all_histories, 1)

    lay.addWidget(danger_row)

    # --- Перекачать промпты
    self.btn_reload_prompts = QPushButton(_("Перекачать промпты", "Reload prompts"))
    self.btn_reload_prompts.setObjectName("SecondaryButton")
    self.btn_reload_prompts.setIcon(qta.icon('fa5s.download', color='#ffffff'))
    lay.addWidget(self.btn_reload_prompts)

    container_lay.addWidget(root)
    parent_layout.addWidget(container)