import sounddevice as sd
import time
from handlers.asr_handler import SpeechRecognition
from main_logger import logger

from core.events import get_event_bus, Events, Event

class SpeechController:
    def __init__(self, main_controller):
        self.main = main_controller
        self.settings = main_controller.settings
        self.selected_microphone = ""
        self.device_id = 0
        self.mic_recognition_active = False
        self.events_bus = get_event_bus()
        
        initial_recognizer_type = self.settings.get("RECOGNIZER_TYPE", "google")
        initial_vosk_model = self.settings.get("VOSK_MODEL", "vosk-model-ru-0.10")

        SpeechRecognition.set_recognizer_type(initial_recognizer_type)
        SpeechRecognition.vosk_model = initial_vosk_model
        
        # Убрали автоматический запуск здесь — он будет вызван после загрузки настроек в GUI
            
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

            if self.settings.get("MIC_ACTIVE", False):
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
            
    def check_text_to_talk_or_send(self):
        if bool(self.settings.get("SILERO_USE")) and self.main.audio_controller.textToTalk:
            self.main.audio_controller.voice_text()

        if self.main.capture_controller.image_request_timer_running:
            self.main.capture_controller.send_interval_image()

        if bool(self.settings.get("MIC_INSTANT_SENT")):
            if not self.main.audio_controller.waiting_answer:
                text_from_recognition = SpeechRecognition.receive_text()
                if text_from_recognition:
                    # При instant send отправляем текст напрямую из буфера, не трогая user_entry
                    logger.warning("Instant send: " + text_from_recognition)
                    self.send_instantly(text_from_recognition)

        elif bool(self.settings.get("MIC_ACTIVE")) and self._check_user_entry_exists():
            text_from_recognition = SpeechRecognition.receive_text()
            if text_from_recognition:
                self._insert_text_to_input(text_from_recognition)
                self.main.user_input = self._get_user_input()
                
    def send_instantly(self, text_to_send):
        try:
            # Проверяем, не обрабатывается ли уже сообщение LLM
            if self.main.llm_processing:
                logger.debug("Пропускаем instant send - LLM обрабатывает запрос")
                return
            
            if not text_to_send:
                return
                
            # Отображаем сообщение пользователя в чате
            self.events_bus.emit(Events.UPDATE_CHAT_UI, {
                'role': 'user',
                'response': text_to_send,
                'is_initial': False,
                'emotion': ''
            })
            
            if self.main.ConnectedToGame:
                self.main.instant_send = True
                
            # Отправляем сообщение на обработку
            self.events_bus.emit(Events.SEND_MESSAGE, {
                'user_input': text_to_send,
                'system_input': '',
                'image_data': []
            })

            # Очищаем буферы
            SpeechRecognition._text_buffer.clear()
            SpeechRecognition._current_text = ""
            
        except Exception as e:
            logger.info(f"Ошибка обработки текста: {str(e)}")
            
    def _insert_text_to_input(self, text):
        """Вставка текста в поле ввода через события"""
        self.events_bus.emit(Events.INSERT_TEXT_TO_INPUT, {"text": text})
        
    def _get_user_input(self):
        """Получение текста из поля ввода через события"""
        result = self.events_bus.emit_and_wait(Events.GET_USER_INPUT, timeout=0.5)
        return result[0] if result else ""
        
    def _send_message(self):
        """Отправка сообщения через события"""
        self.events_bus.emit(Events.SEND_MESSAGE, {
            'user_input': self.main.user_input,
            'system_input': '',
            'image_data': []
        })
        
    def _check_user_entry_exists(self):
        """Проверка существования поля ввода через события"""
        result = self.events_bus.emit_and_wait(Events.CHECK_USER_ENTRY_EXISTS, timeout=0.5)
        return result[0] if result else False