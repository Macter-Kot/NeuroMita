import threading
import time  # Добавлено для time.strftime, хотя оно уже используется
from server import ChatServer
from main_logger import logger
from PyQt6.QtCore import QTimer

class ServerController:
    def __init__(self, main_controller):
        self.main = main_controller
        self.server = ChatServer(self.main, self.main.model_controller.model)
        self.server_thread = None
        self.running = False
        self.start_server()
        
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
        
        # Остановка внутреннего сервера с обработкой ошибок
        try:
            self.server.stop()
        except OSError as e:
            if e.winerror == 10038:  # Игнорируем WinError 10038 (сокет уже не является сокетом)
                logger.debug("Сокет уже закрыт, игнорируем ошибку 10038.")
            else:
                logger.error(f"Ошибка при остановке сервера: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Неожиданная ошибка при остановке сервера: {e}", exc_info=True)
        
        # Ожидание завершения потока
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