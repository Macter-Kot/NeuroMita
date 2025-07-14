import time
import threading
from win32 import win32gui
from handlers.screen_handler import ScreenCapture
from main_logger import logger
from core.events import get_event_bus, Events
from PyQt6.QtCore import QTimer

class CaptureController:
    def __init__(self, main_controller):

        self.settings = main_controller.settings
        self.event_bus = get_event_bus()
        self.screen_capture_instance = ScreenCapture()
        self.screen_capture_thread = None
        self.screen_capture_running = False
        self.screen_capture_active = False
        self.camera_capture_active = False
        self.last_captured_frame = None
        self.camera_capture = None
        
        self.image_request_thread = None
        self.image_request_running = False
        self.last_image_request_time = time.time()
        self.image_request_timer_running = False
        
        if self.settings.get("ENABLE_SCREEN_ANALYSIS", False):
            logger.info("Настройка 'ENABLE_SCREEN_ANALYSIS' включена. Автоматический запуск захвата экрана.")
            self.start_screen_capture_thread()

        if self.settings.get("ENABLE_CAMERA_CAPTURE", False):
            logger.info("Настройка 'ENABLE_CAMERA_CAPTURE' включена. Автоматический запуск захвата с камеры.")
            self.start_camera_capture_thread()
            
    def start_screen_capture_thread(self):
        if not self.screen_capture_running:
            interval = float(self.settings.get("SCREEN_CAPTURE_INTERVAL", 5.0))
            quality = int(self.settings.get("SCREEN_CAPTURE_QUALITY", 25))
            fps = int(self.settings.get("SCREEN_CAPTURE_FPS", 1))
            max_history_frames = int(self.settings.get("SCREEN_CAPTURE_HISTORY_LIMIT", 3))
            max_frames_per_request = int(self.settings.get("SCREEN_CAPTURE_TRANSFER_LIMIT", 1))
            capture_width = int(self.settings.get("SCREEN_CAPTURE_WIDTH", 1024))
            capture_height = int(self.settings.get("SCREEN_CAPTURE_HEIGHT", 768))
            self.screen_capture_instance.start_capture(interval, quality, fps, max_history_frames,
                                                       max_frames_per_request, capture_width,
                                                       capture_height)
            self.screen_capture_running = True
            logger.info(f"Поток захвата экрана запущен")
            
            self.screen_capture_active = True
            if self.settings.get("SEND_IMAGE_REQUESTS", 1):
                self.start_image_request_timer()
            self.event_bus.emit(Events.UPDATE_STATUS_COLORS)
            
    def stop_screen_capture_thread(self):
        if self.screen_capture_running:
            self.screen_capture_instance.stop_capture()
            self.screen_capture_running = False
            logger.info("Поток захвата экрана остановлен.")
        self.screen_capture_active = False
        self.event_bus.emit(Events.UPDATE_STATUS_COLORS)
        
    def start_camera_capture_thread(self):
        if not hasattr(self, 'camera_capture') or self.camera_capture is None:
            from handlers.camera_handler import CameraCapture
            self.camera_capture = CameraCapture()

        if not self.camera_capture.is_running():
            camera_index = int(self.settings.get("CAMERA_INDEX", 0))
            interval = float(self.settings.get("CAMERA_CAPTURE_INTERVAL", 5.0))
            quality = int(self.settings.get("CAMERA_CAPTURE_QUALITY", 25))
            fps = int(self.settings.get("CAMERA_CAPTURE_FPS", 1))
            max_history_frames = int(self.settings.get("CAMERA_CAPTURE_HISTORY_LIMIT", 3))
            max_frames_per_request = int(self.settings.get("CAMERA_CAPTURE_TRANSFER_LIMIT", 1))
            capture_width = int(self.settings.get("CAMERA_CAPTURE_WIDTH", 640))
            capture_height = int(self.settings.get("CAMERA_CAPTURE_HEIGHT", 480))
            self.camera_capture.start_capture(camera_index, quality, fps, max_history_frames,
                                              max_frames_per_request, capture_width,
                                              capture_height)
            logger.info(f"Поток захвата с камеры запущен с индексом {camera_index}")
            self.camera_capture_active = True
            self.event_bus.emit(Events.UPDATE_STATUS_COLORS)
            
    def stop_camera_capture_thread(self):
        if hasattr(self, 'camera_capture') and self.camera_capture is not None and self.camera_capture.is_running():
            self.camera_capture.stop_capture()
            logger.info("Поток захвата с камеры остановлен.")
        self.camera_capture_active = False
        self.event_bus.emit(Events.UPDATE_STATUS_COLORS)
        
    def start_image_request_timer(self):
        if not self.image_request_timer_running:
            self.image_request_timer_running = True
            self.last_image_request_time = time.time()
            logger.info("Таймер периодической отправки изображений запущен.")

    def stop_image_request_timer(self):
        if self.image_request_timer_running:
            self.image_request_timer_running = False
            logger.info("Таймер периодической отправки изображений остановлен.")
            
    def send_interval_image(self):
        current_time = time.time()
        interval = float(self.settings.get("IMAGE_REQUEST_INTERVAL", 20.0))
        delta = current_time - self.last_image_request_time
        
        if delta >= interval:
            image_data = []
            if self.settings.get("ENABLE_SCREEN_ANALYSIS", False):
                logger.info(f"Отправка периодического запроса с изображением ({current_time - self.last_image_request_time:.2f}/{interval:.2f} сек).")
                history_limit = int(self.settings.get("SCREEN_CAPTURE_HISTORY_LIMIT", 1))
                frames = self.screen_capture_instance.get_recent_frames(history_limit)
                if frames:
                    image_data.extend(frames)
                    logger.info(f"Захвачено {len(frames)} кадров для периодической отправки.")
                else:
                    logger.info("Анализ экрана включен, но кадры не готовы или история пуста для периодической отправки.")

                if image_data:
                    if self.main.loop and self.main.loop.is_running():
                        import asyncio
                        asyncio.run_coroutine_threadsafe(
                            self.main.async_send_message(user_input="", system_input="", image_data=image_data),
                            self.main.loop)
                        self.last_image_request_time = current_time
                    else:
                        logger.error("Ошибка: Цикл событий не готов для периодической отправки изображений.")
                else:
                    logger.warning("Нет изображений для периодической отправки.")