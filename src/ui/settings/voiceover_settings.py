import os
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox, 
                             QPushButton, QCheckBox, QSizePolicy)
from PyQt6.QtCore import Qt
from main_logger import logger
from ui.gui_templates import create_setting_widget, create_settings_direct, create_section_header
from utils import getTranslationVariant as _

LOCAL_VOICE_MODELS = [
    {"id": "low", "name": "Edge-TTS + RVC", "min_vram": 3, "rec_vram": 4, "gpu_vendor": ["NVIDIA", "AMD"], "size_gb": 3},
    {"id": "low+", "name": "Silero + RVC", "min_vram": 3, "rec_vram": 4, "gpu_vendor": ["NVIDIA", "AMD"], "size_gb": 3},
    {"id": "medium", "name": "Fish Speech", "min_vram": 4, "rec_vram": 6, "gpu_vendor": ["NVIDIA"], "size_gb": 5},
    {"id": "medium+", "name": "Fish Speech+", "min_vram": 4, "rec_vram": 6, "gpu_vendor": ["NVIDIA"], "size_gb": 10},
    {"id": "medium+low", "name": "Fish Speech+ + RVC", "min_vram": 6, "rec_vram": 8, "gpu_vendor": ["NVIDIA"], "size_gb": 15},
    {"id": "high", "name": "F5-TTS", "min_vram": 4, "rec_vram": 8, "gpu_vendor": ["NVIDIA", "AMD"], "size_gb": 4},
    {"id": "high+low", "name": "F5-TTS + RVC", "min_vram": 6, "rec_vram": 8, "gpu_vendor": ["NVIDIA", "AMD"], "size_gb": 4}
]

