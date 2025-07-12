import threading
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
        if self.running:
            self.running = False
            self.server.stop()
            logger.info("Сервер остановлен.")
            
    def run_server_loop(self):
        while self.running:
            needUpdate = self.server.handle_connection()
            if needUpdate:
                logger.info(f"[{time.strftime('%H:%M:%S')}] run_server_loop: Обнаружено needUpdate, вызываю load_chat_history.")
                QTimer.singleShot(0, self.main.view.load_chat_history)