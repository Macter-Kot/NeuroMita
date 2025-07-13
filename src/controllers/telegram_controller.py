import asyncio
import threading
from PyQt6.QtCore import QObject, pyqtSignal
from handlers.telegram_handler import TelegramBotHandler
from main_logger import logger
from utils import SH

class TelegramAuthSignals(QObject):
    code_required = pyqtSignal(object)
    password_required = pyqtSignal(object)

class TelegramController:
    def __init__(self, main_controller):
        self.main = main_controller
        self.bot_handler = None
        self.bot_handler_ready = False
        self.silero_connected = False
        
        self.api_hash = ""
        self.api_id = ""
        self.phone = ""
        
        self.auth_signals = TelegramAuthSignals()
        
    def connect_view_signals(self):
        self.auth_signals.code_required.connect(self.main.view.prompt_for_code)
        self.auth_signals.password_required.connect(self.main.view.prompt_for_password)
        
    def start_silero_async(self):
        logger.info("Ожидание готовности цикла событий...")
        self.main.loop_ready_event.wait()
        if self.main.loop and self.main.loop.is_running():
            logger.info("Запускаем Silero через цикл событий.")
            asyncio.run_coroutine_threadsafe(self.start_silero(), self.main.loop)
        else:
            logger.info("Ошибка: Цикл событий asyncio не запущен.")
            
    async def start_silero(self):
        logger.info("Telegram Bot запускается!")
        try:
            if not self.api_id or not self.api_hash or not self.phone:
                logger.info("Ошибка: отсутствуют необходимые данные для Telegram бота")
                self.silero_connected = False
                return

            logger.info(f"Передаю в тг {SH(self.api_id)},{SH(self.api_hash)},{SH(self.phone)} (Должно быть не пусто)")

            self.bot_handler = TelegramBotHandler(self.api_id, self.api_hash, self.phone,
                                                  self.main.settings.get("AUDIO_BOT", "@silero_voice_bot"))

            try:
                await self.bot_handler.start()
                self.bot_handler_ready = True
                if hasattr(self, 'silero_connected') and self.silero_connected:
                    logger.info("ТГ успешно подключен")
                    self.main.update_status_colors()
                else:
                    logger.info("ТГ не подключен")
            except Exception as e:
                logger.info(f"Ошибка при запуске Telegram бота: {e}")
                self.bot_handler_ready = False
                self.silero_connected = False

        except Exception as e:
            logger.info(f"Критическая ошибка при инициализации Telegram Bot: {e}")
            self.silero_connected = False
            self.bot_handler_ready = False