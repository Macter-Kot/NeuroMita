import sounddevice as sd
import time
from handlers.asr_handler import SpeechRecognition
from main_logger import logger

class SpeechController:
    def __init__(self, main_controller):
        self.main = main_controller
        self.selected_microphone = ""
        self.device_id = 0
        self.mic_recognition_active = False
        
        initial_recognizer_type = self.main.settings.get("RECOGNIZER_TYPE", "google")
        initial_vosk_model = self.main.settings.get("VOSK_MODEL", "vosk-model-ru-0.10")

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
            self.main.update_status_colors()
        elif key == "RECOGNIZER_TYPE":
            SpeechRecognition.active = False
            time.sleep(0.1)

            SpeechRecognition.set_recognizer_type(value)

            if self.main.settings.get("MIC_ACTIVE", False):
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
        if bool(self.main.settings.get("SILERO_USE")) and self.main.audio_controller.textToTalk:
            self.main.audio_controller.voice_text()

        if self.main.capture_controller.image_request_timer_running:
            self.main.capture_controller.send_interval_image()

        if bool(self.main.settings.get("MIC_INSTANT_SENT")):
            if not self.main.audio_controller.waiting_answer:
                text_from_recognition = SpeechRecognition.receive_text()
                if text_from_recognition:
                    self.main.view.user_entry.insertPlainText(text_from_recognition)
                    self.main.user_input = self.main.view.user_entry.toPlainText().strip()
                    if not self.main.dialog_active:
                        self.send_instantly()

        elif bool(self.main.settings.get("MIC_ACTIVE")) and self.main.view.user_entry:
            text_from_recognition = SpeechRecognition.receive_text()
            if text_from_recognition:
                self.main.view.user_entry.insertPlainText(text_from_recognition)
                self.main.user_input = self.main.view.user_entry.toPlainText().strip()
                
    def send_instantly(self):
        try:
            if self.main.ConnectedToGame:
                self.main.instant_send = True
            else:
                self.main.view.send_message()

            SpeechRecognition._text_buffer.clear()
            SpeechRecognition._current_text = ""
        except Exception as e:
            logger.info(f"Ошибка обработки текста: {str(e)}")