import re
from PyQt6.QtWidgets import QComboBox, QCheckBox

from gui_templates import create_settings_section
from main_logger import logger
from speech_recognition import SpeechRecognition
from utils import getTranslationVariant as _
import sounddevice as sd

def setup_microphone_controls(gui, parent_layout):
    mic_settings = [
        {'label': _("Микрофон", "Microphone"), 'type': 'combobox', 'key': 'MIC_DEVICE',
         'options': get_microphone_list(), 'default': get_microphone_list()[0] if get_microphone_list() else "",
         'command': lambda: on_mic_selected(gui), 'widget_name': 'mic_combobox'},
        {'label': _("Тип распознавания", "Recognition Type"), 'type': 'combobox', 'key': 'RECOGNIZER_TYPE',
         'options': ["google", "vosk", "gigaam"], 'default': "google",
         'tooltip': _("Выберите движок распознавания речи", "Select speech recognition engine"),
         'command': lambda: update_vosk_model_visibility(gui, gui.settings.get('RECOGNIZER_TYPE'))},
        # {'label': _("Модель Vosk", "Vosk Model"), 'type': 'combobox', 'key': 'VOSK_MODEL',
        #  'options': ["vosk-model-ru-0.10"], 'default': "vosk-model-ru-0.10",
        #  'tooltip': _("Выберите модель Vosk.", "Select Vosk model."), 'widget_name': 'VOSK_MODEL_frame'},
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
    
    update_vosk_model_visibility(gui, gui.settings.get('RECOGNIZER_TYPE'))

def get_microphone_list():
    try:
        devices = sd.query_devices()
        input_devices = [f"{d['name']} ({i})" for i, d in enumerate(devices) if d['max_input_channels'] > 0]
        return input_devices or [_("Микрофоны не найдены", "No microphones found")]
    except Exception as e:
        logger.info(f"Ошибка получения списка микрофонов: {e}")
        return [_("Ошибка загрузки", "Loading error")]

def update_vosk_model_visibility(gui, recognizer_type):
    show_vosk = recognizer_type == "vosk"
    if hasattr(gui, 'VOSK_MODEL_frame'):
        gui.VOSK_MODEL_frame.setVisible(show_vosk)
    else:
        # Поскольку виджет может быть закомментирован, это предупреждение не является критичным.
        # logger.warning("Vosk model widget frame not found for visibility update.")
        pass

def on_mic_selected(gui):
    if not hasattr(gui, 'mic_combobox'): return
    selection = gui.mic_combobox.currentText()
    if selection and '(' in selection:
        try:
            gui.selected_microphone = selection.split(" (")[0]
            device_id_match = re.search(r'\((\d+)\)$', selection)
            if device_id_match:
                device_id = int(device_id_match.group(1))
                gui.device_id = device_id
                logger.info(f"Выбран микрофон: {gui.selected_microphone} (ID: {device_id})")
                gui.settings.set("NM_MICROPHONE_ID", device_id)
                gui.settings.set("NM_MICROPHONE_NAME", gui.selected_microphone)
                gui.settings.save_settings()
        except (AttributeError, IndexError, ValueError) as e:
            logger.error(f"Could not parse microphone selection '{selection}': {e}")

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
        device_id = gui.settings.get("NM_MICROPHONE_ID", 0)
        device_name = gui.settings.get("NM_MICROPHONE_NAME", "")
        
        all_devices = get_microphone_list()
        full_device_name = f"{device_name} ({device_id})"

        if hasattr(gui, 'mic_combobox'):
            if full_device_name in all_devices:
                gui.mic_combobox.setCurrentText(full_device_name)
            elif all_devices:
                gui.mic_combobox.setCurrentIndex(0)
            
            gui.device_id = device_id
            gui.selected_microphone = device_name
            logger.info(f"Загружен микрофон: {device_name} (ID: {device_id})")

    except Exception as e:
        logger.info(f"Ошибка загрузки настроек микрофона: {e}")