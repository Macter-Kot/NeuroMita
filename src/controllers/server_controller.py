import threading
from typing import Optional
from main_logger import logger
from core.events import get_event_bus, Events, Event


class ServerController:
    def __init__(self):
        self.event_bus = get_event_bus()
        self.server = None
        self.running = False
        self.ConnectedToGame = False
        self._destroyed = False
        
        self._subscribe_to_events()
        self._init_server()
        
    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.Server.STOP_SERVER, self._on_stop_server, weak=False)
        self.event_bus.subscribe(Events.Server.GET_CHAT_SERVER, self._on_get_chat_server, weak=False)
        self.event_bus.subscribe(Events.Server.SET_GAME_CONNECTION, self._on_update_game_connection, weak=False)
        self.event_bus.subscribe(Events.Server.GET_GAME_CONNECTION, self._on_get_connection_status, weak=False)
        
    def _unsubscribe_from_events(self):
        """Отписываемся от всех событий перед уничтожением"""
        if self.event_bus and not self._destroyed:
            self.event_bus.unsubscribe(Events.Server.STOP_SERVER, self._on_stop_server)
            self.event_bus.unsubscribe(Events.Server.GET_CHAT_SERVER, self._on_get_chat_server)
            self.event_bus.unsubscribe(Events.Server.SET_GAME_CONNECTION, self._on_update_game_connection)
            self.event_bus.unsubscribe(Events.Server.GET_GAME_CONNECTION, self._on_get_connection_status)
        
    def _init_server(self):
        from game_connections.server import ChatServerNew
        self.server = ChatServerNew()
        logger.info("Используется новый API сервер")
        self.start_server()
        
    def start_server(self):
        if not self.running:
            self.running = True
            self.server.start()
            logger.info("Сервер запущен")
            
    def stop_server(self):
        if not self.running:
            logger.debug("Сервер уже остановлен")
            return
            
        logger.info("Начинаем остановку сервера...")
        self.running = False
        
        try:
            if self.server:
                self.server.stop()
        except Exception as e:
            logger.error(f"Ошибка при остановке сервера: {e}", exc_info=True)
        
        logger.info("Сервер остановлен")
        
    def destroy(self):
        """Полная очистка контроллера при переключении API"""
        if self._destroyed:
            return
            
        logger.info("Уничтожение ServerController...")
        self._destroyed = True
        
        # Сначала отписываемся от событий
        self._unsubscribe_from_events()
        
        # Затем останавливаем сервер
        self.stop_server()
        
        # Очищаем менеджер задач
        try:
            from managers.task_manager import get_task_manager
            task_manager = get_task_manager()
            task_manager.clear_all_tasks()
        except Exception as e:
            logger.error(f"Ошибка при очистке task manager: {e}")
        
        # Очищаем ссылки
        self.server = None
        self.event_bus = None
        
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
        
    def _on_stop_server(self, event: Event):
        if self._destroyed:
            return
        self.stop_server()
        
    def _on_get_chat_server(self, event: Event):
        if self._destroyed:
            return None
        return self.server