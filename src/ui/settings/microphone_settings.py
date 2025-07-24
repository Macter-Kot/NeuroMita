import re
from PyQt6.QtWidgets import (QComboBox, QCheckBox, QWidget, QHBoxLayout, QVBoxLayout,
                             QLabel, QSizePolicy, QPushButton)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
import qtawesome as qta

from ui.gui_templates import create_setting_widget, create_settings_direct, create_section_header
from main_logger import logger
from utils import getTranslationVariant as _
from core.events import get_event_bus, Events

def setup_microphone_controls(gui, parent_layout):
    create_section_header(parent_layout, _("Настройки микрофона", "Microphone Settings"))
    
    event_bus = get_event_bus()
    
    # --- Выбор микрофона (строка создается вручную) ---
    mic_row = QWidget()
    mic_layout = QHBoxLayout(mic_row)
    mic_layout.setContentsMargins(0, 2, 0, 2)
    mic_layout.setSpacing(10)
    
    mic_label = QLabel(_("Микрофон", "Microphone"))
    mic_label.setMinimumWidth(140)
    mic_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    
    gui.mic_combobox = QComboBox()
    gui.mic_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    gui.mic_combobox.setMinimumWidth(150)
    
    results = event_bus.emit_and_wait(Events.Speech.GET_MICROPHONE_LIST, timeout=1.0)
    mic_list = results[0] if results else [_("Микрофоны не найдены", "No microphones found")]
    
    for mic_name in mic_list:
        display_name = mic_name
        if len(mic_name) > 40:
            display_name = mic_name[:37] + "..."
        gui.mic_combobox.addItem(display_name)
        index = gui.mic_combobox.count() - 1
        gui.mic_combobox.setItemData(index, mic_name, Qt.ItemDataRole.UserRole)
        gui.mic_combobox.setItemData(index, mic_name, Qt.ItemDataRole.ToolTipRole)
    
    current_mic = gui.settings.get('MIC_DEVICE', mic_list[0] if mic_list else "")
    for i in range(gui.mic_combobox.count()):
        if gui.mic_combobox.itemData(i, Qt.ItemDataRole.UserRole) == current_mic:
            gui.mic_combobox.setCurrentIndex(i)
            break
    gui.mic_combobox.setToolTip(current_mic)
    
    def on_mic_changed(index):
        if index >= 0:
            full_name = gui.mic_combobox.itemData(index, Qt.ItemDataRole.UserRole)
            gui._save_setting('MIC_DEVICE', full_name)
            gui.mic_combobox.setToolTip(full_name)
            on_mic_selected(gui, full_name)
    
    gui.mic_combobox.currentIndexChanged.connect(on_mic_changed)
    
    mic_layout.addWidget(mic_label)
    mic_layout.addWidget(gui.mic_combobox)
    parent_layout.addWidget(mic_row)
    
    # --- Тип распознавания с иконкой статуса ---
    recognizer_row = QWidget()
    recognizer_layout = QHBoxLayout(recognizer_row)
    recognizer_layout.setContentsMargins(0, 2, 0, 2)
    recognizer_layout.setSpacing(10)
    
    label_part = QHBoxLayout()
    label_part.setContentsMargins(0, 0, 0, 0)
    label_part.setSpacing(5)
    
    recognizer_label = QLabel(_("Тип распознавания", "Recognition Type"))
    gui.recognizer_status_icon = QLabel("")
    gui.recognizer_status_icon.setObjectName("StatusIcon")
    label_part.addWidget(gui.recognizer_status_icon)
    label_part.addWidget(recognizer_label)
    
    label_container = QWidget()
    label_container.setLayout(label_part)
    label_container.setMinimumWidth(140)
    label_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    
    gui.recognizer_combobox = QComboBox()
    gui.recognizer_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    gui.recognizer_combobox.addItems(["google", "gigaam"])
    gui.recognizer_combobox.setCurrentText(gui.settings.get('RECOGNIZER_TYPE', 'google'))
    gui.recognizer_combobox.setToolTip(_("Выберите движок распознавания речи", "Select speech recognition engine"))
    
    recognizer_layout.addWidget(label_container)
    recognizer_layout.addWidget(gui.recognizer_combobox)
    parent_layout.addWidget(recognizer_row)
    
    # Кнопка установки модели (изначально скрыта)
    gui.install_model_button = QPushButton(_("Установить модель", "Install Model"))
    gui.install_model_button.setIcon(qta.icon('fa5s.download', color='#3498db'))
    gui.install_model_button.clicked.connect(lambda: install_asr_model(gui))
    gui.install_model_button.hide()
    parent_layout.addWidget(gui.install_model_button)
    
    # --- Общие настройки ---
    common_settings_config = [
        {'label': _("Распознавание", "Recognition"), 'type': 'checkbutton', 'key': 'MIC_ACTIVE',
         'default_checkbutton': False, 'tooltip': _("Включить/выключить распознавание голоса", "Toggle voice recognition"),
         'widget_name': 'MIC_ACTIVE_checkbox'},
        {'label': _("Мгновенная отправка", "Immediate sending"), 'type': 'checkbutton', 'key': 'MIC_INSTANT_SENT', 
         "depends_on": "MIC_ACTIVE", 'default_checkbutton': False, 
         'tooltip': _("Отправлять сообщение сразу после распознавания", "Send message immediately after recognition")},
        {'label': _("Обновить список микрофонов", "Refresh microphone list"), 'type': 'button', 
         'command': lambda: update_mic_list(gui)}
    ]
    
    for config in common_settings_config:
        widget = create_setting_widget(
            gui=gui,
            parent=parent_layout.parent(),
            label=config.get('label'),
            setting_key=config.get('key', ''),
            widget_type=config.get('type', 'entry'),
            options=config.get('options'),
            default=config.get('default', ''),
            default_checkbutton=config.get('default_checkbutton', False),
            validation=config.get('validation'),
            tooltip=config.get('tooltip'),
            command=config.get('command'),
            widget_name=config.get('widget_name'),
            depends_on=config.get('depends_on')
        )
        if widget:
            parent_layout.addWidget(widget)
    
    # --- Контейнер для настроек Google ---
    gui.google_settings_frame = QWidget()
    google_layout = QVBoxLayout(gui.google_settings_frame)
    google_layout.setContentsMargins(0, 0, 0, 0)
    google_layout.setSpacing(0)
    
    info_label = QLabel(_("Google Speech API не требует дополнительных настроек", 
                         "Google Speech API doesn't require additional settings"))
    info_label.setStyleSheet("color: #888; font-style: italic; padding: 10px 0;")
    info_label.setWordWrap(True)
    google_layout.addWidget(info_label)
    
    parent_layout.addWidget(gui.google_settings_frame)
    
    # --- Контейнер для настроек GigaAM ---
    gui.gigaam_settings_frame = QWidget()
    gigaam_layout = QVBoxLayout(gui.gigaam_settings_frame)
    gigaam_layout.setContentsMargins(0, 0, 0, 0)
    gigaam_layout.setSpacing(0)
    
    gigaam_settings_config = [
        {'label': _("Устройство GigaAM", "GigaAM Device"), 'type': 'combobox', 'key': 'GIGAAM_DEVICE',
         'options': ["auto", "cuda", "cpu", "dml"], 'default': "auto",
         'tooltip': _("Устройство для GigaAM. auto - выберет CUDA для NVIDIA и DML/CPU для остальных. dml - только для AMD/Intel.", 
                     "Device for GigaAM. auto - selects CUDA for NVIDIA and DML/CPU for others. dml - for AMD/Intel only."),
         'widget_name': 'GIGAAM_DEVICE_combobox', 'command': lambda: on_gigaam_device_selected(gui)},
        {'label': _("Порог тишины (VAD)", "Silence Threshold (VAD)"), 'type': 'entry', 'key': 'SILENCE_THRESHOLD',
         'default': '0.01', 'validation': gui.validate_float_positive,
         'tooltip': _("Порог громкости для определения начала/конца речи (VAD).", "Volume threshold for Voice Activity Detection (VAD).")},
        {'label': _("Длительность тишины (VAD, сек)", "Silence Duration (VAD, sec)"), 'type': 'entry', 'key': 'SILENCE_DURATION',
         'default': '0.5', 'validation': gui.validate_float_positive,
         'tooltip': _("Длительность тишины для определения конца фразы (VAD).", "Duration of silence to detect end of phrase (VAD).")},
    ]
    
    for config in gigaam_settings_config:
        widget = create_setting_widget(
            gui=gui,
            parent=gui.gigaam_settings_frame,
            label=config.get('label'),
            setting_key=config.get('key', ''),
            widget_type=config.get('type', 'entry'),
            options=config.get('options'),
            default=config.get('default', ''),
            default_checkbutton=config.get('default_checkbutton', False),
            validation=config.get('validation'),
            tooltip=config.get('tooltip'),
            command=config.get('command'),
            widget_name=config.get('widget_name')
        )
        if widget:
            gigaam_layout.addWidget(widget)
    
    parent_layout.addWidget(gui.gigaam_settings_frame)
    
    # Подключаем обработчик изменения типа распознавания
    gui.recognizer_combobox.currentTextChanged.connect(
        lambda text: on_recognizer_type_changed(gui, text)
    )
    
    # Инициализация видимости и проверка установленности модели
    QTimer.singleShot(100, lambda: on_recognizer_type_changed(gui, gui.recognizer_combobox.currentText()))

