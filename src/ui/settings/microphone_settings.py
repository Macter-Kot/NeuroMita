import re
from PyQt6.QtWidgets import QComboBox, QCheckBox

from ui.gui_templates import create_settings_section
from main_logger import logger
from handlers.asr_handler import SpeechRecognition
from utils import getTranslationVariant as _
from ui.windows.events import get_event_bus, Events
import sounddevice as sd
import time

def setup_microphone_controls(gui, parent_layout):
    mic_settings = [
        {'label': _("Микрофон", "Microphone"), 'type': 'combobox', 'key': 'MIC_DEVICE',
         'options': get_microphone_list(), 'default': get_microphone_list()[0] if get_microphone_list() else "",
         'command': lambda: on_mic_selected(gui), 'widget_name': 'mic_combobox'},
        {'label': _("Тип распознавания", "Recognition Type"), 'type': 'combobox', 'key': 'RECOGNIZER_TYPE',
         'options': ["google", "gigaam"], 'default': "google",
         'tooltip': _("Выберите движок распознавания речи", "Select speech recognition engine"),
         'command': lambda: update_recognizer_specific_widgets(gui, gui.settings.get('RECOGNIZER_TYPE'))},
        {'label': _("Устройство GigaAM", "GigaAM Device"), 'type': 'combobox', 'key': 'GIGAAM_DEVICE',
         'options': ["auto", "cuda", "cpu", "dml"], 'default': "auto",
         'tooltip': _("Устройство для GigaAM. auto - выберет CUDA для NVIDIA и DML/CPU для остальных. dml - только для AMD/Intel.", "Device for GigaAM. auto - selects CUDA for NVIDIA and DML/CPU for others. dml - for AMD/Intel only."),
         'widget_name': 'GIGAAM_DEVICE_frame', 'command': lambda: on_gigaam_device_selected(gui)},
        {'label': _("Порог тишины (VAD)", "Silence Threshold (VAD)"), 'type': 'entry', 'key': 'SILENCE_THRESHOLD',
         'default': '0.01', 'validation': gui.validate_float_positive,
         'tooltip': _("Порог громкости для определения начала/конца речи (VAD).", "Volume threshold for Voice Activity Detection (VAD).")},
        {'label': _("Длительность тишины (VAD, сек)", "Silence Duration (VAD, sec)"), 'type': 'entry', 'key': 'SILENCE_DURATION',
         'default': '0.5', 'validation': gui.validate_float_positive,
         'tooltip': _("Длительность тишины для определения конца фразы (VAD).", "Duration of silence to detect end of phrase (VAD).")},
        {'label': _("Интервал обработки Vosk (сек)", "Vosk Process Interval (sec)"), 'type': 'entry', 'key': 'VOSK_PROCESS_INTERVAL',
         'default': '0.1', 'validation': gui.validate_float_positive,
         'tooltip': _("Интервал, с которым Vosk обрабатывает аудио в режиме реального времени.", "Interval at which Vosk processes audio in live recognition mode.")},
        {'label': _("Распознавание", "Recognition"), 'type': 'checkbutton', 'key': 'MIC_ACTIVE',
         'default_checkbutton': False, 'tooltip': _("Включить/выключить распознавание голоса", "Toggle voice recognition")},
        {'label': _("Мгновенная отправка", "Immediate sending"), 'type': 'checkbutton', 'key': 'MIC_INSTANT_SENT',
         'default_checkbutton': False, 'tooltip': _("Отправлять сообщение сразу после распознавания", "Send message immediately after recognition")},
        {'label': _("Обновить список", "Refresh list"), 'type': 'button', 'command': lambda: update_mic_list(gui)}
    ]

    gui.mic_section = create_settings_section(gui, parent_layout, _("Настройки микрофона", "Microphone Settings"), mic_settings)
    
    update_recognizer_specific_widgets(gui, gui.settings.get('RECOGNIZER_TYPE'))

def get_microphone_list():
    try:
        devices = sd.query_devices()
        input_devices = [f"{d['name']} ({i})" for i, d in enumerate(devices) if d['max_input_channels'] > 0]
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
        gui.mic_combobox.addItems(new_list)
        if current_selection in new_list:
            gui.mic_combobox.setCurrentText(current_selection)

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
            elif all_devices:
                gui.mic_combobox.setCurrentIndex(0)
            
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