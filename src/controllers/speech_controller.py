import sounddevice as sd
import time
import threading
from handlers.asr_handler import SpeechRecognition
from main_logger import logger
from core.events import get_event_bus, Events, Event


class SpeechController:
    def __init__(self):
        self.settings = None
        self.selected_microphone = ""
        self.device_id = 0
        self.mic_recognition_active = False
        self.instant_send = False
        self.events_bus = get_event_bus()
        self.recognized_text = ""
        
        self._subscribe_to_events()
        
    def _subscribe_to_events(self):
        self.events_bus.subscribe("speech_settings_loaded", self._on_speech_settings_loaded, weak=False)
        self.events_bus.subscribe("setting_changed", self._on_setting_changed, weak=False)
        self.events_bus.subscribe(Events.Speech.GET_INSTANT_SEND_STATUS, self._on_get_instant_send_status, weak=False)
        self.events_bus.subscribe(Events.Speech.SET_INSTANT_SEND_STATUS, self._on_set_instant_send_status, weak=False)
        self.events_bus.subscribe(Events.Speech.SPEECH_TEXT_RECOGNIZED, self._on_speech_text_recognized, weak=False)
        self.events_bus.subscribe(Events.Chat.SEND_MESSAGE, self._on_sent_message, weak=False)
        self.events_bus.subscribe(Events.Speech.GET_MIC_STATUS, self._on_get_mic_status, weak=False)
        self.events_bus.subscribe(Events.Speech.GET_USER_INPUT, self._on_get_user_input, weak=False)
        
        self.events_bus.subscribe(Events.Speech.SET_MICROPHONE, self._on_set_microphone, weak=False)
        self.events_bus.subscribe(Events.Speech.START_SPEECH_RECOGNITION, self._on_start_speech_recognition, weak=False)
        self.events_bus.subscribe(Events.Speech.STOP_SPEECH_RECOGNITION, self._on_stop_speech_recognition, weak=False)
        
        self.events_bus.subscribe(Events.Speech.GET_MICROPHONE_LIST, self._on_get_microphone_list, weak=False)
        self.events_bus.subscribe(Events.Speech.REFRESH_MICROPHONE_LIST, self._on_refresh_microphone_list, weak=False)
        self.events_bus.subscribe(Events.Speech.SET_GIGAAM_OPTIONS, self._on_set_gigaam_options, weak=False)
        self.events_bus.subscribe(Events.Speech.RESTART_SPEECH_RECOGNITION, self._on_restart_speech_recognition, weak=False)

    def _on_sent_message(self, event: Event):
        self.recognized_text = ""

    def _on_get_user_input(self, event: Event):
        return self.recognized_text
        
    def _on_speech_settings_loaded(self, event: Event):
        self.settings = event.data.get('settings')
        
        if self.settings:
            initial_recognizer_type = self.settings.get("RECOGNIZER_TYPE", "google")
            initial_vosk_model = self.settings.get("VOSK_MODEL", "vosk-model-ru-0.10")

            SpeechRecognition.set_recognizer_type(initial_recognizer_type)
            SpeechRecognition.vosk_model = initial_vosk_model
            logger.info(f"Тип распознавателя установлен на: {initial_recognizer_type}")
            
            # Инициализируем микрофон из настроек
            device_id = self.settings.get("NM_MICROPHONE_ID", 0)
            device_name = self.settings.get("NM_MICROPHONE_NAME", "")
            
            if device_name:
                self.selected_microphone = device_name
                self.device_id = device_id
                logger.info(f"Загружен микрофон из настроек: {device_name} (ID: {device_id})")
        
    def _on_setting_changed(self, event: Event):
        key = event.data.get('key')
        value = event.data.get('value')
        
        if key == "MIC_ACTIVE":
            if bool(value):
                # Убедимся, что у нас есть правильный device_id
                if self.device_id is None:
                    self.device_id = 0
                
                loop = self.events_bus.emit_and_wait(Events.Core.GET_EVENT_LOOP, timeout=1.0)[0]
                SpeechRecognition.speech_recognition_start(self.device_id, loop)
                self.mic_recognition_active = True
            else:
                SpeechRecognition.speech_recognition_stop()
                self.mic_recognition_active = False
            self.events_bus.emit(Events.GUI.UPDATE_STATUS_COLORS)
        elif key == "RECOGNIZER_TYPE":
            # Останавливаем текущее распознавание
            if self.mic_recognition_active:
                SpeechRecognition.speech_recognition_stop()
                time.sleep(0.1)

            SpeechRecognition.set_recognizer_type(value)
            logger.info(f"Тип распознавателя установлен на: {value}")

            # Перезапускаем только если было активно
            if self.settings and self.settings.get("MIC_ACTIVE", False) and self.mic_recognition_active:
                loop = self.events_bus.emit_and_wait(Events.Core.GET_EVENT_LOOP, timeout=1.0)[0]
                SpeechRecognition.speech_recognition_start(self.device_id, loop)
        elif key == "VOSK_MODEL":
            SpeechRecognition.vosk_model = value
        elif key == "SILENCE_THRESHOLD":
            SpeechRecognition.SILENCE_THRESHOLD = float(value)
        elif key == "SILENCE_DURATION":
            SpeechRecognition.SILENCE_DURATION = float(value)
        elif key == "VOSK_PROCESS_INTERVAL":
            SpeechRecognition.VOSK_PROCESS_INTERVAL = float(value)
        elif key == "GIGAAM_DEVICE":
            SpeechRecognition.set_gigaam_options(device=value)
    
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
            
            waiting_answer = self.events_bus.emit_and_wait(Events.Audio.GET_WAITING_ANSWER)[0]
            if not waiting_answer:
                logger.warning("Instant send: " + text)
                self.send_instantly(text)
            else:
                self.recognized_text += text
                
        elif self._check_user_entry_exists():
            connected_to_game = self.events_bus.emit_and_wait(Events.Server.GET_GAME_CONNECTION)[0]
            if connected_to_game:
                self.recognized_text += text
            else:    
                self._insert_text_to_input(text)

    def _on_get_mic_status(self, event: Event):
        return self.mic_recognition_active
    
    def _on_set_microphone(self, event: Event):
        microphone_name = event.data.get('name')
        device_id = event.data.get('device_id')
        
        if microphone_name and device_id is not None:
            self.selected_microphone = microphone_name
            self.device_id = device_id
            
            if self.settings:
                self.settings.set("NM_MICROPHONE_ID", device_id)
                self.settings.set("NM_MICROPHONE_NAME", microphone_name)
                self.settings.save_settings()
            
            logger.info(f"Выбран микрофон: {microphone_name} (ID: {device_id})")
    
    def _on_start_speech_recognition(self, event: Event):
        device_id = event.data.get('device_id', self.device_id)
        
        try:
            loop_result = self.events_bus.emit_and_wait(Events.Core.GET_EVENT_LOOP, timeout=1.0)
            loop = loop_result[0] if loop_result else None
            
            if loop:
                SpeechRecognition.speech_recognition_start(device_id, loop)
                logger.info("Распознавание речи запущено")
            else:
                logger.error("Не удалось получить event loop для запуска распознавания речи")
        except Exception as e:
            logger.error(f"Ошибка запуска распознавания речи: {e}")
    
    def _on_stop_speech_recognition(self, event: Event):
        try:
            SpeechRecognition.speech_recognition_stop()
            logger.info("Распознавание речи остановлено")
        except Exception as e:
            logger.error(f"Ошибка остановки распознавания речи: {e}")
    
    def _on_get_microphone_list(self, event: Event):
        try:
            devices = sd.query_devices()
            input_devices = []
            for i, d in enumerate(devices):
                if d['max_input_channels'] > 0:
                    device_name = f"{d['name']} ({i})"
                    input_devices.append(device_name)
            return input_devices or ["Микрофоны не найдены"]
        except Exception as e:
            logger.error(f"Ошибка получения списка микрофонов: {e}")
            return ["Ошибка загрузки"]
    
    def _on_refresh_microphone_list(self, event: Event):
        return self._on_get_microphone_list(event)
    
    def _on_set_gigaam_options(self, event: Event):
        device = event.data.get('device', 'auto')
        SpeechRecognition.set_gigaam_options(device=device)
        logger.info(f"Выбрано устройство для GigaAM: {device}")
    
    def _on_restart_speech_recognition(self, event: Event):
        device_id = event.data.get('device_id', self.device_id)
        
        def restart_recognition():
            try:
                self.events_bus.emit(Events.Speech.STOP_SPEECH_RECOGNITION)
                start_time = time.time()
                while SpeechRecognition._is_running and time.time() - start_time < 5:
                    time.sleep(0.1)
                if SpeechRecognition._is_running:
                    logger.warning("Предыдущее распознавание не остановилось вовремя, принудительная остановка.")
                self.events_bus.emit(Events.Speech.START_SPEECH_RECOGNITION, {'device_id': device_id})
                logger.info("Распознавание перезапущено с новым микрофоном")
            except Exception as e:
                logger.error(f"Ошибка перезапуска распознавания: {e}")
        
        threading.Thread(target=restart_recognition, daemon=True).start()
    
    def send_instantly(self, text_to_send):
        try:
            llm_status_result = self.events_bus.emit_and_wait(Events.Model.GET_LLM_PROCESSING_STATUS, timeout=0.1)
            llm_processing = llm_status_result[0] if llm_status_result else False
            
            if llm_processing:
                logger.debug("Пропускаем instant send - LLM обрабатывает запрос")
                return
            
            if not text_to_send:
                return
                
            self.events_bus.emit(Events.GUI.UPDATE_CHAT_UI, {
                'role': 'user',
                'response': text_to_send,
                'is_initial': False,
                'emotion': ''
            })
            
                
            self.events_bus.emit(Events.Chat.SEND_MESSAGE, {
                'user_input': text_to_send,
                'system_input': '',
                'image_data': []
            })
            
        except Exception as e:
            logger.info(f"Ошибка обработки текста: {str(e)}")
            
    def _insert_text_to_input(self, text):
        self.events_bus.emit(Events.GUI.INSERT_TEXT_TO_INPUT, {"text": text})
        
    def _get_user_input(self):
        result = self.events_bus.emit_and_wait(Events.Speech.GET_USER_INPUT, timeout=0.5)
        return result[0] if result else ""
        
    def _check_user_entry_exists(self):
        result = self.events_bus.emit_and_wait(Events.GUI.CHECK_USER_ENTRY_EXISTS, timeout=0.5)
        return result[0] if result else False