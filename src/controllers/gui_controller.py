import time
from pathlib import Path
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox
from main_logger import logger
from core.events import get_event_bus, Events, Event
from utils.ffmpeg_installer import install_ffmpeg

# Контроллер для GUI

class GuiController:
    def __init__(self, main_controller, view):
        self.main_controller = main_controller
        self.view = view
        self.event_bus = get_event_bus()
        
        self.voice_language_var = None
        self.local_voice_combobox = None
        self.debug_window = None
        self.mic_combobox = None
        self.chat_window = None
        self.token_count_label = None
        self.user_entry = None
        self.attachment_label = None
        self.attach_button = None
        self.send_screen_button = None
        self.ffmpeg_install_popup = None
        self.game_connected_checkbox_var = False
        
        logger.info(f"GuiController инициализирован с view типа: {type(self.view)}")
        self._subscribe_to_events()
        self._connect_view_signals()
        logger.info("GuiController подписался на события")

        QTimer.singleShot(100, self.check_and_install_ffmpeg)
        
    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.UPDATE_STATUS_COLORS, self._on_update_status_colors, weak=False)
        self.event_bus.subscribe(Events.CLEAR_USER_INPUT_UI, self._on_clear_user_input_ui, weak=False)
        self.event_bus.subscribe(Events.UPDATE_CHAT, self._on_update_chat, weak=False)
        self.event_bus.subscribe(Events.UPDATE_CHAT_UI, self._on_update_chat_ui, weak=False)
        self.event_bus.subscribe(Events.PREPARE_STREAM_UI, self._on_prepare_stream_ui, weak=False)
        self.event_bus.subscribe(Events.APPEND_STREAM_CHUNK_UI, self._on_append_stream_chunk_ui, weak=False)
        self.event_bus.subscribe(Events.FINISH_STREAM_UI, self._on_finish_stream_ui, weak=False)
        self.event_bus.subscribe(Events.UPDATE_STATUS, self._on_update_status, weak=False)
        self.event_bus.subscribe(Events.UPDATE_DEBUG_INFO, self._on_update_debug_info, weak=False)
        self.event_bus.subscribe(Events.UPDATE_TOKEN_COUNT, self._on_update_token_count, weak=False)
        self.event_bus.subscribe(Events.CHECK_AND_INSTALL_FFMPEG, self._on_check_and_install_ffmpeg, weak=False)
        
        self.event_bus.subscribe(Events.ON_STARTED_RESPONSE_GENERATION, self._on_started_response, weak=False)
        self.event_bus.subscribe(Events.ON_SUCCESSFUL_RESPONSE, self._on_successful_response, weak=False)
        self.event_bus.subscribe(Events.ON_FAILED_RESPONSE_ATTEMPT, self._on_failed_response_attempt, weak=False)
        self.event_bus.subscribe(Events.ON_FAILED_RESPONSE, self._on_failed_response, weak=False)
        
        self.event_bus.subscribe(Events.INSERT_TEXT_TO_INPUT, self._on_insert_text_to_input, weak=False)
        self.event_bus.subscribe(Events.CHECK_USER_ENTRY_EXISTS, self._on_check_user_entry_exists, weak=False)

        self.event_bus.subscribe(Events.SWITCH_VOICEOVER_SETTINGS, self._on_switch_voiceover_settings, weak=False)
        self.event_bus.subscribe(Events.SHOW_INFO_MESSAGE, self._on_show_info_message, weak=False)
        self.event_bus.subscribe(Events.UPDATE_CHAT_FONT_SIZE, self._on_update_chat_font_size, weak=False)
        self.event_bus.subscribe(Events.RELOAD_CHAT_HISTORY, self._on_reload_chat_history, weak=False)
        self.event_bus.subscribe(Events.UPDATE_TOKEN_COUNT_UI, self._on_update_token_count_ui, weak=False)
        self.event_bus.subscribe(Events.GET_GUI_WINDOW_ID, self._on_get_gui_window_id, weak=False)

        self.event_bus.subscribe(Events.CHECK_TRITON_DEPENDENCIES, self._on_check_triton_dependencies, weak=False)
        self.event_bus.subscribe(Events.UPDATE_MODEL_LOADING_STATUS, self._on_update_model_loading_status, weak=False)
        self.event_bus.subscribe(Events.FINISH_MODEL_LOADING, self._on_finish_model_loading, weak=False)
        self.event_bus.subscribe(Events.SHOW_ERROR_MESSAGE, self._on_show_error_message, weak=False)
        self.event_bus.subscribe(Events.CANCEL_MODEL_LOADING, self._on_cancel_model_loading, weak=False)

        self.event_bus.subscribe(Events.PROMPT_FOR_TG_CODE, self._on_prompt_for_tg_code, weak=False)
        self.event_bus.subscribe(Events.PROMPT_FOR_TG_PASSWORD, self._on_prompt_for_tg_password, weak=False)
        
        self.event_bus.subscribe("history_loaded", self._on_history_loaded_event, weak=False)
        self.event_bus.subscribe("more_history_loaded", self._on_more_history_loaded_event, weak=False)
        self.event_bus.subscribe("model_initialized", self._on_model_initialized_event, weak=False)
        self.event_bus.subscribe("model_init_cancelled", self._on_model_init_cancelled_event, weak=False)
        self.event_bus.subscribe("model_init_failed", self._on_model_init_failed_event, weak=False)
        self.event_bus.subscribe("reload_prompts_success", self._on_reload_prompts_success_event, weak=False)
        self.event_bus.subscribe("reload_prompts_failed", self._on_reload_prompts_failed_event, weak=False)
        self.event_bus.subscribe("display_loading_popup", self._on_display_loading_popup_event, weak=False)
        self.event_bus.subscribe("hide_loading_popup", self._on_hide_loading_popup_event, weak=False)
        self.event_bus.subscribe("setting_changed", self._on_setting_changed, weak=False)
                
    def _connect_view_signals(self):
        if self.view:
            self.view.clear_user_input_signal = getattr(self.view, 'clear_user_input_signal', None)
            self.view.update_chat_font_size_signal = getattr(self.view, 'update_chat_font_size_signal', None)
            self.view.switch_voiceover_settings_signal = getattr(self.view, 'switch_voiceover_settings_signal', None)
            self.view.load_chat_history_signal = getattr(self.view, 'load_chat_history_signal', None)
            self.view.check_triton_dependencies_signal = getattr(self.view, 'check_triton_dependencies_signal', None)
            self.view.show_info_message_signal = getattr(self.view, 'show_info_message_signal', None)
            self.view.show_error_message_signal = getattr(self.view, 'show_error_message_signal', None)
            self.view.update_model_loading_status_signal = getattr(self.view, 'update_model_loading_status_signal', None)
            self.view.finish_model_loading_signal = getattr(self.view, 'finish_model_loading_signal', None)
            self.view.cancel_model_loading_signal = getattr(self.view, 'cancel_model_loading_signal', None)
        
    def connect_view_signals(self):
        self.main_controller.telegram_controller.connect_view_signals()
        
    def update_status_colors(self):
        logger.debug("GuiController: update_status_colors")
        if self.view:
            self.view.update_status_signal.emit()
        else:
            logger.error("GuiController: view не найден!")
            
    def clear_user_input(self):
        logger.debug("GuiController: clear_user_input")
        self.event_bus.emit(Events.CLEAR_USER_INPUT)
        if self.view and self.view.user_entry:
            self.view.user_entry.clear()
        else:
            logger.error("GuiController: view или user_entry не найден!")
            
    def show_mita_thinking(self, character_name):
        print(f"[DEBUG] GuiController: показ статуса 'думает' для {character_name}")
        logger.info(f"GuiController: show_mita_thinking для {character_name}")
        if self.view:
            print(f"[DEBUG] Эмитим show_thinking_signal с {character_name}")
            self.view.show_thinking_signal.emit(character_name)
        else:
            print("[DEBUG] view не найден!")
            logger.error("GuiController: view не найден!")
            
    def show_mita_error(self, error_message):
        print(f"[DEBUG] GuiController: показ ошибки: {error_message}")
        logger.info(f"GuiController: show_mita_error: {error_message}")
        if self.view:
            self.view.show_error_signal.emit(error_message)
        else:
            logger.error("GuiController: view не найден!")
            
    def hide_mita_status(self):
        print("[DEBUG] GuiController: скрытие статуса")
        logger.info("GuiController: hide_mita_status")
        if self.view:
            print("[DEBUG] Эмитим hide_status_signal")
            self.view.hide_status_signal.emit()
        else:
            print("[DEBUG] view не найден при попытке скрыть!")
            logger.error("GuiController: view не найден при попытке скрыть!")
            
    def show_mita_error_pulse(self):
        logger.info("GuiController: show_mita_error_pulse")
        if self.view:
            self.view.pulse_error_signal.emit()
        else:
            logger.error("GuiController: view не найден!")
            
    def get_user_input(self):
        if self.view and self.view.user_entry:
            result = self.view.user_entry.toPlainText().strip()
            logger.debug(f"GuiController: get_user_input возвращает: '{result}'")
            return result
        logger.warning("GuiController: view или user_entry не найден!")
        return ""
        
    def check_and_install_ffmpeg(self):
        logger.info("GuiController: check_and_install_ffmpeg")
        QTimer.singleShot(100, self._check_and_install_ffmpeg_impl)
        
    def _check_and_install_ffmpeg_impl(self):
        ffmpeg_path = Path(".") / "ffmpeg.exe"
        logger.info(f"Checking for FFmpeg at: {ffmpeg_path}")

        if not ffmpeg_path.exists():
            logger.info("FFmpeg not found. Starting installation process in a separate thread.")
            import threading
            install_thread = threading.Thread(target=self._ffmpeg_install_thread_target, daemon=True)
            install_thread.start()
        else:
            logger.info("FFmpeg found. No installation needed.")
            
    def _ffmpeg_install_thread_target(self):
        if self.view:
            QTimer.singleShot(0, self.view._show_ffmpeg_installing_popup)

        logger.info("Starting FFmpeg installation attempt...")
        success = install_ffmpeg()
        logger.info(f"FFmpeg installation attempt finished. Success: {success}")

        if self.view:
            QTimer.singleShot(0, self.view._close_ffmpeg_installing_popup)

        if not success and self.view:
            QTimer.singleShot(0, self.view._show_ffmpeg_error_popup)
            
    def stream_callback_handler(self, chunk: str):
        logger.debug(f"GuiController: stream_callback_handler: {chunk[:50]}...")
        if self.view:
            self.view.append_stream_chunk_signal.emit(chunk)
        else:
            logger.error("GuiController: view не найден!")
            
    def prepare_stream(self):
        logger.info("GuiController: prepare_stream")
        if self.view:
            self.view.prepare_stream_signal.emit()
        else:
            logger.error("GuiController: view не найден!")
            
    def finish_stream(self):
        logger.info("GuiController: finish_stream")
        if self.view:
            self.view.finish_stream_signal.emit()
        else:
            logger.error("GuiController: view не найден!")
            
    def update_chat(self, role, response, is_initial, emotion):
        logger.info(f"GuiController: update_chat - role: {role}, response: {response[:50]}..., is_initial: {is_initial}, emotion: {emotion}")
        if self.view:
            print(f"[DEBUG] GuiController: эмитим update_chat_signal с данными role={role}, response={response[:50]}...")
            self.view.update_chat_signal.emit(role, response, is_initial, emotion)
        else:
            print("[DEBUG] GuiController: view не найден!")
            logger.error("GuiController: view не найден!")
            
    def update_status(self):
        logger.debug("GuiController: update_status")
        if self.view:
            self.view.update_status_signal.emit()
        else:
            logger.error("GuiController: view не найден!")
            
    def update_debug(self):
        logger.debug("GuiController: update_debug")
        if self.view:
            self.view.update_debug_signal.emit()
        else:
            logger.error("GuiController: view не найден!")
            
    def update_token_count(self):
        logger.debug("GuiController: update_token_count")
        if self.view:
            QTimer.singleShot(0, self.view.update_token_count)
        else:
            logger.error("GuiController: view не найден!")
        
    def _on_update_status_colors(self, event: Event):
        logger.debug("GuiController: получено событие UPDATE_STATUS_COLORS")
        self.update_status_colors()
        
    def _on_clear_user_input_ui(self, event: Event):
        logger.debug("GuiController: получено событие CLEAR_USER_INPUT_UI")
        self.clear_user_input()

    # ДУБЛИКАТ НАВЕРНОЕ    
    def _on_update_chat(self, event: Event):
        logger.info(f"GuiController: получено событие UPDATE_CHAT с данными: {event.data}")
        role = event.data.get('role', '')
        content = event.data.get('content', '')
        is_initial = event.data.get('is_initial', False)
        emotion = event.data.get('emotion', '')
        self.update_chat(role, content, is_initial, emotion)
    

    def _on_update_chat_ui(self, event: Event):
        logger.info(f"GuiController: получено событие UPDATE_CHAT_UI с данными: {event.data}")
        role = event.data.get('role', '')
        response = event.data.get('response', '')
        is_initial = event.data.get('is_initial', False)
        emotion = event.data.get('emotion', '')
        self.update_chat(role, response, is_initial, emotion)
        
    def _on_prepare_stream_ui(self, event: Event):
        logger.debug("GuiController: получено событие PREPARE_STREAM_UI")
        self.prepare_stream()
        
    def _on_append_stream_chunk_ui(self, event: Event):
        chunk = event.data.get('chunk', '')
        logger.debug(f"GuiController: получено событие APPEND_STREAM_CHUNK_UI с chunk: {chunk[:30]}...")
        self.stream_callback_handler(chunk)
        
    def _on_finish_stream_ui(self, event: Event):
        logger.debug("GuiController: получено событие FINISH_STREAM_UI")
        self.finish_stream()
        
    def _on_update_status(self, event: Event):
        logger.debug("GuiController: получено событие UPDATE_STATUS")
        self.update_status()
        
    def _on_update_debug_info(self, event: Event):
        logger.debug("GuiController: получено событие UPDATE_DEBUG_INFO")
        self.update_debug()
        
    def _on_update_token_count(self, event: Event):
        logger.debug("GuiController: получено событие UPDATE_TOKEN_COUNT")
        self.update_token_count()
        
    def _on_check_and_install_ffmpeg(self, event: Event):
        logger.debug("GuiController: получено событие CHECK_AND_INSTALL_FFMPEG")
        self.check_and_install_ffmpeg()
        
        
    def _on_started_response(self, event: Event):
        logger.info("GuiController: получено событие ON_STARTED_RESPONSE_GENERATION")
        character_name = "Мита"
        
        results = self.event_bus.emit_and_wait(Events.GET_CURRENT_CHARACTER, timeout=1.0)
        if results and results[0]:
            character_data = results[0]
            character_name = character_data.get('name', 'Мита')
        
        print(f"[DEBUG] GuiController: вызываем show_mita_thinking с {character_name}")
        self.show_mita_thinking(character_name)
        
    def _on_successful_response(self, event: Event):
        logger.info("GuiController: получено событие ON_SUCCESSFUL_RESPONSE")
        print("[DEBUG] GuiController: вызываем hide_mita_status")
        self.hide_mita_status()
        
    def _on_failed_response_attempt(self, event: Event):
        logger.info("GuiController: получено событие ON_FAILED_RESPONSE_ATTEMPT")
        print("[DEBUG] GuiController: вызываем show_mita_error_pulse")
        self.show_mita_error_pulse()
        
    def _on_failed_response(self, event: Event):
        logger.warning(f"GuiController: получено событие ON_FAILED_RESPONSE с данными: {event.data}")
        error_message = event.data.get('error', 'Неизвестная ошибка') if event.data else 'Неизвестная ошибка'
        print(f"[DEBUG] GuiController: вызываем show_mita_error с {error_message}")
        self.show_mita_error(error_message)
        
    def _on_insert_text_to_input(self, event: Event):
        text = event.data.get('text', '')
        if self.view and self.view.user_entry:
            self.view.user_entry.insertPlainText(text)

    def _on_check_user_entry_exists(self, event: Event):
        return bool(self.view and self.view.user_entry)
    
    def _on_switch_voiceover_settings(self, event: Event):
        if self.view and hasattr(self.view, 'switch_voiceover_settings_signal') and self.view.switch_voiceover_settings_signal:
            self.view.switch_voiceover_settings_signal.emit()
        elif self.view and hasattr(self.view, 'switch_voiceover_settings'):
            self.view.switch_voiceover_settings()

    def _on_show_info_message(self, event: Event):
        title = event.data.get('title', 'Информация')
        message = event.data.get('message', '')
        if self.view and hasattr(self.view, 'show_info_message_signal') and self.view.show_info_message_signal:
            self.view.show_info_message_signal.emit({'title': title, 'message': message})
        elif self.view:
            QTimer.singleShot(0, lambda: QMessageBox.information(self.view, title, message))

    def _on_update_chat_font_size(self, event: Event):
        font_size = event.data.get('font_size', 12)
        if self.view and hasattr(self.view, 'update_chat_font_size_signal') and self.view.update_chat_font_size_signal:
            self.view.update_chat_font_size_signal.emit(font_size)
        elif self.view and hasattr(self.view, 'update_chat_font_size'):
            self.view.update_chat_font_size(font_size)

    def _on_reload_chat_history(self, event: Event):
        if self.view and hasattr(self.view, 'load_chat_history_signal') and self.view.load_chat_history_signal:
            self.view.load_chat_history_signal.emit()
        elif self.view and hasattr(self.view, 'load_chat_history'):
            self.view.load_chat_history()

    def _on_update_token_count_ui(self, event: Event):
        self.update_token_count()

    def _on_get_gui_window_id(self, event: Event):
        if self.view and hasattr(self.view, 'winId'):
            return int(self.view.winId())
        return None
    
    def _on_check_triton_dependencies(self, event: Event):
        if self.view and hasattr(self.view, 'check_triton_dependencies_signal') and self.view.check_triton_dependencies_signal:
            self.view.check_triton_dependencies_signal.emit()
        elif self.view and hasattr(self.view, 'check_triton_dependencies'):
            self.view.check_triton_dependencies()

    def _on_update_model_loading_status(self, event: Event):
        status = event.data.get('status', '')
        if self.view and hasattr(self.view, 'update_model_loading_status_signal') and self.view.update_model_loading_status_signal:
            self.view.update_model_loading_status_signal.emit(status)
        elif self.view and hasattr(self.view, 'loading_status_label'):
            QTimer.singleShot(0, lambda: self.view.loading_status_label.setText(status))

    def _on_finish_model_loading(self, event: Event):
        model_id = event.data.get('model_id')
        if self.view and hasattr(self.view, 'finish_model_loading_signal') and self.view.finish_model_loading_signal:
            self.view.finish_model_loading_signal.emit({'model_id': model_id})
        elif self.view and hasattr(self.view, 'finish_model_loading') and hasattr(self.view, 'loading_dialog'):
            QTimer.singleShot(0, lambda: self.view.finish_model_loading(model_id, self.view.loading_dialog))

    def _on_show_error_message(self, event: Event):
        title = event.data.get('title', 'Ошибка')
        message = event.data.get('message', '')
        if self.view and hasattr(self.view, 'show_error_message_signal') and self.view.show_error_message_signal:
            self.view.show_error_message_signal.emit({'title': title, 'message': message})
        elif self.view:
            QTimer.singleShot(0, lambda: QMessageBox.critical(self.view, title, message))

    def _on_cancel_model_loading(self, event: Event):
        if self.view and hasattr(self.view, 'cancel_model_loading_signal') and self.view.cancel_model_loading_signal:
            self.view.cancel_model_loading_signal.emit()
        elif self.view and hasattr(self.view, 'cancel_model_loading') and hasattr(self.view, 'loading_dialog'):
            QTimer.singleShot(0, lambda: self.view.cancel_model_loading(self.view.loading_dialog))
    
    def _on_prompt_for_tg_code(self, event: Event):
        code_future = event.data.get('future')    
        self.view.show_tg_code_dialog_signal.emit({'future': code_future})

    def _on_prompt_for_tg_password(self, event: Event):
        password_future = event.data.get('future')
        self.view.show_tg_password_dialog_signal.emit({'future': password_future})
    def _on_history_loaded_event(self, event: Event):
        logger.debug("GuiController: получено ghost событие history_loaded, транслируем в view")
        if self.view:
            self.view.history_loaded_signal.emit(event.data)
    
    def _on_more_history_loaded_event(self, event: Event):
        logger.debug("GuiController: получено ghost событие more_history_loaded, транслируем в view")
        if self.view:
            self.view.more_history_loaded_signal.emit(event.data)
    
    def _on_model_initialized_event(self, event: Event):
        logger.debug("GuiController: получено событие model_initialized, транслируем в view")
        if self.view:
            self.view.model_initialized_signal.emit(event.data)
    
    def _on_model_init_cancelled_event(self, event: Event):
        logger.debug("GuiController: получено событие model_init_cancelled, транслируем в view")
        if self.view:
            self.view.model_init_cancelled_signal.emit(event.data)
    
    def _on_model_init_failed_event(self, event: Event):
        logger.debug("GuiController: получено событие model_init_failed, транслируем в view")
        if self.view:
            self.view.model_init_failed_signal.emit(event.data)
    
    def _on_reload_prompts_success_event(self, event: Event):
        logger.debug("GuiController: получено событие reload_prompts_success, транслируем в view")
        if self.view:
            self.view.reload_prompts_success_signal.emit()
    
    def _on_reload_prompts_failed_event(self, event: Event):
        logger.debug("GuiController: получено событие reload_prompts_failed, транслируем в view")
        if self.view:
            self.view.reload_prompts_failed_signal.emit(event.data)
    
    def _on_display_loading_popup_event(self, event: Event):
        logger.debug("GuiController: получено событие display_loading_popup, транслируем в view")
        if self.view:
            self.view.display_loading_popup_signal.emit(event.data)
    
    def _on_hide_loading_popup_event(self, event: Event):
        logger.debug("GuiController: получено событие hide_loading_popup, транслируем в view")
        if self.view:
            self.view.hide_loading_popup_signal.emit()

    def _on_setting_changed(self, event: Event):
        key = event.data.get('key')
        value = event.data.get('value')
        
        if key in ["USE_VOICEOVER", "VOICEOVER_METHOD", "AUDIO_BOT"]:
            self.event_bus.emit(Events.SWITCH_VOICEOVER_SETTINGS)
            
        if key == "AUDIO_BOT":
            if value.startswith("@CrazyMitaAIbot"):
                self.event_bus.emit(Events.SHOW_INFO_MESSAGE, {
                    "title": "Информация",
                    "message": "VinerX: наши товарищи из CrazyMitaAIbot предоставляет озвучку бесплатно буквально со своих пк, будет время - загляните к ним в тг, скажите спасибо)"
                })
                
        elif key == "CHAT_FONT_SIZE":
            try:
                font_size = int(value)
                self.event_bus.emit(Events.UPDATE_CHAT_FONT_SIZE, {"font_size": font_size})
                self.event_bus.emit(Events.RELOAD_CHAT_HISTORY)
                logger.info(f"Размер шрифта чата изменен на: {font_size}")
            except ValueError:
                logger.warning(f"Неверное значение для размера шрифта: {value}")
            except Exception as e:
                logger.error(f"Ошибка при изменении размера шрифта: {e}")
                
        elif key in ["SHOW_CHAT_TIMESTAMPS", "MAX_CHAT_HISTORY_DISPLAY", "HIDE_CHAT_TAGS"]:
            self.event_bus.emit(Events.RELOAD_CHAT_HISTORY)
            logger.info(f"Настройка '{key}' изменена на: {value}. История чата перезагружена.")
            
        elif key == "SHOW_TOKEN_INFO":
            self.event_bus.emit(Events.UPDATE_TOKEN_COUNT)
            
        if key in ["MIC_ACTIVE", "ENABLE_SCREEN_ANALYSIS", "ENABLE_CAMERA_CAPTURE"]:
            self.event_bus.emit(Events.UPDATE_STATUS_COLORS)