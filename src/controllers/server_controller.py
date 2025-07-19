import threading
import time
from server import ChatServer
from main_logger import logger
from PyQt6.QtCore import QTimer
from core.events import get_event_bus, Events, Event


# Контроллер для работы с сервером
class ServerController:
    def __init__(self, main_controller):
        self.main = main_controller
        self.event_bus = get_event_bus()
        self.server = ChatServer(self.main, self.main.model_controller.model)
        self.server_thread = None
        self.running = False
        
        self.patch_to_sound_file = ""
        
        self._subscribe_to_events()
        self.start_server()
        
    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.GET_SERVER_DATA, self._on_get_server_data, weak=False)
        self.event_bus.subscribe(Events.RESET_SERVER_DATA, self._on_reset_server_data, weak=False)
        self.event_bus.subscribe(Events.STOP_SERVER, self._on_stop_server, weak=False)
        self.event_bus.subscribe(Events.GET_CHAT_SERVER, self._on_get_chat_server, weak=False)
        self.event_bus.subscribe(Events.SET_PATCH_TO_SOUND_FILE, self._on_set_patch_to_sound_file, weak=False)
        self.event_bus.subscribe(Events.SET_ID_SOUND, self._on_set_id_sound, weak=False)
        
    def start_server(self):
        if not self.running:
            self.running = True
            self.server.start()
            self.server_thread = threading.Thread(target=self.run_server_loop, daemon=True)
            self.server_thread.start()
            logger.info("Сервер запущен.")
            
    def stop_server(self):
        if not self.running:
            logger.debug("Сервер уже остановлен.")
            return
            
        logger.info("Начинаем остановку сервера...")
        self.running = False
        
        try:
            self.server.stop()
        except OSError as e:
            if e.winerror == 10038:
                logger.debug("Сокет уже закрыт, игнорируем ошибку 10038.")
            else:
                logger.error(f"Ошибка при остановке сервера: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Неожиданная ошибка при остановке сервера: {e}", exc_info=True)
        
        if self.server_thread and self.server_thread.is_alive():
            logger.info("Ожидание завершения серверного потока...")
            self.server_thread.join(timeout=5)
            if self.server_thread.is_alive():
                logger.warning("Серверный поток не завершился вовремя (таймаут 5 сек).")
        
        self.server_thread = None
        logger.info("Сервер остановлен.")
            
    def run_server_loop(self):
        while self.running:
            needUpdate = self.server.handle_connection()
            if needUpdate:
                logger.info(f"[{time.strftime('%H:%M:%S')}] run_server_loop: Обнаружено needUpdate, вызываю load_chat_history.")
                QTimer.singleShot(0, self.main.view.load_chat_history)
    
    def _on_get_server_data(self, event: Event):
        return {
            'patch_to_sound_file': self.patch_to_sound_file,
            'id_sound': self.id_sound,
            'instant_send': self.event_bus.emit_and_wait(Events.GET_INSTANT_SEND_STATUS),
            'silero_connected': self.event_bus.emit_and_wait(Events.GET_SILERO_STATUS)
        }
    
    def _on_set_id_sound(self, event: Event):
        self.id_sound = event.data.get("id")
    
    def _on_reset_server_data(self, event: Event):
        self.main.instant_send = False
        self.patch_to_sound_file = ""
    
    def _on_stop_server(self, event: Event):
        self.stop_server()
    
    def _on_get_chat_server(self, event: Event):
        return self.server
    
    def _on_set_patch_to_sound_file(self, event: Event):
        self.patch_to_sound_file = event.data
        logger.info(f"Установлен путь к звуковому файлу: {self.patch_to_sound_file}")