def setup_voiceover_controls(gui, parent_layout):
    # Создаём заголовок секции
    create_section_header(parent_layout, _("Настройка озвучки", "Voiceover Settings"))
    
    # Сохраняем ссылку для совместимости
    gui.voiceover_section = type('obj', (object,), {'content_frame': parent_layout.parent()})()
    
    # --- Главный чекбокс и выбор метода ---
    main_config = [
        {'label': _('Использовать озвучку', 'Use speech'), 'key': 'USE_VOICEOVER', 'type': 'checkbutton', 
         'default_checkbutton': False, 'widget_name': 'use_voice_checkbox'},
        {'label': _("Вариант озвучки", "Voiceover Method"), 'key': 'VOICEOVER_METHOD', 'type': 'combobox', 
         'options': ["TG", "Local"] if os.environ.get("EXPERIMENTAL_FUNCTIONS", "1") == "1" else ["TG"], 
         'default': 'TG', 'widget_name': 'method_combobox'}
    ]
    
    for config in main_config:
        widget = create_setting_widget(
            gui=gui,
            parent=parent_layout.parent(),
            label=config.get('label'),
            setting_key=config.get('key', ''),
            widget_type=config.get('type', 'entry'),
            options=config.get('options'),
            default=config.get('default', ''),
            default_checkbutton=config.get('default_checkbutton', False),
            widget_name=config.get('widget_name')
        )
        if widget:
            parent_layout.addWidget(widget)
            if config.get('widget_name') == 'method_combobox':
                gui.method_frame = widget

    # --- Контейнер для настроек TG ---
    gui.tg_settings_frame = QWidget()
    tg_layout = QVBoxLayout(gui.tg_settings_frame)
    tg_layout.setContentsMargins(0,0,0,0)
    tg_layout.setSpacing(0)
    
    tg_config = [
        {'label': _('Канал/Сервис', "Channel/Service"), 'key': 'AUDIO_BOT', 'type': 'combobox', 
         'options': ["@silero_voice_bot", "@CrazyMitaAIbot"], 'default': "@silero_voice_bot"},
        {'label': _('Макс. ожидание (сек)', 'Max wait (sec)'), 'key': 'SILERO_TIME', 'type': 'entry', 
         'default': '12', 'validation': gui.validate_number_0_60},
        {'label': _('Настройки Telegram API', 'Telegram API Settings'), 'type': 'text'},
        {'label': _('Будет скрыто после перезапуска', 'Will be hidden after restart'), 'type': 'text'},
        {'label': _('Telegram ID'), 'key': 'NM_TELEGRAM_API_ID', 'type': 'entry', 
         'default': "", 'hide': bool(gui.settings.get("HIDE_PRIVATE"))},
        {'label': _('Telegram Hash'), 'key': 'NM_TELEGRAM_API_HASH', 'type': 'entry', 
         'default': "", 'hide': bool(gui.settings.get("HIDE_PRIVATE"))},
        {'label': _('Telegram Phone'), 'key': 'NM_TELEGRAM_PHONE', 'type': 'entry', 
         'default': "", 'hide': bool(gui.settings.get("HIDE_PRIVATE"))},
    ]
    
    for config in tg_config:
        widget = create_setting_widget(
            gui=gui, 
            parent=gui.tg_settings_frame, 
            label=config['label'], 
            setting_key=config.get('key', ''), 
            widget_type=config.get('type', 'entry'), 
            options=config.get('options'), 
            default=config.get('default', ''), 
            validation=config.get('validation'), 
            hide=config.get('hide', False)
        )
        if widget:
            tg_layout.addWidget(widget)
    
    parent_layout.addWidget(gui.tg_settings_frame)

    # --- Контейнер для локальных настроек ---
    gui.local_settings_frame = QWidget()
    local_layout = QVBoxLayout(gui.local_settings_frame)
    local_layout.setContentsMargins(0,0,0,0)
    local_layout.setSpacing(0)

    # --- Локальная модель (строка создается вручную для иконки) ---
    local_model_row = QWidget()
    local_model_layout = QHBoxLayout(local_model_row)
    local_model_layout.setContentsMargins(0, 2, 0, 2)
    local_model_layout.setSpacing(10)

    label_part = QHBoxLayout()
    label_part.setContentsMargins(0, 0, 0, 0)
    label_part.setSpacing(5)
    
    local_model_label = QLabel(_("Локальная модель", "Local Model"))
    gui.local_model_status_label = QLabel("⚠️")
    gui.local_model_status_label.setObjectName("WarningIcon")
    gui.local_model_status_label.setToolTip(_("Модель не инициализирована или не установлена.", 
                                             "Model not initialized or not installed."))
    label_part.addWidget(gui.local_model_status_label)
    label_part.addWidget(local_model_label)
    
    label_container = QWidget()
    label_container.setLayout(label_part)
    label_container.setMinimumWidth(140)
    label_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    
    gui.local_voice_combobox = QComboBox()
    gui.local_voice_combobox.activated.connect(gui.on_local_voice_selected)

    local_model_layout.addWidget(label_container)
    local_model_layout.addWidget(gui.local_voice_combobox, 1)
    local_layout.addWidget(local_model_row)

    # --- Остальные локальные настройки ---
    local_config = [
        {'label': _("Язык локальной озвучки", "Local Voice Language"), 'key': "VOICE_LANGUAGE", 
         'type': 'combobox', 'options': ["ru", "en"], 'default': "ru", 
         'command': gui.on_voice_language_selected, 'widget_name': 'voice_language_var_combobox'},
        {'label': _('Автозагрузка модели', 'Autoload model'), 'key': 'LOCAL_VOICE_LOAD_LAST', 
         'type': 'checkbutton', 'default_checkbutton': False},
        {'label': _('Озвучивать в чате', 'Voiceover in chat'), 'key': 'VOICEOVER_LOCAL_CHAT', 
         'type': 'checkbutton', 'default_checkbutton': True},
        {'label': _('Управление моделями', 'Manage Models'), 'type': 'button', 
         'command': gui.open_local_model_installation_window}
    ]
    
    if os.environ.get("ENABLE_VOICE_DELETE_CHECKBOX", "0") == "1":
        local_config.insert(2, {'label': _('Удалять аудио', 'Delete audio'), 
                               'key': 'LOCAL_VOICE_DELETE_AUDIO', 'type': 'checkbutton', 
                               'default_checkbutton': True})

    for config in local_config:
        widget = create_setting_widget(
            gui=gui,
            parent=gui.local_settings_frame,
            label=config.get('label'),
            setting_key=config.get('key', ''),
            widget_type=config.get('type', 'entry'),
            options=config.get('options'),
            default=config.get('default', ''),
            default_checkbutton=config.get('default_checkbutton', False),
            command=config.get('command'),
            widget_name=config.get('widget_name')
        )
        if widget:
            local_layout.addWidget(widget)

    parent_layout.addWidget(gui.local_settings_frame)

    # --- Первичная настройка видимости ---
    gui.switch_voiceover_settings()
    gui.check_triton_dependencies()
    gui.update_local_voice_combobox()