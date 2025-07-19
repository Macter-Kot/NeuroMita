import sounddevice as sd
import time
from handlers.asr_handler import SpeechRecognition
from main_logger import logger
from core.events import get_event_bus, Events, Event

# Контроллер для управления распознаванием речи

class SpeechController:
    def __init__(self, main_controller):
        self.main = main_controller
        self.settings = None
        self.selected_microphone = ""
        self.device_id = 0
        self.mic_recognition_active = False
        self.instant_send = False
        self.events_bus = get_event_bus()
        
        self._subscribe_to_events()
        
    def _subscribe_to_events(self):
        self.events_bus.subscribe("speech_settings_loaded", self._on_speech_settings_loaded, weak=False)
        self.events_bus.subscribe("speech_setting_changed", self._on_speech_setting_changed, weak=False)
        self.events_bus.subscribe(Events.GET_INSTANT_SEND_STATUS, self._on_get_instant_send_status, weak=False)
        self.events_bus.subscribe(Events.SET_INSTANT_SEND_STATUS, self._on_set_instant_send_status, weak=False)
        # НОВАЯ ПОДПИСКА
        self.events_bus.subscribe(Events.SPEECH_TEXT_RECOGNIZED, self._on_speech_text_recognized, weak=False)
        
    def _on_speech_settings_loaded(self, event: Event):
        self.settings = event.data.get('settings')
        
        if self.settings:
            initial_recognizer_type = self.settings.get("RECOGNIZER_TYPE", "google")
            initial_vosk_model = self.settings.get("VOSK_MODEL", "vosk-model-ru-0.10")

            SpeechRecognition.set_recognizer_type(initial_recognizer_type)
            SpeechRecognition.vosk_model = initial_vosk_model
            logger.info(f"Тип распознавателя установлен на: {initial_recognizer_type}")
        
    def _on_speech_setting_changed(self, event: Event):
        key = event.data.get('key')
        value = event.data.get('value')
        self.update_speech_settings(key, value)
    
    def _on_get_instant_send_status(self, event: Event):
        logger.warning("Настройка MIC_INSTANT_SENT: " + str(bool(self.settings.get("MIC_INSTANT_SENT"))))
        return bool(self.settings.get("MIC_INSTANT_SENT"))
    
    def _on_set_instant_send_status(self, event: Event):
        self.instant_send = event.data.get('status', False)
    
    def _on_speech_text_recognized(self, event: Event):
        """Обработчик распознанного текста"""
        text = event.data.get('text', '')
        if not text or not self.settings:
            return
            
        if not bool(self.settings.get("MIC_ACTIVE")):
            return
            
        if bool(self.settings.get("MIC_INSTANT_SENT")):
            if not self.main.audio_controller.waiting_answer:
                logger.warning("Instant send: " + text)
                self.send_instantly(text)
                
        elif self._check_user_entry_exists():
            self._insert_text_to_input(text)
            
    def update_speech_settings(self, key, value):
        if key == "MIC_ACTIVE":
            if bool(value):
                SpeechRecognition.speech_recognition_start(self.device_id, self.main.loop)
                self.mic_recognition_active = True
            else:
                SpeechRecognition.speech_recognition_stop()
                self.mic_recognition_active = False
            self.events_bus.emit(Events.UPDATE_STATUS_COLORS)
        elif key == "RECOGNIZER_TYPE":
            SpeechRecognition.active = False
            time.sleep(0.1)

            SpeechRecognition.set_recognizer_type(value)
            logger.info(f"Тип распознавателя установлен на: {value}")

            if self.settings and self.settings.get("MIC_ACTIVE", False):
                SpeechRecognition.active = True
                SpeechRecognition.speech_recognition_start(self.device_id, self.main.loop)
        elif key == "VOSK_MODEL":
            SpeechRecognition.vosk_model = value
        elif key == "SILENCE_THRESHOLD":
            SpeechRecognition.SILENCE_THRESHOLD = float(value)
        elif key == "SILENCE_DURATION":
            SpeechRecognition.SILENCE_DURATION = float(value)
        elif key == "VOSK_PROCESS_INTERVAL":
            SpeechRecognition.VOSK_PROCESS_INTERVAL = float(value)
    
    def send_instantly(self, text_to_send):
        try:
            llm_status_result = self.events_bus.emit_and_wait(Events.GET_LLM_PROCESSING_STATUS, timeout=0.1)
            llm_processing = llm_status_result[0] if llm_status_result else False
            
            if llm_processing:
                logger.debug("Пропускаем instant send - LLM обрабатывает запрос")
                return
            
            if not text_to_send:
                return
                
            self.events_bus.emit(Events.UPDATE_CHAT_UI, {
                'role': 'user',
                'response': text_to_send,
                'is_initial': False,
                'emotion': ''
            })
            
            if self.main.ConnectedToGame:
                self.instant_send = True
                
            self.events_bus.emit(Events.SEND_MESSAGE, {
                'user_input': text_to_send,
                'system_input': '',
                'image_data': []
            })
            
        except Exception as e:
            logger.info(f"Ошибка обработки текста: {str(e)}")
            
    def _insert_text_to_input(self, text):
        self.events_bus.emit(Events.INSERT_TEXT_TO_INPUT, {"text": text})
        
    def _get_user_input(self):
        result = self.events_bus.emit_and_wait(Events.GET_USER_INPUT, timeout=0.5)
        return result[0] if result else ""
        
    def _check_user_entry_exists(self):
        result = self.events_bus.emit_and_wait(Events.CHECK_USER_ENTRY_EXISTS, timeout=0.5)
        return result[0] if result else False