def on_recognizer_type_changed(gui, recognizer_type):
    """Обработчик изменения типа распознавания"""
    gui._save_setting('RECOGNIZER_TYPE', recognizer_type)
    
    gui.google_settings_frame.setVisible(recognizer_type == "google")
    gui.gigaam_settings_frame.setVisible(recognizer_type == "gigaam")
    
    check_model_installation_status(gui, recognizer_type)

def check_model_installation_status(gui, recognizer_type):
    bus = get_event_bus()
    results = bus.emit_and_wait(
        Events.Speech.CHECK_ASR_MODEL_INSTALLED,
        {'model': recognizer_type},
        timeout=1.0
    )
    if not results:          # не дождались ответа – попробуем позже
        QTimer.singleShot(2000,
            lambda: check_model_installation_status(gui, recognizer_type))
        return
    is_installed = results[0]
    
    if recognizer_type == "google":
        gui.recognizer_status_icon.setText("✅")
        gui.recognizer_status_icon.setToolTip(_("Google Speech API готов к использованию", 
                                               "Google Speech API is ready to use"))
        gui.install_model_button.hide()
    elif recognizer_type == "gigaam":
        if is_installed:
            gui.recognizer_status_icon.setText("✅")
            gui.recognizer_status_icon.setToolTip(_("Модель GigaAM установлена и готова", 
                                                   "GigaAM model is installed and ready"))
            gui.install_model_button.hide()
        else:
            gui.recognizer_status_icon.setText("⚠️")
            gui.recognizer_status_icon.setToolTip(_("Модель GigaAM не установлена", 
                                                   "GigaAM model is not installed"))
            gui.install_model_button.show()

