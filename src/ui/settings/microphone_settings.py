import re
from PyQt6.QtWidgets import QComboBox, QCheckBox, QWidget, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt

from ui.gui_templates import create_setting_widget, create_settings_direct, create_section_header
from main_logger import logger
from utils import getTranslationVariant as _
from core.events import get_event_bus, Events

def setup_microphone_controls(gui, parent_layout):
    create_section_header(parent_layout, _("Настройки микрофона", "Microphone Settings"))
    
    event_bus = get_event_bus()
    
    mic_row = QWidget()
    mic_row.setMaximumWidth(380)
    mic_layout = QHBoxLayout(mic_row)
    mic_layout.setContentsMargins(0, 2, 0, 2)
    mic_layout.setSpacing(10)
    
    mic_label = QLabel(_("Микрофон", "Microphone"))
    mic_label.setMinimumWidth(140)
    mic_label.setMaximumWidth(140)
    mic_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    
    gui.mic_combobox = QComboBox()
    gui.mic_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    gui.mic_combobox.setMinimumWidth(150)
    gui.mic_combobox.setMaximumWidth(220)
    
    results = event_bus.emit_and_wait(Events.GET_MICROPHONE_LIST, timeout=1.0)
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
    mic_layout.addStretch()
    parent_layout.addWidget(mic_row)
    
    mic_settings = [
        {'label': _("Тип распознавания", "Recognition Type"), 'type': 'combobox', 'key': 'RECOGNIZER_TYPE',
         'options': ["google", "gigaam"], 'default': "google",
         'tooltip': _("Выберите движок распознавания речи", "Select speech recognition engine"),
         'command': lambda: update_recognizer_specific_widgets(gui, gui.settings.get('RECOGNIZER_TYPE'))},
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
        {'label': _("Интервал обработки Vosk (сек)", "Vosk Process Interval (sec)"), 'type': 'entry', 'key': 'VOSK_PROCESS_INTERVAL',
         'default': '0.1', 'validation': gui.validate_float_positive,
         'tooltip': _("Интервал, с которым Vosk обрабатывает аудио в режиме реального времени.", 
                     "Interval at which Vosk processes audio in live recognition mode.")},
        {'label': _("Распознавание", "Recognition"), 'type': 'checkbutton', 'key': 'MIC_ACTIVE',
         'default_checkbutton': False, 'tooltip': _("Включить/выключить распознавание голоса", "Toggle voice recognition")},
        {'label': _("Мгновенная отправка", "Immediate sending"), 'type': 'checkbutton', 'key': 'MIC_INSTANT_SENT', 
         "depends_on": "MIC_ACTIVE", 'default_checkbutton': False, 
         'tooltip': _("Отправлять сообщение сразу после распознавания", "Send message immediately after recognition")},
        {'label': _("Обновить список", "Refresh list"), 'type': 'button', 'command': lambda: update_mic_list(gui)}
    ]
    
    for config in mic_settings:
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
            widget.setMaximumWidth(380)
            parent_layout.addWidget(widget)
    
    update_recognizer_specific_widgets(gui, gui.settings.get('RECOGNIZER_TYPE'))
    
    if hasattr(gui, 'GIGAAM_DEVICE_combobox'):
        gui.GIGAAM_DEVICE_frame = gui.GIGAAM_DEVICE_combobox.parent()

def update_recognizer_specific_widgets(gui, recognizer_type):
    show_vosk = recognizer_type == "vosk"
    show_gigaam = recognizer_type == "gigaam"

    if hasattr(gui, 'VOSK_MODEL_frame'):
        gui.VOSK_MODEL_frame.setVisible(show_vosk)
    
    if hasattr(gui, 'GIGAAM_DEVICE_frame'):
        gui.GIGAAM_DEVICE_frame.setVisible(show_gigaam)

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
            device_id_match = re.search(r'\((\d+)\)$', selection)
            
            if device_id_match:
                device_id = int(device_id_match.group(1))
                
                event_bus.emit(Events.SET_MICROPHONE, {
                    'name': microphone_name,
                    'device_id': device_id
                })
                
                if gui.settings.get("MIC_ACTIVE", False):
                    event_bus.emit(Events.RESTART_SPEECH_RECOGNITION, {'device_id': device_id})
                        
        except Exception as e:
            logger.error(f"Ошибка выбора микрофона: {e}")

def on_gigaam_device_selected(gui):
    if not hasattr(gui, 'GIGAAM_DEVICE_combobox'): 
        return
    device = gui.GIGAAM_DEVICE_combobox.currentText()
    event_bus = get_event_bus()
    event_bus.emit(Events.SET_GIGAAM_OPTIONS, {'device': device})

def update_mic_list(gui):
    if hasattr(gui, 'mic_combobox'):
        event_bus = get_event_bus()
        
        current_index = gui.mic_combobox.currentIndex()
        current_full_name = None
        if current_index >= 0:
            current_full_name = gui.mic_combobox.itemData(current_index, Qt.ItemDataRole.UserRole)
        
        gui.mic_combobox.clear()
        
        results = event_bus.emit_and_wait(Events.REFRESH_MICROPHONE_LIST, timeout=1.0)
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
            
            event_bus.emit(Events.SET_MICROPHONE, {
                'name': device_name,
                'device_id': device_id
            })

        if gui.settings.get("MIC_ACTIVE", False):
            gui._save_setting('MIC_ACTIVE', True)

    except Exception as e:
        logger.error(f"Ошибка загрузки настроек микрофона: {e}")