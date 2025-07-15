import re
from PyQt6.QtWidgets import QComboBox, QCheckBox, QWidget, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt

from ui.gui_templates import create_settings_section, create_setting_widget
from main_logger import logger
from handlers.asr_handler import SpeechRecognition
from utils import getTranslationVariant as _
from core.events import get_event_bus, Events
import sounddevice as sd
import time

def setup_microphone_controls(gui, parent_layout):
    # Создаем основную секцию
    gui.mic_section = create_settings_section(
        gui, parent_layout, 
        _("Настройки микрофона", "Microphone Settings"), 
        []  # Передаем пустой список, виджеты добавим вручную
    )
    
    content_widget = gui.mic_section.content_frame
    content_layout = gui.mic_section.content_layout
    
    # --- Микрофон (специальная обработка для длинных названий) ---
    mic_row = QWidget()
    mic_layout = QHBoxLayout(mic_row)
    mic_layout.setContentsMargins(0, 2, 0, 2)
    mic_layout.setSpacing(10)
    
    mic_label = QLabel(_("Микрофон", "Microphone"))
    mic_label.setMinimumWidth(140)
    mic_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    
    gui.mic_combobox = QComboBox()
    gui.mic_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    gui.mic_combobox.setMaximumWidth(400)  # Ограничиваем максимальную ширину
    
    # Заполняем список микрофонов
    mic_list = get_microphone_list()
    for mic_name in mic_list:
        gui.mic_combobox.addItem(mic_name)
        # Добавляем полное название как tooltip
        index = gui.mic_combobox.count() - 1
        gui.mic_combobox.setItemData(index, mic_name, Qt.ItemDataRole.ToolTipRole)
    
    # Устанавливаем текущее значение
    current_mic = gui.settings.get('MIC_DEVICE', mic_list[0] if mic_list else "")
    gui.mic_combobox.setCurrentText(current_mic)
    gui.mic_combobox.setToolTip(current_mic)
    
    # Подключаем обработчик
    gui.mic_combobox.currentTextChanged.connect(lambda text: (
        gui._save_setting('MIC_DEVICE', text),
        gui.mic_combobox.setToolTip(text),
        on_mic_selected(gui)
    ))
    
    mic_layout.addWidget(mic_label)
    mic_layout.addWidget(gui.mic_combobox, 1)
    content_layout.addWidget(mic_row)
    
    # --- Остальные настройки через шаблон ---
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
            parent=content_widget,
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
            content_layout.addWidget(widget)
    
    # Скрываем/показываем специфичные виджеты
    update_recognizer_specific_widgets(gui, gui.settings.get('RECOGNIZER_TYPE'))
    
    # Также создаем frame для GIGAAM_DEVICE чтобы можно было его скрывать
    if hasattr(gui, 'GIGAAM_DEVICE_combobox'):
        gui.GIGAAM_DEVICE_frame = gui.GIGAAM_DEVICE_combobox.parent()

def get_microphone_list():
    try:
        devices = sd.query_devices()
        input_devices = []
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                device_name = f"{d['name']} ({i})"
                input_devices.append(device_name)
        return input_devices or [_("Микрофоны не найдены", "No microphones found")]
    except Exception as e:
        logger.error(f"Ошибка получения списка микрофонов: {e}")
        return [_("Ошибка загрузки", "Loading error")]

def update_recognizer_specific_widgets(gui, recognizer_type):
    show_vosk = recognizer_type == "vosk"
    show_gigaam = recognizer_type == "gigaam"

    if hasattr(gui, 'VOSK_MODEL_frame'):
        gui.VOSK_MODEL_frame.setVisible(show_vosk)
    
    if hasattr(gui, 'GIGAAM_DEVICE_frame'):
        gui.GIGAAM_DEVICE_frame.setVisible(show_gigaam)

def on_mic_selected(gui):
    if not hasattr(gui, 'mic_combobox'): 
        return
    
    event_bus = get_event_bus()
    selection = gui.mic_combobox.currentText()
    
    if selection and '(' in selection:
        try:
            microphone_name = selection.split(" (")[0]
            device_id_match = re.search(r'\((\d+)\)$', selection)
            
            if device_id_match:
                device_id = int(device_id_match.group(1))
                
                # Устанавливаем микрофон через событие
                event_bus.emit(Events.SET_MICROPHONE, {
                    'name': microphone_name,
                    'device_id': device_id
                })
                
                # Перезапускаем распознавание если активно
                if gui.settings.get("MIC_ACTIVE", False):
                    def restart_recognition():
                        try:
                            event_bus.emit(Events.STOP_SPEECH_RECOGNITION)
                            # Ожидаем завершения предыдущей задачи
                            start_time = time.time()
                            while SpeechRecognition._is_running and time.time() - start_time < 5:
                                time.sleep(0.1)
                            if SpeechRecognition._is_running:
                                logger.warning("Предыдущее распознавание не остановилось вовремя, принудительная остановка.")
                            event_bus.emit(Events.START_SPEECH_RECOGNITION, {'device_id': device_id})
                            logger.info("Распознавание перезапущено с новым микрофоном")
                        except Exception as e:
                            logger.error(f"Ошибка перезапуска распознавания: {e}")
                    
                    # Запускаем в отдельном потоке чтобы избежать блокировки UI
                    import threading
                    threading.Thread(target=restart_recognition, daemon=True).start()
                        
        except Exception as e:
            logger.error(f"Ошибка выбора микрофона: {e}")

def on_gigaam_device_selected(gui):
    if not hasattr(gui, 'GIGAAM_DEVICE_combobox'): 
        return
    device = gui.GIGAAM_DEVICE_combobox.currentText()
    SpeechRecognition.set_gigaam_options(device=device)
    logger.info(f"Выбрано устройство для GigaAM: {device}")

def update_mic_list(gui):
    if hasattr(gui, 'mic_combobox'):
        current_selection = gui.mic_combobox.currentText()
        gui.mic_combobox.clear()
        new_list = get_microphone_list()
        
        for mic_name in new_list:
            gui.mic_combobox.addItem(mic_name)
            # Добавляем полное название как tooltip
            index = gui.mic_combobox.count() - 1
            gui.mic_combobox.setItemData(index, mic_name, Qt.ItemDataRole.ToolTipRole)
        
        if current_selection in new_list:
            gui.mic_combobox.setCurrentText(current_selection)
            gui.mic_combobox.setToolTip(current_selection)

def load_mic_settings(gui):
    try:
        event_bus = get_event_bus()
        
        device_id = gui.settings.get("NM_MICROPHONE_ID", 0)
        device_name = gui.settings.get("NM_MICROPHONE_NAME", "")
        
        all_devices = get_microphone_list()
        full_device_name = f"{device_name} ({device_id})"

        if hasattr(gui, 'mic_combobox'):
            if full_device_name in all_devices:
                gui.mic_combobox.setCurrentText(full_device_name)
                gui.mic_combobox.setToolTip(full_device_name)
            elif all_devices:
                gui.mic_combobox.setCurrentIndex(0)
                gui.mic_combobox.setToolTip(gui.mic_combobox.currentText())
            
            # Устанавливаем микрофон через событие
            event_bus.emit(Events.SET_MICROPHONE, {
                'name': device_name,
                'device_id': device_id
            })

        # После загрузки настроек запускаем распознавание, если активно
        if gui.settings.get("MIC_ACTIVE", False):
            event_bus.emit(Events.UPDATE_SPEECH_SETTINGS, {
                'key': "MIC_ACTIVE",
                'value': True
            })

    except Exception as e:
        logger.error(f"Ошибка загрузки настроек микрофона: {e}")