def install_asr_model(gui):
    """Запуск установки модели ASR"""
    event_bus = get_event_bus()
    recognizer_type = gui.recognizer_combobox.currentText()
    
    gui.install_model_button.setEnabled(False)
    gui.install_model_button.setText(_("Установка...", "Installing..."))
    
    # Переменные для отслеживания подписок
    gui._asr_event_subscriptions = []
    
    def on_install_progress(event):
        if event.data.get('model') == recognizer_type:
            gui.asr_install_progress_signal.emit(event.data)

    def on_install_finished(event):
        if event.data.get('model') == recognizer_type:
            gui.asr_install_finished_signal.emit(event.data)
            cleanup_subscriptions()

    def on_install_failed(event):
        if event.data.get('model') == recognizer_type:
            gui.asr_install_failed_signal.emit(event.data)
            cleanup_subscriptions()
    
    def cleanup_subscriptions():
        for event_name, callback in gui._asr_event_subscriptions:
            event_bus.unsubscribe(event_name, callback)
        gui._asr_event_subscriptions.clear()
    
    # Подписываемся на события
    gui._asr_event_subscriptions = [
        (Events.Speech.ASR_MODEL_INSTALL_PROGRESS, on_install_progress),
        (Events.Speech.ASR_MODEL_INSTALL_FINISHED, on_install_finished),
        (Events.Speech.ASR_MODEL_INSTALL_FAILED, on_install_failed)
    ]
    
    for event_name, callback in gui._asr_event_subscriptions:
        event_bus.subscribe(event_name, callback, weak=False)
    
    # Запускаем установку
    event_bus.emit(Events.Speech.INSTALL_ASR_MODEL, {'model': recognizer_type})

