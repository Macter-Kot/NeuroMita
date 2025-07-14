import asyncio
import threading
from PyQt6.QtCore import QObject, pyqtSignal
from handlers.telegram_handler import TelegramBotHandler
from main_logger import logger
from utils import SH
from core.events import get_event_bus, Events, Event

class TelegramAuthSignals(QObject):
    code_required = pyqtSignal(object)
    password_required = pyqtSignal(object)

class TelegramController:
    def __init__(self, main_controller):
        self.main = main_controller
        self.settings = None
        self.event_bus = get_event_bus()
        self.bot_handler = None
        self.bot_handler_ready = False
        self.silero_connected = False
        
        self.api_hash = ""
        self.api_id = ""
        self.phone = ""
        
        self.auth_signals = TelegramAuthSignals()
        self._subscribe_to_events()
        
    def _subscribe_to_events(self):
        self.event_bus.subscribe("telegram_settings_loaded", self._on_telegram_settings_loaded, weak=False)
        self.event_bus.subscribe("telegram_settings_changed", self._on_telegram_settings_changed, weak=False)
        self.event_bus.subscribe("telegram_send_voice_request", self._on_send_voice_request, weak=False)
    
    def _on_telegram_settings_loaded(self, event: Event):
        data = event.data
        self.api_id = data.get("api_id", "")
        self.api_hash = data.get("api_hash", "")
        self.phone = data.get("phone", "")
        self.settings = data.get("settings")
        logger.info(f"Telegram настройки загружены: api_id={SH(self.api_id)}, api_hash={SH(self.api_hash)}, phone={SH(self.phone)}")
    
    def _on_telegram_settings_changed(self, event: Event):
        key = event.data.get('key')
        value = event.data.get('value')
        
        if key == "SILERO_TIME" and self.bot_handler:
            self.bot_handler.silero_time_limit = int(value)
        elif key == "AUDIO_BOT" and self.bot_handler:
            self.bot_handler.tg_bot = value
        
    def connect_view_signals(self):
        self.auth_signals.code_required.connect(self._on_code_required)
        self.auth_signals.password_required.connect(self._on_password_required)
        
    def _on_code_required(self, code_future):
        self.event_bus.emit(Events.PROMPT_FOR_TG_CODE, {'future': code_future})
        
    def _on_password_required(self, password_future):
        self.event_bus.emit(Events.PROMPT_FOR_TG_PASSWORD, {'future': password_future})
        
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

            audio_bot = "@silero_voice_bot"
            if self.settings:
                audio_bot = self.settings.get("AUDIO_BOT", "@silero_voice_bot")

            self.bot_handler = TelegramBotHandler(self.api_id, self.api_hash, self.phone, audio_bot)

            try:
                await self.bot_handler.start()
                self.bot_handler_ready = True
                if hasattr(self, 'silero_connected') and self.silero_connected:
                    logger.info("ТГ успешно подключен")
                    self.event_bus.emit(Events.UPDATE_STATUS_COLORS)
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

    def _on_send_voice_request(self, event: Event):
        data = event.data
        text = data.get('text', '')
        speaker_command = data.get('speaker_command', '')
        id = data.get('id', 0)
        future = data.get('future')
        
        if self.bot_handler and self.bot_handler_ready:
            asyncio.run_coroutine_threadsafe(
                self._async_send_and_receive(text, speaker_command, id, future),
                self.main.loop
            )
        else:
            logger.error("Bot handler не готов для отправки голосового запроса")
            if future:
                future.set_exception(Exception("Bot handler not ready"))

    async def _async_send_and_receive(self, text, speaker_command, id, future):
        try:
            await self.bot_handler.send_and_receive(text, speaker_command, id)
            if future:
                future.set_result(True)
        except Exception as e:
            logger.error(f"Ошибка при отправке голосового запроса: {e}")
            if future:
                future.set_exception(e)