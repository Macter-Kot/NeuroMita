import threading
import time
from game_connections.server_old import ChatServer
from main_logger import logger
from core.events import get_event_bus, Events, Event


class ServerControllerOld:
    def __init__(self):
        self.event_bus = get_event_bus()
        self.server = ChatServer()
        self.server_thread = None
        self.running = False
        self.ConnectedToGame = False
        self.patch_to_sound_file = ""
        self.id_sound = None
        self._destroyed = False

        self._subscribe_to_events()
        self.start_server()
        
    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.Server.GET_SERVER_DATA, self._on_get_server_data, weak=False)
        self.event_bus.subscribe(Events.Server.RESET_SERVER_DATA, self._on_reset_server_data, weak=False)
        self.event_bus.subscribe(Events.Server.STOP_SERVER, self._on_stop_server, weak=False)
        self.event_bus.subscribe(Events.Server.GET_CHAT_SERVER, self._on_get_chat_server, weak=False)
        self.event_bus.subscribe(Events.Server.SET_PATCH_TO_SOUND_FILE, self._on_set_patch_to_sound_file, weak=False)
        self.event_bus.subscribe(Events.Server.SET_ID_SOUND, self._on_set_id_sound, weak=False)
        self.event_bus.subscribe(Events.Server.SET_GAME_CONNECTION, self._on_update_game_connection, weak=False)
        self.event_bus.subscribe(Events.Server.GET_GAME_CONNECTION, self._on_get_connection_status, weak=False)
        
    def _unsubscribe_from_events(self):
        """Отписываемся от всех событий перед уничтожением"""
        if self.event_bus and not self._destroyed:
            self.event_bus.unsubscribe(Events.Server.GET_SERVER_DATA, self._on_get_server_data)
            self.event_bus.unsubscribe(Events.Server.RESET_SERVER_DATA, self._on_reset_server_data)
            self.event_bus.unsubscribe(Events.Server.STOP_SERVER, self._on_stop_server)
            self.event_bus.unsubscribe(Events.Server.GET_CHAT_SERVER, self._on_get_chat_server)
            self.event_bus.unsubscribe(Events.Server.SET_PATCH_TO_SOUND_FILE, self._on_set_patch_to_sound_file)
            self.event_bus.unsubscribe(Events.Server.SET_ID_SOUND, self._on_set_id_sound)
            self.event_bus.unsubscribe(Events.Server.SET_GAME_CONNECTION, self._on_update_game_connection)
            self.event_bus.unsubscribe(Events.Server.GET_GAME_CONNECTION, self._on_get_connection_status)
        
    def start_server(self):
        if not self.running:
            self.running = True
            self.server.start()
            self.server_thread = threading.Thread(target=self.run_server_loop, daemon=True)
            self.server_thread.start()
            logger.info("Сервер запущен")
            
    def stop_server(self):
        if not self.running:
            logger.debug("Сервер уже остановлен")
            return

        logger.info("Начинаем остановку сервера...")
        self.running = False

        try:
            self.server.stop()
        except OSError as e:
            if hasattr(e, 'winerror') and e.winerror == 10038:
                logger.debug("Сокет уже закрыт, игнорируем ошибку 10038")
            else:
                logger.error(f"Ошибка при остановке сервера: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Неожиданная ошибка при остановке сервера: {e}", exc_info=True)

        if self.server_thread and self.server_thread.is_alive():
            logger.info("Ожидание завершения серверного потока...")
            self.server_thread.join(timeout=5)
            if self.server_thread.is_alive():
                logger.warning("Серверный поток не завершился вовремя (таймаут 5 сек)")

        self.server_thread = None
        logger.info("Сервер остановлен")
            
    def run_server_loop(self):
        while self.running:
            try:
                if self.server and self.server.server_socket:
                    self.server.handle_connection()
                else:
                    break
            except Exception as e:
                if self.running and not self._destroyed:
                    logger.error(f"Ошибка в server loop: {e}")
                    time.sleep(0.1)
    
    def destroy(self):
        """Полная очистка контроллера при переключении API"""
        if self._destroyed:
            return
            
        logger.info("Уничтожение ServerController (старый API)...")
        self._destroyed = True
        
        # Сначала отписываемся от событий
        self._unsubscribe_from_events()
        
        # Затем останавливаем сервер
        self.stop_server()
        
        # Очищаем ссылки
        self.server = None
        self.event_bus = None
    
    def _on_get_server_data(self, event: Event):
        if self._destroyed:
            return None
            
        silero_connected_result = self.event_bus.emit_and_wait(Events.Telegram.GET_SILERO_STATUS)
        silero_connected = silero_connected_result[0] if silero_connected_result else False
        instand_send_result = self.event_bus.emit_and_wait(Events.Speech.GET_INSTANT_SEND_STATUS)
        instand_send = instand_send_result[0] if instand_send_result else False

        return {
            'patch_to_sound_file': self.patch_to_sound_file,
            'id_sound': self.id_sound,
            'instant_send': instand_send,
            'silero_connected': silero_connected
        }
    
    def _on_set_id_sound(self, event: Event):
        if self._destroyed:
            return False
        try:
            logger.info(f"Установлен ID звука: {event.data.get('id')}")
            self.id_sound = event.data.get("id")
            return True
        except Exception as ex:
            logger.error("При установке id_sound произошла ошибка: " + str(ex))
            return False
    
    def _on_reset_server_data(self, event: Event):
        if self._destroyed:
            return
        logger.info("Сброс данных сервера")
        self.patch_to_sound_file = ""
        self.id_sound = None
    
    def _on_stop_server(self, event: Event):
        if self._destroyed:
            return
        self.stop_server()
    
    def _on_get_chat_server(self, event: Event):
        if self._destroyed:
            return None
        return self.server
    
    def _on_set_patch_to_sound_file(self, event: Event):
        if self._destroyed:
            return
        self.patch_to_sound_file = event.data
        logger.info(f"Установлен путь к звуковому файлу: {self.patch_to_sound_file}")

    def update_game_connection(self, is_connected):
        if self._destroyed or not self.event_bus:
            return
        self.ConnectedToGame = is_connected
        self.event_bus.emit(Events.GUI.UPDATE_STATUS_COLORS)

    def _on_update_game_connection(self, event: Event):
        if self._destroyed:
            return
        is_connected = event.data.get('is_connected', False)
        self.update_game_connection(is_connected)

    def _on_get_connection_status(self, event: Event):
        if self._destroyed:
            return None
        return self.ConnectedToGame