def on_mic_selected(gui, full_device_name=None):
    if not hasattr(gui, 'mic_combobox'): 
        return
    
    event_bus = get_event_bus()
    
    if full_device_name is None:
        index = gui.mic_combobox.currentIndex()
        if index >= 0:
            full_device_name = gui.mic_combobox.itemData(index, Qt.ItemDataRole.UserRole)
    
    selection = full_device_name
    
    if selection and '(' in selection:
        try:
            microphone_name = selection.split(" (")[0]
            device_id_match = re.search(r'KATEX_INLINE_OPEN(\d+)KATEX_INLINE_CLOSE$', selection)
            
            if device_id_match:
                device_id = int(device_id_match.group(1))
                
                event_bus.emit(Events.Speech.SET_MICROPHONE, {
                    'name': microphone_name,
                    'device_id': device_id
                })
                
                if gui.settings.get("MIC_ACTIVE", False):
                    event_bus.emit(Events.Speech.RESTART_SPEECH_RECOGNITION, {'device_id': device_id})
                        
        except Exception as e:
            logger.error(f"Ошибка выбора микрофона: {e}")

def on_gigaam_device_selected(gui):
    if not hasattr(gui, 'GIGAAM_DEVICE_combobox'): 
        return
    device = gui.GIGAAM_DEVICE_combobox.currentText()
    event_bus = get_event_bus()
    event_bus.emit(Events.Speech.SET_GIGAAM_OPTIONS, {'device': device})
    gui._save_setting("GIGAAM_DEVICE", device)

def update_mic_list(gui):
    if hasattr(gui, 'mic_combobox'):
        event_bus = get_event_bus()
        
        current_index = gui.mic_combobox.currentIndex()
        current_full_name = None
        if current_index >= 0:
            current_full_name = gui.mic_combobox.itemData(current_index, Qt.ItemDataRole.UserRole)
        
        gui.mic_combobox.clear()
        
        results = event_bus.emit_and_wait(Events.Speech.REFRESH_MICROPHONE_LIST, timeout=1.0)
        new_list = results[0] if results else [_("Ошибка загрузки", "Loading error")]
        
        for mic_name in new_list:
            display_name = mic_name
            if len(mic_name) > 40:
                display_name = mic_name[:37] + "..."
            gui.mic_combobox.addItem(display_name)
            index = gui.mic_combobox.count() - 1
            gui.mic_combobox.setItemData(index, mic_name, Qt.ItemDataRole.UserRole)
            gui.mic_combobox.setItemData(index, mic_name, Qt.ItemDataRole.ToolTipRole)
        
        if current_full_name:
            for i in range(gui.mic_combobox.count()):
                if gui.mic_combobox.itemData(i, Qt.ItemDataRole.UserRole) == current_full_name:
                    gui.mic_combobox.setCurrentIndex(i)
                    gui.mic_combobox.setToolTip(current_full_name)
                    break

def load_mic_settings(gui):
    try:
        event_bus = get_event_bus()
        
        device_id = gui.settings.get("NM_MICROPHONE_ID", 0)
        device_name = gui.settings.get("NM_MICROPHONE_NAME", "")
        
        full_device_name = f"{device_name} ({device_id})"

        if hasattr(gui, 'mic_combobox'):
            found = False
            for i in range(gui.mic_combobox.count()):
                if gui.mic_combobox.itemData(i, Qt.ItemDataRole.UserRole) == full_device_name:
                    gui.mic_combobox.setCurrentIndex(i)
                    gui.mic_combobox.setToolTip(full_device_name)
                    found = True
                    break
            
            if not found and gui.mic_combobox.count() > 0:
                gui.mic_combobox.setCurrentIndex(0)
                gui.mic_combobox.setToolTip(gui.mic_combobox.itemData(0, Qt.ItemDataRole.UserRole))
            
            event_bus.emit(Events.Speech.SET_MICROPHONE, {
                'name': device_name,
                'device_id': device_id
            })

        if gui.settings.get("MIC_ACTIVE", False):
            gui._save_setting('MIC_ACTIVE', True)

    except Exception as e:
        logger.error(f"Ошибка загрузки настроек микрофона: {e}")