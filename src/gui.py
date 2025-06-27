
import io
import uuid
from win32 import  win32gui
import guiTemplates
from AudioHandler import AudioHandler
from Logger import logger
from SettingsManager import SettingsManager, CollapsibleSection
from chat_model import ChatModel
from server import ChatServer
# from Silero import TelegramBotHandler # ВРЕМЕННО УБРАЛ

from pyqt_styles.styles import get_stylesheet
import gettext
from pathlib import Path
import os
import base64
import json
import glob
import sounddevice as sd
from ui.settings.voiceover_settings import LOCAL_VOICE_MODELS
from utils.ffmpeg_installer import install_ffmpeg
# from utils.ModelsDownloader import ModelsDownloader # ВРЕМЕННО УБРАЛ

import asyncio
import threading
import binascii
import re
import subprocess
from utils import _
from utils import SH, process_text_to_voice
import sys

from ScreenCapture import ScreenCapture
import requests
import importlib
from LocalVoice import LocalVoice
import time
from SpeechRecognition import SpeechRecognition
from utils.PipInstaller import PipInstaller

# PyQt6 imports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTextEdit, QPushButton, QLabel, QScrollArea, QFrame,
                             QSplitter, QMessageBox, QComboBox, QCheckBox, QDialog,
                             QProgressBar, QTextBrowser, QVBoxLayout )
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont, QImage, QPixmap, QIcon

from ui import chat_area, status_indicators, debug_area, news_area
from ui.settings import (
    api_settings, character_settings, chat_settings, common_settings,
    g4f_settings, gamemaster_settings, general_model_settings,
    language_settings, microphone_settings, screen_analysis_settings,
    token_settings, voiceover_settings, command_replacer_settings, history_compressor,
    # prompt_catalogue_settings #  ВРЕМЕННО УБРАЛ
)


class AsyncWorker(QObject):
    """Worker для выполнения асинхронных задач"""
    finished = pyqtSignal()
    error = pyqtSignal(str)
    result = pyqtSignal(object)

    def __init__(self, coro):
        super().__init__()
        self.coro = coro

    async def run(self):
        try:
            result = await self.coro
            self.result.emit(result)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class ChatGUI(QMainWindow):
    # Сигналы для обновления UI из других потоков
    update_chat_signal = pyqtSignal(str, str, bool, str)  # role, content, insert_at_start, message_time
    update_status_signal = pyqtSignal()
    update_debug_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        
        self.voice_language_var = None
        self.local_voice_combobox = None
        self.debug_window = None
        self.mic_combobox = None

        self.ConnectedToGame = False
        self.chat_window = None
        self.token_count_label = None

        self.bot_handler = None
        self.bot_handler_ready = False

        self.selected_microphone = ""
        self.device_id = 0
        self.user_entry = None
        self.user_input = ""

        self.api_key = ""
        self.api_key_res = ""
        self.api_url = ""
        self.api_model = ""

        self.makeRequest = False
        self.api_hash = ""
        self.api_id = ""
        self.phone = ""

        try:
            target_folder = "Settings"
            os.makedirs(target_folder, exist_ok=True)
            self.config_path = os.path.join(target_folder, "settings.json")

            self.load_api_settings(False)
            self.settings = SettingsManager(self.config_path)
        except Exception as e:
            logger.info("Не удалось удачно получить из системных переменных все данные", e)
            self.settings = SettingsManager("Settings/settings.json")

        try:
            self.pip_installer = PipInstaller(
                script_path=r"libs\python\python.exe",
                libs_path="Lib",
                update_log=logger.info
            )
            logger.info("PipInstaller успешно инициализирован.")
        except Exception as e:
            logger.error(f"Не удалось инициализировать PipInstaller: {e}", exc_info=True)
            self.pip_installer = None

        self._check_and_perform_pending_update()

        self.local_voice = LocalVoice(self)
        self.voiceover_method = self.settings.get("VOICEOVER_METHOD", "TG")
        self.current_local_voice_id = self.settings.get("NM_CURRENT_VOICEOVER", None)
        self.last_voice_model_selected = None
        if self.current_local_voice_id:
            for model_info in LOCAL_VOICE_MODELS:
                if model_info["id"] == self.current_local_voice_id:
                    self.last_voice_model_selected = model_info
                    break
        self.model_loading_cancelled = False

        self.model = ChatModel(self, self.api_key, self.api_key_res, self.api_url, self.api_model, self.makeRequest,
                               self.pip_installer)
        self.server = ChatServer(self, self.model)
        self.server_thread = None
        self.running = False
        self.start_server()

        self.textToTalk = ""
        self.textSpeaker = "/Speaker Mita"
        self.textSpeakerMiku = "/set_person CrazyMita"

        self.silero_turn_off_video = False
        self.dialog_active = False

        self.patch_to_sound_file = ""
        self.id_sound = -1
        self.instant_send = False
        self.waiting_answer = False

        # Параметры для ленивой загрузки
        self.lazy_load_batch_size = 50
        self.total_messages_in_history = 0
        self.loaded_messages_offset = 0
        self.loading_more_history = False

        # Установка иконки и заголовка
        self.setWindowTitle(_("Чат с NeuroMita", "NeuroMita Chat"))
        self.setWindowIcon(QIcon('icon.png'))

        self.ffmpeg_install_popup = None
        QTimer.singleShot(100, self.check_and_install_ffmpeg)

        self.delete_all_sound_files()

        # Переменные для индикаторов статуса
        self.silero_connected = False
        self.game_connected_checkbox_var = False
        self.mic_recognition_active = False
        self.screen_capture_active = False
        self.camera_capture_active = False

        # Соединяем сигналы
        self.update_chat_signal.connect(self._insert_message_slot)
        self.update_status_signal.connect(self.update_status_colors)
        self.update_debug_signal.connect(self.update_debug_info)

        self.setup_ui()
        self.load_chat_history()

        try:
            microphone_settings.load_mic_settings(self)
        except Exception as e:
            logger.info("Не удалось удачно получить настройки микрофона", e)

        # Событие для синхронизации потоков
        self.loop_ready_event = threading.Event()

        self.loop = None
        self.asyncio_thread = threading.Thread(target=self.start_asyncio_loop, daemon=True)
        self.asyncio_thread.start()

        self.start_silero_async()

        # Загружаем настройки распознавания речи при запуске
        initial_recognizer_type = self.settings.get("RECOGNIZER_TYPE", "google")
        initial_vosk_model = self.settings.get("VOSK_MODEL", "vosk-model-ru-0.10")

        SpeechRecognition.set_recognizer_type(initial_recognizer_type)
        SpeechRecognition.vosk_model = initial_vosk_model

        # Запуск проверки переменной textToTalk через QTimer
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_text_to_talk_or_send)
        self.check_timer.start(150)

        QTimer.singleShot(500, self.initialize_last_local_model_on_startup)

        self.screen_capture_instance = ScreenCapture()
        self.screen_capture_thread = None
        self.screen_capture_running = False
        self.last_captured_frame = None
        self.image_request_thread = None
        self.image_request_running = False
        self.last_image_request_time = time.time()
        self.image_request_timer_running = False

        if self.settings.get("MIC_ACTIVE", False):
            SpeechRecognition.speach_recognition_start(self.device_id, self.loop)
            self.mic_recognition_active = True
            self.update_status_colors()

        if self.settings.get("ENABLE_SCREEN_ANALYSIS", False):
            logger.info("Настройка 'ENABLE_SCREEN_ANALYSIS' включена. Автоматический запуск захвата экрана.")
            self.start_screen_capture_thread()

        if self.settings.get("ENABLE_CAMERA_CAPTURE", False):
            logger.info("Настройка 'ENABLE_CAMERA_CAPTURE' включена. Автоматический запуск захвата с камеры.")
            self.start_camera_capture_thread()

    def start_asyncio_loop(self):
        """Запускает цикл событий asyncio в отдельном потоке."""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            logger.info("Цикл событий asyncio успешно запущен.")
            self.loop_ready_event.set()
            try:
                self.loop.run_forever()
            except Exception as e:
                logger.info(f"Ошибка в цикле событий asyncio: {e}")
            finally:
                self.loop.close()
        except Exception as e:
            logger.info(f"Ошибка при запуске цикла событий asyncio: {e}")
            self.loop_ready_event.set()

    def start_silero_async(self):
        """Отправляет задачу для запуска Silero в цикл событий."""
        logger.info("Ожидание готовности цикла событий...")
        self.loop_ready_event.wait()
        if self.loop and self.loop.is_running():
            logger.info("Запускаем Silero через цикл событий.")
            asyncio.run_coroutine_threadsafe(self.startSilero(), self.loop)
        else:
            logger.info("Ошибка: Цикл событий asyncio не запущен.")

    async def startSilero(self):
        """Асинхронный запуск обработчика Telegram Bot."""
        logger.info("Telegram Bot запускается!")
        try:
            if not self.api_id or not self.api_hash or not self.phone:
                logger.info("Ошибка: отсутствуют необходимые данные для Telegram бота")
                self.silero_connected = False
                return

            logger.info(f"Передаю в тг {SH(self.api_id)},{SH(self.api_hash)},{SH(self.phone)} (Должно быть не пусто)")

            self.bot_handler = TelegramBotHandler(self, self.api_id, self.api_hash, self.phone,
                                                  self.settings.get("AUDIO_BOT", "@silero_voice_bot"))

            try:
                await self.bot_handler.start()
                self.bot_handler_ready = True
                if hasattr(self, 'silero_connected') and self.silero_connected:
                    logger.info("ТГ успешно подключен")
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

    def run_in_thread(self, response):
        """Запуск асинхронной задачи в отдельном потоке."""
        self.loop_ready_event.wait()
        if self.loop and self.loop.is_running():
            logger.info("Запускаем асинхронную задачу в цикле событий...")
            self.loop.create_task(self.run_send_and_receive(self.textToTalk, self.get_speaker_text()))
        else:
            logger.info("Ошибка: Цикл событий asyncio не готов.")

    def get_speaker_text(self):
        if self.settings.get("AUDIO_BOT") == "@CrazyMitaAIbot":
            return self.textSpeakerMiku
        else:
            return self.textSpeaker

    async def run_send_and_receive(self, response, speaker_command, id=0):
        """Асинхронный метод для вызова send_and_receive."""
        logger.info("Попытка получить фразу")
        self.waiting_answer = True
        await self.bot_handler.send_and_receive(response, speaker_command, id)
        self.waiting_answer = False
        logger.info("Завершение получения фразы")

    def check_text_to_talk_or_send(self):
        """Периодическая проверка переменной self.textToTalk."""
        if bool(self.settings.get("SILERO_USE")) and self.textToTalk:
            self.voice_text()

        if self.image_request_timer_running:
            self.send_interval_image()

        if bool(self.settings.get("MIC_INSTANT_SENT")):
            if not self.waiting_answer:
                text_from_recognition = SpeechRecognition.receive_text()
                user_input = self.user_entry.toPlainText()
                user_input += text_from_recognition
                self.user_entry.insertPlainText(text_from_recognition)
                self.user_input = self.user_entry.toPlainText().strip()
                if not self.dialog_active:
                    self.send_instantly()

        elif bool(self.settings.get("MIC_ACTIVE")) and self.user_entry:
            text_from_recognition = SpeechRecognition.receive_text()
            self.user_entry.insertPlainText(text_from_recognition)
            self.user_input = self.user_entry.toPlainText().strip()

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
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.async_send_message(user_input="", system_input="", image_data=image_data),
                            self.loop)
                        self.last_image_request_time = current_time
                    else:
                        logger.error("Ошибка: Цикл событий не готов для периодической отправки изображений.")
                else:
                    logger.warning("Нет изображений для периодической отправки.")

    def voice_text(self):
        logger.info(f"Есть текст для отправки: {self.textToTalk} id {self.id_sound}")
        if self.loop and self.loop.is_running():
            try:
                self.voiceover_method = self.settings.get("VOICEOVER_METHOD", "TG")

                if self.voiceover_method == "TG":
                    logger.info("Используем Telegram (Silero/Miku) для озвучки")
                    asyncio.run_coroutine_threadsafe(
                        self.run_send_and_receive(self.textToTalk, self.get_speaker_text(), self.id_sound),
                        self.loop
                    )
                    self.textToTalk = ""

                elif self.voiceover_method == "Local":
                    selected_local_model_id = self.settings.get("NM_CURRENT_VOICEOVER", None)
                    if selected_local_model_id:
                        logger.info(f"Используем {selected_local_model_id} для локальной озвучки")
                        if self.local_voice.is_model_initialized(selected_local_model_id):
                            asyncio.run_coroutine_threadsafe(
                                self.run_local_voiceover(self.textToTalk),
                                self.loop
                            )
                            self.textToTalk = ""
                        else:
                            logger.warning(f"Модель {selected_local_model_id} выбрана, но не инициализирована. Озвучка не будет выполнена.")
                            self.textToTalk = ""
                    else:
                        logger.warning("Локальная озвучка выбрана, но конкретная модель не установлена/не выбрана.")
                        self.textToTalk = ""
                else:
                    logger.warning(f"Неизвестный метод озвучки: {self.voiceover_method}")
                    self.textToTalk = ""

                logger.info("Выполнено")
            except Exception as e:
                logger.error(f"Ошибка при отправке текста на озвучку: {e}")
                self.textToTalk = ""
        else:
            logger.error("Ошибка: Цикл событий не готов.")

    def send_instantly(self):
        """Мгновенная отправка распознанного текста"""
        try:
            if self.ConnectedToGame:
                self.instant_send = True
            else:
                self.send_message()

            SpeechRecognition._text_buffer.clear()
            SpeechRecognition._current_text = ""
        except Exception as e:
            logger.info(f"Ошибка обработки текста: {str(e)}")

    def clear_user_input(self):
        self.user_input = ""
        self.user_entry.clear()

    def on_enter_pressed(self):
        """Обработчик нажатия клавиши Enter в поле ввода."""
        self.send_message()

    def start_server(self):
        """Запускает сервер в отдельном потоке."""
        if not self.running:
            self.running = True
            self.server.start()
            self.server_thread = threading.Thread(target=self.run_server_loop, daemon=True)
            self.server_thread.start()
            logger.info("Сервер запущен.")

    def stop_server(self):
        """Останавливает сервер."""
        if self.running:
            self.running = False
            self.server.stop()
            logger.info("Сервер остановлен.")

    def run_server_loop(self):
        """Цикл обработки подключений сервера."""
        while self.running:
            needUpdate = self.server.handle_connection()
            if needUpdate:
                logger.info(f"[{time.strftime('%H:%M:%S')}] run_server_loop: Обнаружено needUpdate, вызываю load_chat_history.")
                QTimer.singleShot(0, self.load_chat_history)

    def setup_ui(self):
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Установка стилей
        self.setStyleSheet(get_stylesheet())
        
        # Главный layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Создаем splitter для изменения размеров панелей
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Левая панель
        left_widget = QWidget()
        splitter.addWidget(left_widget)
        self.setup_left_frame(left_widget)
        
        # Правая панель
        right_widget = QWidget()
        splitter.addWidget(right_widget)
        self.setup_right_frame(right_widget)
        
        # Устанавливаем начальные размеры
        splitter.setSizes([700, 500])
        
        main_layout.addWidget(splitter)
        
        # Устанавливаем размер окна
        self.resize(1200, 800)

    def setup_left_frame(self, parent):
        layout = QVBoxLayout(parent)
        layout.setSpacing(5)
        
        # Кнопки над чатом
        button_layout = QHBoxLayout()
        
        self.clear_chat_button = QPushButton(_("Очистить", "Clear"))
        self.clear_chat_button.clicked.connect(self.clear_chat_display)
        self.clear_chat_button.setMaximumHeight(30)
        
        self.load_history_button = QPushButton(_("Взять из истории", "Load from history"))
        self.load_history_button.clicked.connect(self.load_chat_history)
        self.load_history_button.setMaximumHeight(30)
        
        button_layout.addWidget(self.clear_chat_button)
        button_layout.addWidget(self.load_history_button)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Чат окно
        self.chat_window = QTextBrowser()
        self.chat_window.setOpenExternalLinks(False)
        self.chat_window.setReadOnly(True)
        initial_font_size = int(self.settings.get("CHAT_FONT_SIZE", 12))
        font = QFont("Arial", initial_font_size)
        self.chat_window.setFont(font)
        
        layout.addWidget(self.chat_window, 1)
        
        # Инпут секция
        input_frame = QFrame()
        input_frame.setStyleSheet(get_stylesheet())
        input_layout = QVBoxLayout(input_frame)
        
        # Метка для токенов
        self.token_count_label = QLabel(_("Токены: 0/0 | Стоимость: 0.00 ₽", "Tokens: 0/0 | Cost: 0.00 ₽"))
        self.token_count_label.setStyleSheet("font-size: 10px;")
        input_layout.addWidget(self.token_count_label)
        
        # Поле ввода и кнопка отправки
        input_row_layout = QHBoxLayout()
        
        self.user_entry = QTextEdit()
        self.user_entry.setMaximumHeight(60)
        self.user_entry.installEventFilter(self)
        
        self.send_button = QPushButton(_("Отправить", "Send"))
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setMaximumHeight(60)
        
        input_row_layout.addWidget(self.user_entry)
        input_row_layout.addWidget(self.send_button)
        
        input_layout.addLayout(input_row_layout)
        layout.addWidget(input_frame)

    def eventFilter(self, obj, event):
        """Обработчик событий для перехвата Enter в QTextEdit"""
        from PyQt6.QtCore import QEvent
        # Импорт QKeyEvent здесь больше не нужен, но можно и оставить
        from PyQt6.QtGui import QKeyEvent
        
        if obj == self.user_entry and event.type() == QEvent.Type.KeyPress:
            # 'event' уже является нужным нам объектом QKeyEvent.
            # Используем его напрямую.
            if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.send_message()
                return True
        return super().eventFilter(obj, event)

    def setup_right_frame(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Создаем скроллинг область
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Контейнер для настроек
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setSpacing(10)
        
        # Добавляем все секции настроек
        status_indicators.create_status_indicators(self, settings_layout)
        language_settings.create_language_section(self, settings_layout)
        api_settings.setup_api_controls(self, settings_layout)
        g4f_settings.setup_g4f_controls(self, settings_layout)
        general_model_settings.setup_general_settings_control(self, settings_layout)
        voiceover_settings.setup_voiceover_controls(self, settings_layout)
        microphone_settings.setup_microphone_controls(self, settings_layout)
        character_settings.setup_mita_controls(self, settings_layout)
        #prompt_catalogue_settings.setup_prompt_catalogue_controls(self, settings_layout) # ВРЕМЕННО УБРАЛ
        self.setup_debug_controls(settings_layout)
        self.setup_common_controls(settings_layout)
        gamemaster_settings.setup_game_master_controls(self, settings_layout)
        history_compressor.setup_history_compressor_controls(self, settings_layout)
        chat_settings.setup_chat_settings_controls(self, settings_layout)
        screen_analysis_settings.setup_screen_analysis_controls(self, settings_layout)
        token_settings.setup_token_settings_controls(self, settings_layout)
        command_replacer_settings.setup_command_replacer_controls(self, settings_layout)
        self.setup_news_control(settings_layout)
        
        # Добавляем растягивающийся элемент в конец
        settings_layout.addStretch()
        
        scroll_area.setWidget(settings_widget)
        layout.addWidget(scroll_area)
        
        # Сворачиваем все секции по умолчанию
        for i in range(settings_layout.count()):
            widget = settings_layout.itemAt(i).widget()
            if isinstance(widget, CollapsibleSection):
                widget.collapse()

    def _insert_message_slot(self, role, content, insert_at_start, message_time):
        """Слот для вставки сообщения в UI потоке"""
        self.insert_message(role, content, insert_at_start, message_time)

    def insert_message(self, role, content, insert_at_start=False, message_time=""):
        logger.info(f"insert_message вызван. Роль: {role}, Содержимое: {str(content)[:50]}...")
        
        if not hasattr(self, '_images_in_chat'):
            self._images_in_chat = []
        
        processed_content_parts = []
        has_image_content = False
        
        # Обработка контента
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        processed_content_parts.append(
                            {"type": "text", "content": item.get("text", ""), "tag": "default"})
                    elif item.get("type") == "image_url":
                        has_image_content = self.process_image_for_chat(has_image_content, item,
                                                                        processed_content_parts)
            
            if has_image_content and not any(
                    part["type"] == "text" and part["content"].strip() for part in processed_content_parts):
                processed_content_parts.insert(0, {"type": "text",
                                                   "content": _("<Изображение экрана>", "<Screen Image>") + "\n",
                                                   "tag": "default"})
                
        elif isinstance(content, str):
            processed_content_parts.append({"type": "text", "content": content, "tag": "default"})
        else:
            return
        
        # Обработка тегов
        processed_text_parts = []
        hide_tags = self.settings.get("HIDE_CHAT_TAGS", False)
        
        for part in processed_content_parts:
            if part["type"] == "text":
                text_content = part["content"]
                if hide_tags:
                    text_content = process_text_to_voice(text_content)
                    processed_text_parts.append({"type": "text", "content": text_content, "tag": "default"})
                else:
                    # Здесь обработка тегов аналогично оригиналу
                    processed_text_parts.append({"type": "text", "content": text_content, "tag": "default"})
            else:
                processed_text_parts.append(part)
        
        # Вставка сообщений
        cursor = self.chat_window.textCursor()
        
        show_timestamps = self.settings.get("SHOW_CHAT_TIMESTAMPS", False)
        timestamp_str = "[???] "
        if show_timestamps:
            if message_time:
                timestamp_str = f"[{message_time}]"
            else:
                timestamp_str = time.strftime("[%H:%M:%S] ")
        
        if insert_at_start:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Форматирование и вставка текста
        if show_timestamps:
            self._insert_formatted_text(cursor, timestamp_str, QColor("#888888"), italic=True)
        
        if role == "user":
            self._insert_formatted_text(cursor, _("Вы: ", "You: "), QColor("gold"), bold=True)
        elif role == "assistant":
            self._insert_formatted_text(cursor, f"{self.model.current_character.name}: ", QColor("hot pink"), bold=True)
        
        # Вставка контента
        for part in processed_text_parts:
            if part["type"] == "text":
                color = None
                if part["tag"] == "tag_green":
                    color = QColor("#00FF00")
                self._insert_formatted_text(cursor, part["content"], color)
            elif part["type"] == "image":
                cursor.insertImage(part["content"])
                cursor.insertText("\n")
        
        # Добавляем переводы строк
        if role == "user":
            cursor.insertText("\n")
        elif role in {"assistant", "system"}:
            cursor.insertText("\n\n")
        
        # Автоматическая прокрутка вниз
        if not insert_at_start:
            self.chat_window.verticalScrollBar().setValue(
                self.chat_window.verticalScrollBar().maximum()
            )

    def _insert_formatted_text(self, cursor, text, color=None, bold=False, italic=False):
        """Вставляет форматированный текст в позицию курсора"""
        char_format = QTextCharFormat()
        
        if color:
            char_format.setForeground(color)
        
        font = QFont("Arial", int(self.settings.get("CHAT_FONT_SIZE", 12)))
        if bold:
            font.setBold(True)
        if italic:
            font.setItalic(True)
        
        char_format.setFont(font)
        cursor.insertText(text, char_format)

    def append_message(self, text):
        cursor = self.chat_window.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter, QTextCursor.MoveMode.MoveAnchor, 2)
        cursor.insertText(text)
        self.chat_window.verticalScrollBar().setValue(
            self.chat_window.verticalScrollBar().maximum()
        )

    def process_image_for_chat(self, has_image_content, item, processed_content_parts):
        image_data_base64 = item.get("image_url", {}).get("url", "")
        if image_data_base64.startswith("data:image/jpeg;base64,"):
            image_data_base64 = image_data_base64.replace("data:image/jpeg;base64,", "")
        elif image_data_base64.startswith("data:image/png;base64,"):
            image_data_base64 = image_data_base64.replace("data:image/png;base64,", "")
        
        try:
            from PIL import Image
            image_bytes = base64.b64decode(image_data_base64)
            image = Image.open(io.BytesIO(image_bytes))
            
            # Изменение размера
            max_width = 400
            max_height = 300
            original_width, original_height = image.size
            
            if original_width > max_width or original_height > max_height:
                ratio = min(max_width / original_width, max_height / original_height)
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Конвертируем PIL Image в QImage
            image_bytes = io.BytesIO()
            image.save(image_bytes, format='PNG')
            image_bytes.seek(0)
            
            qimage = QImage()
            qimage.loadFromData(image_bytes.getvalue())
            
            processed_content_parts.append({"type": "image", "content": qimage})
            has_image_content = True
        except Exception as e:
            logger.error(f"Ошибка при декодировании или обработке изображения: {e}")
            processed_content_parts.append(
                {"type": "text", "content": _("<Ошибка загрузки изображения>", "<Image load error>")})
        
        return has_image_content

    def _check_and_perform_pending_update(self):
        """Проверяет, запланировано ли обновление g4f, и выполняет его."""
        if not self.pip_installer:
            logger.warning("PipInstaller не инициализирован, проверка отложенного обновления пропущена.")
            return

        update_pending = self.settings.get("G4F_UPDATE_PENDING", False)
        target_version = self.settings.get("G4F_TARGET_VERSION", None)

        if update_pending and target_version:
            logger.info(f"Обнаружено запланированное обновление g4f до версии: {target_version}")
            package_spec = f"g4f=={target_version}" if target_version != "latest" else "g4f"
            description = f"Запланированное обновление g4f до {target_version}..."

            success = False
            try:
                success = self.pip_installer.install_package(
                    package_spec,
                    description=description,
                    extra_args=["--force-reinstall", "--upgrade"]
                )
                if success:
                    logger.info(f"Запланированное обновление g4f до {target_version} успешно завершено.")
                    try:
                        importlib.invalidate_caches()
                        logger.info("Кэш импорта очищен после запланированного обновления.")
                    except Exception as e_invalidate:
                        logger.error(f"Ошибка при очистке кэша импорта после обновления: {e_invalidate}")
                else:
                    logger.error(f"Запланированное обновление g4f до {target_version} не удалось (ошибка pip).")
            except Exception as e_install:
                logger.error(f"Исключение во время запланированного обновления g4f: {e_install}", exc_info=True)
                success = False

            finally:
                logger.info("Сброс флагов запланированного обновления g4f.")
                self.settings.set("G4F_UPDATE_PENDING", False)
                self.settings.set("G4F_TARGET_VERSION", None)
                self.settings.save_settings()
        else:
            logger.info("Нет запланированных обновлений g4f.")

    def trigger_g4f_reinstall_schedule(self):
        """Считывает версию из поля ввода, сохраняет ее и флаг для обновления при следующем запуске."""
        logger.info("Запрос на планирование обновления g4f...")

        target_version = None
        if hasattr(self, 'g4f_version_entry') and self.g4f_version_entry:
            target_version = self.g4f_version_entry.text().strip()
            if not target_version:
                QMessageBox.critical(self, _("Ошибка", "Error"),
                                   _("Пожалуйста, введите версию g4f или 'latest'.",
                                     "Please enter a g4f version or 'latest'."))
                return
        else:
            logger.error("Виджет entry для версии g4f не найден.")
            QMessageBox.critical(self, _("Ошибка", "Error"),
                               _("Не найден элемент интерфейса для ввода версии.",
                                 "UI element for version input not found."))
            return

        try:
            self.settings.set("G4F_TARGET_VERSION", target_version)
            self.settings.set("G4F_UPDATE_PENDING", True)
            self.settings.set("G4F_VERSION", target_version)
            self.settings.save_settings()
            logger.info(f"Обновление g4f до версии '{target_version}' запланировано на следующий запуск.")

            QMessageBox.information(self, _("Запланировано", "Scheduled"),
                _("Версия g4f '{version}' будет установлена/обновлена при следующем запуске программы.",
                  "g4f version '{version}' will be installed/updated the next time the program starts.").format(
                    version=target_version))
        except Exception as e:
            logger.error(f"Ошибка при сохранении настроек для запланированного обновления: {e}", exc_info=True)
            QMessageBox.critical(self, _("Ошибка сохранения", "Save Error"),
                _("Не удалось сохранить настройки для обновления. Пожалуйста, проверьте логи.",
                  "Failed to save settings for the update. Please check the logs."))

    def update_game_connection(self, is_connected):
        self.ConnectedToGame = is_connected
        QTimer.singleShot(0, self.update_status_colors)

    def update_all(self):
        self.update_status_colors()
        self.update_debug_info()

    def update_status_colors(self):
        """Обновляет цвета индикаторов статуса"""
        self.game_connected_checkbox_var = self.ConnectedToGame
        
        # Обновление чекбоксов если они существуют
        if hasattr(self, 'game_status_checkbox'):
            self.game_status_checkbox.setChecked(self.ConnectedToGame)
            
        if hasattr(self, 'silero_status_checkbox'):
            self.silero_status_checkbox.setChecked(self.silero_connected)
            
        if hasattr(self, 'mic_status_checkbox'):
            self.mic_status_checkbox.setChecked(self.mic_recognition_active)
            
        if hasattr(self, 'screen_capture_status_checkbox'):
            self.screen_capture_status_checkbox.setChecked(self.screen_capture_active)
            
        if hasattr(self, 'camera_capture_status_checkbox'):
            self.camera_capture_status_checkbox.setChecked(self.camera_capture_active)

    def load_chat_history(self):
        self.clear_chat_display()
        self.loaded_messages_offset = 0
        self.total_messages_in_history = 0
        self.loading_more_history = False

        chat_history = self.model.current_character.load_history()
        all_messages = chat_history["messages"]
        self.total_messages_in_history = len(all_messages)
        logger.info(f"[{time.strftime('%H:%M:%S')}] Всего сообщений в истории: {self.total_messages_in_history}")

        max_display_messages = int(self.settings.get("MAX_CHAT_HISTORY_DISPLAY", 100))
        start_index = max(0, self.total_messages_in_history - max_display_messages)
        messages_to_load = all_messages[start_index:]

        for entry in messages_to_load:
            role = entry["role"]
            content = entry["content"]
            message_time = entry.get("time", "???")
            self.insert_message(role, content, message_time=message_time)

        self.loaded_messages_offset = len(messages_to_load)
        logger.info(f"[{time.strftime('%H:%M:%S')}] Загружено {self.loaded_messages_offset} последних сообщений.")

        self.update_debug_info()
        self.update_token_count()
        
        # Автоматическая прокрутка вниз
        self.chat_window.verticalScrollBar().setValue(
            self.chat_window.verticalScrollBar().maximum()
        )

    def setup_debug_controls(self, parent_layout):
        debug_config = [
            {'label': '', 'key': 'debug_window', 'type': 'text_area', 'height': 5}
        ]
        
        section = self.create_settings_section(parent_layout, _("Отладка", "Debug"), debug_config)
        
        # Находим QTextEdit в секции
        for i in range(section.content_layout.count()):
            widget = section.content_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'findChild'):
                text_edit = widget.findChild(QTextEdit)
                if text_edit:
                    self.debug_window = text_edit
                    break
        
        self.update_debug_info()

    def setup_common_controls(self, parent_layout):
        common_config = [
            {'label': _('Скрывать (приватные) данные', 'Hide (private) data'), 'key': 'HIDE_PRIVATE',
             'type': 'checkbutton', 'default_checkbutton': True},
        ]
        self.create_settings_section(parent_layout, _("Общие настройки", "Common settings"), common_config)

    # Методы валидации остаются без изменений
    def validate_number_0_60(self, new_value):
        if not new_value.isdigit():
            return False
        return 0 <= int(new_value) <= 60

    def validate_float_0_1(self, new_value):
        try:
            val = float(new_value)
            return 0.0 <= val <= 1.0
        except ValueError:
            return False

    def validate_float_positive(self, new_value):
        try:
            val = float(new_value)
            return val > 0.0
        except ValueError:
            return False

    def validate_float_positive_or_zero(self, new_value):
        if new_value == "": return True
        try:
            value = float(new_value)
            return value >= 0.0
        except ValueError:
            return False

    def validate_positive_integer(self, new_value):
        if new_value == "": return True
        try:
            value = int(new_value)
            return value > 0
        except ValueError:
            return False

    def validate_positive_integer_or_zero(self, new_value):
        if new_value == "": return True
        try:
            value = int(new_value)
            return value >= 0
        except ValueError:
            return False

    def validate_float_0_to_1(self, new_value):
        if new_value == "": return True
        try:
            value = float(new_value)
            return 0.0 <= value <= 1.0
        except ValueError:
            return False

    def validate_float_0_to_2(self, new_value):
        if new_value == "": return True
        try:
            value = float(new_value)
            return 0.0 <= value <= 2.0
        except ValueError:
            return False

    def validate_float_minus2_to_2(self, new_value):
        if new_value == "": return True
        try:
            value = float(new_value)
            return -2.0 <= value <= 2.0
        except ValueError:
            return False

    def load_api_settings(self, update_model):
        """Загружает настройки из файла"""
        logger.info("Начинаю загрузку настроек")

        if not os.path.exists(self.config_path):
            logger.info("Не найден файл настроек")
            return

        try:
            with open(self.config_path, "rb") as f:
                encoded = f.read()
            decoded = base64.b64decode(encoded)
            settings = json.loads(decoded.decode("utf-8"))

            self.api_key = settings.get("NM_API_KEY", "")
            self.api_key_res = settings.get("NM_API_KEY_RES", "")
            self.api_url = settings.get("NM_API_URL", "")
            self.api_model = settings.get("NM_API_MODEL", "")
            self.makeRequest = settings.get("NM_API_REQ", False)

            self.api_id = settings.get("NM_TELEGRAM_API_ID", "")
            self.api_hash = settings.get("NM_TELEGRAM_API_HASH", "")
            self.phone = settings.get("NM_TELEGRAM_PHONE", "")

            logger.info(f"Итого загружено {SH(self.api_key)},{SH(self.api_key_res)},{self.api_url},{self.api_model},{self.makeRequest} (Должно быть не пусто)")
            logger.info(f"По тг {SH(self.api_id)},{SH(self.api_hash)},{SH(self.phone)} (Должно быть не пусто если тг)")
            
            if update_model:
                if self.api_key:
                    self.model.api_key = self.api_key
                if self.api_url:
                    self.model.api_url = self.api_url
                if self.api_model:
                    self.model.api_model = self.api_model
                self.model.makeRequest = self.makeRequest
                self.model.update_openai_client()

            logger.info("Настройки загружены из файла")
        except Exception as e:
            logger.info(f"Ошибка загрузки: {e}")

    def update_debug_info(self):
        """Обновить окно отладки с отображением актуальных данных."""
        if hasattr(self, 'debug_window') and self.debug_window:
            self.debug_window.clear()
            debug_info = self.model.current_character.current_variables_string()
            self.debug_window.insertPlainText(debug_info)

    def update_token_count(self, event=None):
        show_token_info = self.settings.get("SHOW_TOKEN_INFO", True)

        if show_token_info and self.model.hasTokenizer:
            current_context_tokens = self.model.get_current_context_token_count()

            token_cost_input = float(self.settings.get("TOKEN_COST_INPUT", 0.000001))
            token_cost_output = float(self.settings.get("TOKEN_COST_OUTPUT", 0.000002))
            max_model_tokens = int(self.settings.get("MAX_MODEL_TOKENS", 32000))

            self.model.token_cost_input = token_cost_input
            self.model.token_cost_output = token_cost_output
            self.model.max_model_tokens = max_model_tokens

            cost = self.model.calculate_cost_for_current_context()

            self.token_count_label.setText(
                _("Токены: {}/{} (Макс. токены: {}) | Ориент. стоимость: {:.4f} ₽",
                  "Tokens: {}/{} (Max tokens: {}) | Approx. cost: {:.4f} ₽").format(
                    current_context_tokens, max_model_tokens, max_model_tokens, cost
                )
            )
            self.token_count_label.setVisible(True)
        else:
            self.token_count_label.setVisible(False)
            self.token_count_label.setText(
                _("Токены: Токенизатор недоступен", "Tokens: Tokenizer not available")
            )
        self.update_debug_info()

    def clear_chat_display(self):
        """Очищает отображаемую историю чата в GUI."""
        self.chat_window.clear()

    def send_message(self, system_input: str = "", image_data: list[bytes] = None):
        user_input = self.user_entry.toPlainText().strip()
        current_image_data = []
        
        if self.settings.get("ENABLE_SCREEN_ANALYSIS", False):
            history_limit = int(self.settings.get("SCREEN_CAPTURE_HISTORY_LIMIT", 1))
            frames = self.screen_capture_instance.get_recent_frames(history_limit)
            if frames:
                current_image_data.extend(frames)
            else:
                logger.info("Анализ экрана включен, но кадры не готовы или история пуста.")

        all_image_data = (image_data if image_data is not None else []) + current_image_data

        if self.settings.get("ENABLE_CAMERA_CAPTURE", False):
            if hasattr(self, 'camera_capture') and self.camera_capture is not None and self.camera_capture.is_running():
                history_limit = int(self.settings.get("CAMERA_CAPTURE_HISTORY_LIMIT", 1))
                camera_frames = self.camera_capture.get_recent_frames(history_limit)
                if camera_frames:
                    all_image_data.extend(camera_frames)
                    logger.info(f"Добавлено {len(camera_frames)} кадров с камеры для отправки.")
                else:
                    logger.info("Захват с камеры включен, но кадры не готовы или история пуста.")

        if not user_input and not system_input:
            return

        self.last_image_request_time = time.time()

        if user_input:
            self.insert_message("user", user_input)
            self.user_entry.clear()

        if all_image_data:
            image_content_for_display = [{"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{base64.b64encode(img).decode('utf-8')}"}} for img in all_image_data]
            if not user_input:
                image_content_for_display.insert(0, {"type": "text",
                                                     "content": _("<Изображение экрана>", "<Screen Image>") + "\n"})
            self.insert_message("user", image_content_for_display)

        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.async_send_message(user_input, system_input, all_image_data),
                                             self.loop)

    async def async_send_message(
        self,
        user_input: str,
        system_input: str = "",
        image_data: list[bytes] | None = None
    ):
        """
        Асинхронно генерирует ответ модели и передаёт его в GUI-поток.

        Параметры
        ----------
        user_input : str
            Текст пользователя.
        system_input : str, optional
            Дополнительный системный промпт.
        image_data : list[bytes] | None, optional
            Снимки экрана / камеры, если есть.
        """
        try:
            # Генерация ответа модели в пуле потоков
            response = await asyncio.wait_for(
                self.loop.run_in_executor(
                    None,
                    lambda: self.model.generate_response(
                        user_input,
                        system_input,
                        image_data
                    )
                ),
                timeout=60.0
            )

            # --- ОБНОВЛЯЕМ GUI ЧЕРЕЗ СИГНАЛ ---
            # role, content, insert_at_start, message_time
            self.update_chat_signal.emit("assistant", response, False, "")

            # Дополнительные обновления (статусы, токены)
            self.update_status_signal.emit()
            QTimer.singleShot(0, self.update_token_count)

            # Отдаём ответ в сервер (игра)
            if self.server and self.server.client_socket:
                try:
                    self.server.send_message_to_server(response)
                    logger.info("Ответ отправлен в игру.")
                except Exception as e:
                    logger.error(f"Не удалось отправить ответ в игру: {e}")
        except asyncio.TimeoutError:
            logger.warning("Тайм-аут: генерация ответа заняла слишком много времени.")
        except Exception as e:
            logger.error(f"Ошибка в async_send_message: {e}", exc_info=True)

    def start_camera_capture_thread(self):
        if not hasattr(self, 'camera_capture') or self.camera_capture is None:
            from CameraCapture import CameraCapture
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
            self.update_status_colors()

    def stop_camera_capture_thread(self):
        if hasattr(self, 'camera_capture') and self.camera_capture is not None and self.camera_capture.is_running():
            self.camera_capture.stop_capture()
            logger.info("Поток захвата с камеры остановлен.")
        self.camera_capture_active = False
        self.update_status_colors()

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
            self.update_status_colors()

    def stop_screen_capture_thread(self):
        if self.screen_capture_running:
            self.screen_capture_instance.stop_capture()
            self.screen_capture_running = False
            logger.info("Поток захвата экрана остановлен.")
        self.screen_capture_active = False
        self.update_status_colors()

    def start_image_request_timer(self):
        if not self.image_request_timer_running:
            self.image_request_timer_running = True
            self.last_image_request_time = time.time()
            logger.info("Таймер периодической отправки изображений запущен.")

    def stop_image_request_timer(self):
        if self.image_request_timer_running:
            self.image_request_timer_running = False
            logger.info("Таймер периодической отправки изображений остановлен.")

    def load_more_history(self):
        """Загружает предыдущие сообщения в чат, сохраняя позицию прокрутки."""
        if self.loaded_messages_offset >= self.total_messages_in_history:
            return

        self.loading_more_history = True
        try:
            chat_history = self.model.current_character.load_history()
            all_messages = chat_history["messages"]

            end_index = self.total_messages_in_history - self.loaded_messages_offset
            start_index = max(0, end_index - self.lazy_load_batch_size)
            messages_to_prepend = all_messages[start_index:end_index]

            if not messages_to_prepend:
                self.loading_more_history = False
                return

            # Сохраняем текущую позицию прокрутки
            scrollbar = self.chat_window.verticalScrollBar()
            old_value = scrollbar.value()
            old_max = scrollbar.maximum()

            # Вставляем сообщения в начало
            for entry in reversed(messages_to_prepend):
                role = entry["role"]
                content = entry["content"]
                message_time = entry.get("time", "???")
                self.insert_message(role, content, insert_at_start=True, message_time=message_time)

            # Восстанавливаем позицию прокрутки
            QTimer.singleShot(0, lambda: scrollbar.setValue(scrollbar.maximum() - old_max + old_value))

            self.loaded_messages_offset += len(messages_to_prepend)
            logger.info(f"Загружено еще {len(messages_to_prepend)} сообщений. Всего загружено: {self.loaded_messages_offset}")

        finally:
            self.loading_more_history = False

    def _show_loading_popup(self, message):
        """Показать окно загрузки"""
        self.loading_popup = QDialog(self)
        self.loading_popup.setWindowTitle(" ")
        self.loading_popup.setFixedSize(300, 100)
        self.loading_popup.setModal(True)
        
        layout = QVBoxLayout(self.loading_popup)
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        self.loading_popup.show()

    def _close_loading_popup(self):
        if hasattr(self, 'loading_popup') and self.loading_popup:
            self.loading_popup.close()
            self.loading_popup = None

    def all_settings_actions(self, key, value):
        """Обработчик изменения настроек"""
        # Весь код остается таким же, как в оригинале
        if key in ["SILERO_USE", "VOICEOVER_METHOD", "AUDIO_BOT"]:
            self.switch_voiceover_settings()

        if key == "SILERO_TIME":
            self.bot_handler.silero_time_limit = int(value)

        if key == "AUDIO_BOT":
            if value.startswith("@CrazyMitaAIbot"):
                QMessageBox.information(self, "Информация",
                    "VinerX: наши товарищи из CrazyMitaAIbot предоставляет озвучку бесплатно буквально со своих пк, будет время - загляните к ним в тг, скажите спасибо)")

            if self.bot_handler:
                self.bot_handler.tg_bot = value

        elif key == "CHARACTER":
            self.model.current_character_to_change = value
            self.model.check_change_current_character()

        elif key == "NM_API_MODEL":
            self.model.api_model = value.strip()
        elif key == "NM_API_KEY":
            self.model.api_key = value.strip()
        elif key == "NM_API_URL":
            self.model.api_url = value.strip()
        elif key == "NM_API_REQ":
            self.model.makeRequest = bool(value)
        elif key == "gpt4free_model":
            self.model.gpt4free_model = value.strip()


        elif key == "MODEL_MAX_RESPONSE_TOKENS":
            self.model.max_response_tokens = int(value)
        elif key == "MODEL_TEMPERATURE":
            self.model.temperature = float(value)
        elif key == "MODEL_PRESENCE_PENALTY":
            self.model.presence_penalty = float(value)
        elif key == "MODEL_FREQUENCY_PENALTY":
            self.model.frequency_penalty = float(value)
        elif key == "MODEL_LOG_PROBABILITY":
            self.model.log_probability = float(value)
        elif key == "MODEL_TOP_K":
            self.model.top_k = int(value)
        elif key == "MODEL_TOP_P":
            self.model.top_p = float(value)
        elif key == "MODEL_THOUGHT_PROCESS":
            self.model.thinking_budget = float(value)



        elif key == "MODEL_MESSAGE_LIMIT":
            self.model.memory_limit = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_COUNT":
            self.model.max_request_attempts = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_TIME":
            self.model.request_delay = float(value)

        elif key == "MIC_ACTIVE":
            if bool(value):
                # Запускаем распознавание, если оно активировано
                SpeechRecognition.speach_recognition_start(self.device_id, self.loop)
                self.mic_recognition_active.set(True)
            else:
                # Останавливаем распознавание, если оно деактивировано
                SpeechRecognition.speach_recognition_stop()
                self.mic_recognition_active.set(False)
            self.update_status_colors()

        elif key == "ENABLE_SCREEN_ANALYSIS":
            if bool(value):
                self.start_screen_capture_thread()
            else:
                self.stop_screen_capture_thread()
        elif key == "ENABLE_CAMERA_CAPTURE":
            if bool(value):
                self.start_camera_capture_thread()
            else:
                self.stop_camera_capture_thread()
        elif key in ["SCREEN_CAPTURE_INTERVAL", "SCREEN_CAPTURE_QUALITY", "SCREEN_CAPTURE_FPS",
                     "SCREEN_CAPTURE_HISTORY_LIMIT", "SCREEN_CAPTURE_TRANSFER_LIMIT", "SCREEN_CAPTURE_WIDTH",
                     "SCREEN_CAPTURE_HEIGHT"]:
            # Если поток захвата экрана запущен, перезапускаем его с новыми настройками
            if self.screen_capture_instance and self.screen_capture_instance.is_running():
                logger.info(f"Настройка захвата экрана '{key}' изменена на '{value}'. Перезапускаю поток захвата.")
                self.stop_screen_capture_thread()
                self.start_screen_capture_thread()
            else:
                logger.info(
                    f"Настройка захвата экрана '{key}' изменена на '{value}'. Поток захвата не активен, изменения будут применены при следующем запуске.")
        elif key == "SEND_IMAGE_REQUESTS":
            if bool(value):
                self.start_image_request_timer()
            else:
                self.stop_image_request_timer()
        elif key == "IMAGE_REQUEST_INTERVAL":
            if self.image_request_timer_running:
                logger.info(f"Настройка интервала запросов изображений изменена на '{value}'. Перезапускаю таймер.")
                self.stop_image_request_timer()
                self.start_image_request_timer()
            else:
                logger.info(
                    f"Настройка интервала запросов изображений изменена на '{value}'. Таймер не активен, изменения будут применены при следующем запуске.")
        elif key in ["EXCLUDE_GUI_WINDOW", "EXCLUDE_WINDOW_TITLE"]:
            # Получаем текущие значения настроек
            exclude_gui = self.settings.get("EXCLUDE_GUI_WINDOW", False)
            exclude_title = self.settings.get("EXCLUDE_WINDOW_TITLE", "")

            hwnd_to_pass = None
            if exclude_gui:
                # Если включено исключение GUI, получаем HWND текущего окна Tkinter
                hwnd_to_pass = self.root.winfo_id()
                logger.info(f"Получен HWND окна GUI для исключения: {hwnd_to_pass}")
            elif exclude_title:
                # Если указан заголовок, пытаемся найти HWND по заголовку
                try:
                    hwnd_to_pass = win32gui.FindWindow(None, exclude_title)
                    if hwnd_to_pass:
                        logger.info(f"Найден HWND для заголовка '{exclude_title}': {hwnd_to_pass}")
                    else:
                        logger.warning(f"Окно с заголовком '{exclude_title}' не найдено.")
                except Exception as e:
                    logger.error(f"Ошибка при поиске окна по заголовку '{exclude_title}': {e}")

            # Передаем параметры в ScreenCapture
            if self.screen_capture_instance:
                self.screen_capture_instance.set_exclusion_parameters(hwnd_to_pass, exclude_title,
                                                                      exclude_gui or bool(exclude_title))
                logger.info(
                    f"Параметры исключения окна переданы в ScreenCapture: exclude_gui={exclude_gui}, exclude_title='{exclude_title}'")

            # Если поток захвата экрана запущен, перезапускаем его с новыми настройками
            if self.screen_capture_instance and self.screen_capture_instance.is_running():
                logger.info(f"Настройка исключения окна '{key}' изменена на '{value}'. Перезапускаю поток захвата.")
                self.stop_screen_capture_thread()
                self.start_screen_capture_thread()
            else:
                logger.info(
                    f"Настройка исключения окна '{key}' изменена на '{value}'. Поток захвата не активен, изменения будут применены при следующем запуске.")
        elif key == "RECOGNIZER_TYPE":
            # Останавливаем текущее распознавание
            SpeechRecognition.active = False
            # Даем время на завершение текущего потока
            time.sleep(0.1)  # Небольшая задержка

            # Устанавливаем новый тип распознавателя
            SpeechRecognition.set_recognizer_type(value)

            # Перезапускаем распознавание с новым типом
            if self.settings.get("MIC_ACTIVE", False):
                SpeechRecognition.active = True  # Активируем снова, только если был активен
                SpeechRecognition.speach_recognition_start(self.device_id, self.loop)
            microphone_settings.update_vosk_model_visibility(self, value)
        elif key == "VOSK_MODEL":
            SpeechRecognition.vosk_model = value
        elif key == "SILENCE_THRESHOLD":
            SpeechRecognition.SILENCE_THRESHOLD = float(value)
        elif key == "SILENCE_DURATION":
            SpeechRecognition.SILENCE_DURATION = float(value)
        elif key == "VOSK_PROCESS_INTERVAL":
            SpeechRecognition.VOSK_PROCESS_INTERVAL = float(value)
        elif key == "IMAGE_QUALITY_REDUCTION_ENABLED":
            self.model.image_quality_reduction_enabled = bool(value)

            self.model.image_quality_reduction_start_index = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_USE_PERCENTAGE":
            self.model.image_quality_reduction_use_percentage = bool(value)
        elif key == "IMAGE_QUALITY_REDUCTION_MIN_QUALITY":
            self.model.image_quality_reduction_min_quality = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_DECREASE_RATE":
            self.model.image_quality_reduction_decrease_rate = int(value)

        elif key == "ENABLE_HISTORY_COMPRESSION_ON_LIMIT":
            self.model.enable_history_compression_on_limit = bool(value)
        elif key == "ENABLE_HISTORY_COMPRESSION_PERIODIC":
            self.model.enable_history_compression_periodic = bool(value)
        elif key == "HISTORY_COMPRESSION_OUTPUT_TARGET":
            self.model.history_compression_output_target = str(value)
        elif key == "HISTORY_COMPRESSION_PERIODIC_INTERVAL":
            self.model.history_compression_periodic_interval = int(value)
        elif key == "HISTORY_COMPRESSION_MIN_PERCENT_TO_COMPRESS":
            self.model.history_compression_min_messages_to_compress = float(value)

            # Handle chat specific settings keys
        if key == "CHAT_FONT_SIZE":
            try:
                font_size = int(value)
                # Обновляем размер шрифта для всех тегов, использующих "Arial"
                for tag_name in self.chat_window.tag_names():
                    current_font = self.chat_window.tag_cget(tag_name, "font")
                    if "Arial" in current_font:
                        # Разбираем текущий шрифт, чтобы сохранить стиль (bold, italic)
                        font_parts = current_font.split()
                        new_font_parts = ["Arial", str(font_size)]
                        if "bold" in font_parts:
                            new_font_parts.append("bold")
                        if "italic" in font_parts:
                            new_font_parts.append("italic")
                        self.chat_window.tag_configure(tag_name, font=(" ".join(new_font_parts)))
                logger.info(f"Размер шрифта чата изменен на: {font_size}")
            except ValueError:
                logger.warning(f"Неверное значение для размера шрифта чата: {value}")
            except Exception as e:
                logger.error(f"Ошибка при изменении размера шрифта чата: {e}")
        elif key == "SHOW_CHAT_TIMESTAMPS":
            # Перезагружаем историю чата, чтобы применить/убрать метки времени
            self.load_chat_history()
            logger.info(f"Настройка 'Показывать метки времени' изменена на: {value}. История чата перезагружена.")
        elif key == "MAX_CHAT_HISTORY_DISPLAY":
            # Перезагружаем историю чата, чтобы применить новое ограничение
            self.load_chat_history()
            logger.info(f"Настройка 'Макс. сообщений в истории' изменена на: {value}. История чата перезагружена.")
        elif key == "HIDE_CHAT_TAGS":
            # Перезагружаем историю чата, чтобы применить/убрать скрытие тегов
            self.load_chat_history()
            logger.info(f"Настройка 'Скрывать теги' изменена на: {value}. История чата перезагружена.")


        elif key == "SHOW_TOKEN_INFO":
            self.update_token_count()
        elif key == "TOKEN_COST_INPUT":
            self.model.token_cost_input = float(value)
            self.update_token_count()
        elif key == "TOKEN_COST_OUTPUT":
            self.model.token_cost_output = float(value)
            self.update_token_count()
        elif key == "MAX_MODEL_TOKENS":
            self.model.max_model_tokens = int(value)
            self.update_token_count()


    def create_settings_section(self, parent_layout, title, settings_config):
        return guiTemplates.create_settings_section(self, parent_layout, title, settings_config)

    def create_setting_widget(self, parent, label, setting_key='', widget_type='entry',
                              options=None, default='', default_checkbutton=False, validation=None, tooltip=None,
                              width=None, height=None, command=None, hide=False):
        # Теперь используется guiTemplates
        return guiTemplates.create_setting_widget(self, parent, label, setting_key, widget_type,
                                                  options, default, default_checkbutton, validation, tooltip,
                                                  width, height, command, hide)

    def _save_setting(self, key, value):
        self.settings.set(key, value)
        self.settings.save_settings()
        self.all_settings_actions(key, value)

    def get_news_content(self):
        """Получает содержимое новостей с GitHub"""
        try:
            response = requests.get('https://raw.githubusercontent.com/VinerX/NeuroMita/main/NEWS.md', timeout=500)
            if response.status_code == 200:
                return response.text
            return _('Не удалось загрузить новости', 'Failed to load news')
        except Exception as e:
            logger.info(f"Ошибка при получении новостей: {e}")
            return _('Ошибка при загрузке новостей', 'Error loading news')

    def setup_news_control(self, parent_layout):
        news_config = [
            {'label': self.get_news_content(), 'type': 'text'},
        ]
        self.create_settings_section(parent_layout, _("Новости", "News"), news_config)

    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        self.stop_screen_capture_thread()
        self.stop_camera_capture_thread()
        self.delete_all_sound_files()
        self.stop_server()
        logger.info("Закрываемся")
        event.accept()

    def close_app(self):
        """Закрытие приложения корректным образом."""
        logger.info("Завершение программы...")
        self.close()

    @staticmethod
    def delete_all_sound_files():
        # Удаление всех wav и mp3 файлов
        for pattern in ["*.wav", "*.mp3"]:
            files = glob.glob(pattern)
            for file in files:
                try:
                    os.remove(file)
                    logger.info(f"Удален файл: {file}")
                except Exception as e:
                    logger.info(f"Ошибка при удалении файла {file}: {e}")

        # region LocalVoice Functions
    async def run_local_voiceover(self, text):
        """Асинхронный метод для вызова локальной озвучки."""
        result_path = None
        try:
            character = self.model.current_character if hasattr(self.model, "current_character") else None
            output_file = f"MitaVoices/output_{uuid.uuid4()}.wav"
            absolute_audio_path = os.path.abspath(output_file)
            os.makedirs(os.path.dirname(absolute_audio_path), exist_ok=True)

            result_path = await self.local_voice.voiceover(
                text=text,
                output_file=absolute_audio_path,
                character=character
            )

            if result_path:
                logger.info(f"Локальная озвучка сохранена в: {result_path}")
                if not self.ConnectedToGame and self.settings.get("VOICEOVER_LOCAL_CHAT"):
                    await AudioHandler.handle_voice_file(result_path, self.settings.get("LOCAL_VOICE_DELETE_AUDIO",
                                                                                        True) if os.environ.get(
                        "ENABLE_VOICE_DELETE_CHECKBOX", "0") == "1" else True)
                elif self.ConnectedToGame:
                    self.patch_to_sound_file = result_path
                    logger.info(f"Путь к файлу для игры: {self.patch_to_sound_file}")
                else:
                    logger.info("Озвучка в локальном чате отключена.")
            else:
                logger.error("Локальная озвучка не удалась, файл не создан.")

        except Exception as e:
            logger.error(f"Ошибка при выполнении локальной озвучки: {e}")

    def on_local_voice_selected(self, event=None):
        """Обработчик выбора локальной модели озвучки"""
        if not hasattr(self, 'local_voice_combobox'):
            return

        selected_model_name = self.local_voice_combobox.currentText()
        if not selected_model_name:
            self.update_local_model_status_indicator()
            return

        selected_model_id = None
        selected_model = None
        for model in LOCAL_VOICE_MODELS:
            if model["name"] == selected_model_name:
                selected_model = model
                selected_model_id = model["id"]
                break

        if not selected_model_id:
            QMessageBox.critical(self, _("Ошибка", "Error"), 
                _("Не удалось определить ID выбранной модели", "Could not determine ID of selected model"))
            self.update_local_model_status_indicator()
            return

        if selected_model_id in ["medium+", "medium+low"] and self.local_voice.first_compiled == False:
            reply = QMessageBox.question(self, _("Внимание", "Warning"),
                _("Невозможно перекомпилировать модель Fish Speech в Fish Speech+ - требуется перезапуск программы. \n\n Перезапустить?",
                  "Cannot recompile Fish Speech model to Fish Speech+ - program restart required. \n\n Restart?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                
            if reply != QMessageBox.StandardButton.Yes:
                if self.last_voice_model_selected:
                    self.local_voice_combobox.setCurrentText(self.last_voice_model_selected["name"])
                else:
                    self.local_voice_combobox.setCurrentText('')
                    self.settings.set("NM_CURRENT_VOICEOVER", None)
                    self.settings.save_settings()
                self.update_local_model_status_indicator()
                return
            else:
                import sys, subprocess
                python = sys.executable
                script = os.path.abspath(sys.argv[0])
                subprocess.Popen([python, script] + sys.argv[1:])
                self.close()
                return

        self.settings.set("NM_CURRENT_VOICEOVER", selected_model_id)
        self.settings.save_settings()
        self.current_local_voice_id = selected_model_id

        self.update_local_model_status_indicator()
        if not self.local_voice.is_model_initialized(selected_model_id):
            self.show_model_loading_window(selected_model)
        else:
            logger.info(f"Модель {selected_model_id} уже инициализирована.")
            self.last_voice_model_selected = selected_model
            self.local_voice.current_model = selected_model_id

    def show_model_loading_window(self, model):
        """Показывает окно загрузки модели с прогрессом"""
        model_id = model["id"]
        model_name = model["name"]

        downloader = ModelsDownloader(target_dir=".")
        logger.info(f"Проверка/загрузка файлов для '{model_name}'...")

        models_are_ready = downloader.download_models_if_needed(self)

        if not models_are_ready:
            logger.warning(f"Файлы моделей для '{model_name}' не готовы (загрузка не удалась или отменена).")
            QMessageBox.critical(self, _("Ошибка", "Error"),
                _("Не удалось подготовить файлы моделей. Инициализация отменена.",
                  "Failed to prepare model files. Initialization cancelled."))
            return

        logger.info(f"Модели для '{model_name}' готовы. Запуск инициализации...")

        # Создаем диалог загрузки
        self.loading_dialog = QDialog(self)
        self.loading_dialog.setWindowTitle(_("Загрузка модели", "Loading model") + f" {model_name}")
        self.loading_dialog.setFixedSize(400, 300)
        self.loading_dialog.setModal(True)
        
        layout = QVBoxLayout(self.loading_dialog)
        
        # Заголовок
        title_label = QLabel(_("Инициализация модели", "Initializing model") + f" {model_name}")
        title_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Подзаголовок
        wait_label = QLabel(_("Пожалуйста, подождите...", "Please wait..."))
        wait_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(wait_label)
        
        # Прогресс-бар
        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 0)  # Неопределенный прогресс
        layout.addWidget(self.loading_progress)
        
        # Статус
        self.loading_status_label = QLabel(_("Инициализация...", "Initializing..."))
        self.loading_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.loading_status_label)
        
        # Кнопка отмены
        cancel_button = QPushButton(_("Отменить", "Cancel"))
        cancel_button.clicked.connect(lambda: self.cancel_model_loading(self.loading_dialog))
        layout.addWidget(cancel_button, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.model_loading_cancelled = False
        
        # Запускаем инициализацию в отдельном потоке
        loading_thread = threading.Thread(
            target=self.init_model_thread,
            args=(model_id, self.loading_dialog, self.loading_status_label, self.loading_progress),
            daemon=True
        )
        loading_thread.start()
        
        self.loading_dialog.show()

    def cancel_model_loading(self, loading_window):
        """Отменяет загрузку модели"""
        logger.info("Загрузка модели отменена пользователем.")
        self.model_loading_cancelled = True
        if loading_window:
            loading_window.close()

        restored_model_id = None
        if self.last_voice_model_selected:
            if hasattr(self, 'local_voice_combobox'):
                self.local_voice_combobox.setCurrentText(self.last_voice_model_selected["name"])
            restored_model_id = self.last_voice_model_selected["id"]
            self.settings.set("NM_CURRENT_VOICEOVER", restored_model_id)
            self.current_local_voice_id = restored_model_id
        else:
            if hasattr(self, 'local_voice_combobox'):
                self.local_voice_combobox.setCurrentText('')
            self.settings.set("NM_CURRENT_VOICEOVER", None)
            self.current_local_voice_id = None

        self.settings.save_settings()
        self.update_local_model_status_indicator()

    def init_model_thread(self, model_id, loading_window, status_label, progress):
        """Поток инициализации модели"""
        try:
            QTimer.singleShot(0, lambda: status_label.setText(_("Загрузка настроек...", "Loading settings...")))

            success = False
            if not self.model_loading_cancelled:
                QTimer.singleShot(0, lambda: status_label.setText(_("Инициализация модели...", "Initializing model...")))
                success = self.local_voice.initialize_model(model_id, init=True)

            if success and not self.model_loading_cancelled:
                QTimer.singleShot(0, lambda: self.finish_model_loading(model_id, loading_window))
            elif not self.model_loading_cancelled:
                error_message = _("Не удалось инициализировать модель. Проверьте логи.",
                                  "Failed to initialize model. Check logs.")
                QTimer.singleShot(0, lambda: [
                    status_label.setText(_("Ошибка инициализации!", "Initialization Error!")),
                    progress.setRange(0, 1),
                    QMessageBox.critical(loading_window, _("Ошибка инициализации", "Initialization Error"), error_message),
                    self.cancel_model_loading(loading_window)
                ])
        except Exception as e:
            logger.error(f"Критическая ошибка в потоке инициализации модели {model_id}: {e}", exc_info=True)
            if not self.model_loading_cancelled:
                error_message = _("Критическая ошибка при инициализации модели: ",
                                  "Critical error during model initialization: ") + str(e)
                QTimer.singleShot(0, lambda: [
                    status_label.setText(_("Ошибка!", "Error!")),
                    progress.setRange(0, 1),
                    QMessageBox.critical(loading_window, _("Ошибка", "Error"), error_message),
                    self.cancel_model_loading(loading_window)
                ])

    def finish_model_loading(self, model_id, loading_window):
        """Завершает процесс загрузки модели"""
        logger.info(f"Модель {model_id} успешно инициализирована.")
        if loading_window:
            loading_window.close()

        self.local_voice.current_model = model_id

        self.last_voice_model_selected = None
        for model in LOCAL_VOICE_MODELS:
            if model["id"] == model_id:
                self.last_voice_model_selected = model
                break

        self.settings.set("NM_CURRENT_VOICEOVER", model_id)
        self.settings.save_settings()
        self.current_local_voice_id = model_id

        QMessageBox.information(self, _("Успешно", "Success"),
            _("Модель {} успешно инициализирована!", "Model {} initialized successfully!").format(model_id))
        
        self.update_local_voice_combobox()

    def initialize_last_local_model_on_startup(self):
        """Проверяет настройку и инициализирует последнюю локальную модель при запуске."""
        if self.settings.get("LOCAL_VOICE_LOAD_LAST", False):
            logger.info("Проверка автозагрузки последней локальной модели...")
            last_model_id = self.settings.get("NM_CURRENT_VOICEOVER", None)

            if last_model_id:
                logger.info(f"Найдена последняя модель для автозагрузки: {last_model_id}")
                model_to_load = None
                for model in LOCAL_VOICE_MODELS:
                    if model["id"] == last_model_id:
                        model_to_load = model
                        break

                if model_to_load:
                    if self.local_voice.is_model_installed(last_model_id):
                        if not self.local_voice.is_model_initialized(last_model_id):
                            logger.info(f"Модель {last_model_id} установлена, но не инициализирована. Запуск инициализации...")
                            self.show_model_loading_window(model_to_load)
                        else:
                            logger.info(f"Модель {last_model_id} уже инициализирована.")
                            self.last_voice_model_selected = model_to_load
                            self.update_local_voice_combobox()
                    else:
                        logger.warning(f"Модель {last_model_id} выбрана для автозагрузки, но не установлена.")
                else:
                    logger.warning(f"Не найдена информация для модели с ID: {last_model_id}")
            else:
                logger.info("Нет сохраненной последней локальной модели для автозагрузки.")
        else:
            logger.info("Автозагрузка локальной модели отключена.")

    def update_local_model_status_indicator(self):
        if hasattr(self, 'local_model_status_label') and self.local_model_status_label:
            show_combobox_indicator = False
            current_model_id_combo = self.settings.get("NM_CURRENT_VOICEOVER", None)

            if current_model_id_combo:
                model_installed_combo = self.local_voice.is_model_installed(current_model_id_combo)
                if model_installed_combo:
                    if not self.local_voice.is_model_initialized(current_model_id_combo):
                        show_combobox_indicator = True
                else:
                    show_combobox_indicator = True

            self.local_model_status_label.setVisible(show_combobox_indicator)

        show_section_warning = False
        if (hasattr(self, 'voiceover_section_warning_label') and 
                self.voiceover_section_warning_label and
                hasattr(self, 'voiceover_section') and 
                self.voiceover_section):

            voiceover_method = self.settings.get("VOICEOVER_METHOD", "TG")
            current_model_id_section = self.settings.get("NM_CURRENT_VOICEOVER", None)

            if voiceover_method == "Local" and current_model_id_section:
                model_installed_section = self.local_voice.is_model_installed(current_model_id_section)
                if model_installed_section:
                    if not self.local_voice.is_model_initialized(current_model_id_section):
                        show_section_warning = True
                else:
                    show_section_warning = True

            if hasattr(self.voiceover_section, 'warning_label'):
                self.voiceover_section.warning_label.setVisible(show_section_warning)

        # ------------------------------------------------------------------
    #  Отображение / скрытие настроек озвучки  (PyQt-реализация)
    # ------------------------------------------------------------------
    def switch_voiceover_settings(self, selected_method: str | None = None) -> None:
        """
        • Если 'Использовать озвучку' снято – остаётся видимым только главный чекбокс.<br>
        • Если включено – показывается строка выбора метода и блок,
          соответствующий выбранному методу ('TG' или 'Local').
        """

        # --- возможно метод передали напрямую из ComboBox'а ---
        if selected_method is not None:
            self._save_setting("VOICEOVER_METHOD", selected_method)

        use_voice        = bool(self.settings.get("SILERO_USE",  True))
        current_method   =      self.settings.get("VOICEOVER_METHOD", "TG")

        # 1. проверяем, что нужные объекты существуют
        if not hasattr(self, "voiceover_section"):
            logger.error("Отсутствует voiceover_section – переключать нечего.")
            return

        # 2. подготавливаем ссылки на строки / группы
        #    (метод-ряд = label + combobox)
        method_row_widget  = getattr(self, "method_frame", None)
        tg_group_widget    = getattr(self, "tg_settings_frame", None)
        local_group_widget = getattr(self, "local_settings_frame", None)

        # удобный помощник: прятать строку ЦЕЛИКОМ (контрол + контейнер)
        def set_row_visible(widget: QWidget | None, visible: bool):
            if widget is None:
                return
            widget.setVisible(visible)
            parent = widget.parentWidget()
            # если контрол упакован в отдельный QWidget-строку – прячем и её
            if parent is not None and parent != self.voiceover_section.content_frame:
                parent.setVisible(visible)

        # 3. сначала скрываем всё
        set_row_visible(method_row_widget,  False)
        if tg_group_widget:
            tg_group_widget.setVisible(False)
        if local_group_widget:
            local_group_widget.setVisible(False)

        # 4. если озвучка выключена – на этом всё
        if not use_voice:
            return

        # 5. показываем строку выбора метода
        set_row_visible(method_row_widget, True)

        # 6. показываем блок для выбранного метода
        if current_method == "TG":
            if tg_group_widget:
                tg_group_widget.setVisible(True)

        elif current_method == "Local":
            if local_group_widget:
                local_group_widget.setVisible(True)
                # актуализируем список моделей и статус индикаторов
                self.update_local_voice_combobox()
                self.update_local_model_status_indicator()

        # 7. сохраняем текущее состояние
        self.voiceover_method = current_method
        self.check_triton_dependencies()

    def update_local_voice_combobox(self):
        """Обновляет комбобокс списком установленных локальных моделей и статус инициализации."""
        if not hasattr(self, 'local_voice_combobox') or self.local_voice_combobox is None:
            logger.info(self.local_voice_combobox)
            logger.warning("update_local_voice_combobox: виджет local_voice_combobox не найден.")
            return

        installed_models_names = [model["name"] for model in LOCAL_VOICE_MODELS if
                                  self.local_voice.is_model_installed(model["id"])]
        logger.info(f'Доступные модели: {installed_models_names}')
        
        current_items = [self.local_voice_combobox.itemText(i) for i in range(self.local_voice_combobox.count())]
        
        if installed_models_names != current_items:
            self.local_voice_combobox.clear()
            self.local_voice_combobox.addItems(installed_models_names)
            logger.info(f"Обновлен список локальных моделей: {installed_models_names}")

        current_model_id = self.settings.get("NM_CURRENT_VOICEOVER", None)
        current_model_name = ""
        if current_model_id:
            for model in LOCAL_VOICE_MODELS:
                if model["id"] == current_model_id:
                    current_model_name = model["name"]
                    break

        if current_model_name and current_model_name in installed_models_names:
            if self.local_voice_combobox.currentText() != current_model_name:
                self.local_voice_combobox.setCurrentText(current_model_name)
        elif installed_models_names:
            if self.local_voice_combobox.currentText() != installed_models_names[0]:
                self.local_voice_combobox.setCurrentText(installed_models_names[0])
                for model in LOCAL_VOICE_MODELS:
                    if model["name"] == installed_models_names[0]:
                        if self.settings.get("NM_CURRENT_VOICEOVER") != model["id"]:
                            self.settings.set("NM_CURRENT_VOICEOVER", model["id"])
                            self.settings.save_settings()
                            self.current_local_voice_id = model["id"]
                        break
        else:
            if self.local_voice_combobox.currentText() != '':
                self.local_voice_combobox.setCurrentText('')
            if self.settings.get("NM_CURRENT_VOICEOVER") is not None:
                self.settings.set("NM_CURRENT_VOICEOVER", None)
                self.settings.save_settings()
                self.current_local_voice_id = None

        self.update_local_model_status_indicator()
        self.check_triton_dependencies()

    def check_triton_dependencies(self):
        """Проверяет зависимости Triton и отображает предупреждение, если нужно."""
        if hasattr(self, 'triton_warning_label') and self.triton_warning_label:
            self.triton_warning_label.deleteLater()
            delattr(self, 'triton_warning_label')

        if self.settings.get("VOICEOVER_METHOD") != "Local":
            return
        if not hasattr(self, 'local_settings_frame') or not self.local_settings_frame:
            return

        triton_found = False
        try:
            import triton
            triton_found = True
            logger.debug("Зависимости Triton найдены (через import triton).")
        except ImportError as e:
            logger.warning(f"Зависимости Triton не найдены! Игнорируйте это предупреждение, если не используете \"Fish Speech+ / + RVC\" озвучку. Exception импорта: {e}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при проверке Triton. Игнорируйте это предупреждение, если не используете \"Fish Speech+ / + RVC\" озвучку. Exception: {e}", exc_info=True)

    def open_local_model_installation_window(self):
        """Открывает новое окно для управления установкой локальных моделей."""
        try:
            from voice_model_settings import VoiceModelSettingsWindow
            import os

            config_dir = "Settings"
            os.makedirs(config_dir, exist_ok=True)

            def on_save_callback(settings_data):
                """Обработчик события сохранения настроек из окна установки."""
                installed_models_ids = settings_data.get("installed_models", [])
                logger.info(f"Сохранены установленные модели (из окна установки): {installed_models_ids}")

                self.refresh_local_voice_modules()
                self.update_local_voice_combobox()

                current_model_id = self.settings.get("NM_CURRENT_VOICEOVER", None)
                if current_model_id and current_model_id not in installed_models_ids:
                    logger.warning(f"Текущая модель {current_model_id} была удалена. Сбрасываем выбор.")
                    new_model_id = installed_models_ids[0] if installed_models_ids else None
                    self.settings.set("NM_CURRENT_VOICEOVER", new_model_id)
                    self.settings.save_settings()
                    self.current_local_voice_id = new_model_id
                    self.update_local_voice_combobox()

            # Создаем отдельное окно QDialog
            from PyQt6.QtWidgets import QDialog
            install_dialog = QDialog(self)
            install_dialog.setWindowTitle(_("Управление локальными моделями", "Manage Local Models"))
            install_dialog.setModal(False)  # Делаем немодальным
            install_dialog.resize(875, 800)
            
            # Создаем layout для диалога
            dialog_layout = QVBoxLayout(install_dialog)
            dialog_layout.setContentsMargins(0, 0, 0, 0)
            
            # Создаем виджет настроек моделей
            settings_widget = VoiceModelSettingsWindow(
                master=None,  # Не передаем родителя
                config_dir=config_dir,
                on_save_callback=on_save_callback,
                local_voice=self.local_voice,
                check_installed_func=self.check_module_installed,
            )
            
            # Добавляем виджет в диалог
            dialog_layout.addWidget(settings_widget)
            
            # Показываем диалог
            install_dialog.show()
            
        except ImportError:
            logger.error("Не найден модуль voice_model_settings.py. Установка моделей недоступна.")
            QMessageBox.critical(self, _("Ошибка", "Error"),
                _("Не найден файл voice_model_settings.py", "voice_model_settings.py not found."))
        except Exception as e:
            logger.error(f"Ошибка при открытии окна установки моделей: {e}", exc_info=True)
            QMessageBox.critical(self, _("Ошибка", "Error"), 
                _("Не удалось открыть окно установки моделей.", "Failed to open model installation window."))

    def refresh_local_voice_modules(self):
        """Обновляет импорты модулей в LocalVoice без перезапуска программы."""
        import importlib
        import sys
        logger.info("Попытка обновления модулей локальной озвучки...")

        modules_to_check = {
            "tts_with_rvc": "TTS_RVC",
            "fish_speech_lib.inference": "FishSpeech",
            "triton": None
        }
        
        lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Lib")
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)

        for module_name, class_name in modules_to_check.items():
            try:
                if module_name in sys.modules:
                    logger.debug(f"Перезагрузка модуля: {module_name}")
                    importlib.reload(sys.modules[module_name])
                else:
                    logger.debug(f"Импорт модуля: {module_name}")
                    imported_module = importlib.import_module(module_name)

                if class_name:
                    actual_class = getattr(sys.modules[module_name], class_name)
                    if module_name == "tts_with_rvc":
                        self.local_voice.tts_rvc_module = actual_class
                    elif module_name == "fish_speech_lib.inference":
                        self.local_voice.fish_speech_module = actual_class

                logger.info(f"Модуль {module_name} успешно обработан.")
            except ImportError:
                logger.warning(f"Модуль {module_name} не найден или не установлен.")
                if module_name == "tts_with_rvc":
                    self.local_voice.tts_rvc_module = None
                elif module_name == "fish_speech_lib.inference":
                    self.local_voice.fish_speech_module = None
            except Exception as e:
                logger.error(f"Ошибка при обработке модуля {module_name}: {e}", exc_info=True)

        self.check_triton_dependencies()

    def check_module_installed(self, module_name):
        """Проверяет, установлен ли модуль, фокусируясь на результате find_spec."""
        logger.info(f"Проверка установки модуля: {module_name}")
        spec = None
        try:
            spec = importlib.util.find_spec(module_name)

            if spec is None:
                logger.info(f"Модуль {module_name} НЕ найден через find_spec.")
                return False
            else:
                if spec.loader is not None:
                    try:
                        module = importlib.import_module(module_name)
                        if hasattr(module, '__spec__') and module.__spec__ is not None:
                            logger.info(f"Модуль {module_name} найден (find_spec + loader + import).")
                            return True
                        else:
                            logger.warning(f"Модуль {module_name} импортирован, но __spec__ is None или отсутствует. Считаем не установленным корректно.")
                            if module_name in sys.modules:
                                try:
                                    del sys.modules[module_name]
                                except KeyError:
                                    pass
                            return False
                    except ImportError as ie:
                        logger.warning(f"Модуль {module_name} найден find_spec, но не импортируется: {ie}. Считаем не установленным.")
                        return False
                    except ValueError as ve:
                        logger.warning(f"Модуль {module_name} найден find_spec, но ошибка ValueError при импорте: {ve}. Считаем не установленным.")
                        return False
                    except Exception as e_import:
                        logger.error(f"Неожиданная ошибка при импорте {module_name} после find_spec: {e_import}")
                        return False
                else:
                    logger.warning(f"Модуль {module_name} найден через find_spec, но loader is None. Считаем не установленным корректно.")
                    return False

        except ValueError as e:
            logger.warning(f"Ошибка ValueError при find_spec для {module_name}: {e}. Считаем не установленным корректно.")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при вызове find_spec для {module_name}: {e}")
            return False

    def check_available_vram(self):
        """Проверка доступной видеопамяти (заглушка)."""
        logger.warning("Проверка VRAM не реализована, возвращается фиктивное значение.")
        try:
            return 100
        except Exception as e:
            logger.error(f"Ошибка при попытке проверки VRAM: {e}")
            return 4
    # endregion

    # region ffmpeg installations tools
    def _show_ffmpeg_installing_popup(self):
        """Показывает неблокирующее окно 'Установка FFmpeg...'."""
        if hasattr(self, 'ffmpeg_install_popup') and self.ffmpeg_install_popup:
            return

        self.ffmpeg_install_popup = QDialog(self)
        self.ffmpeg_install_popup.setWindowTitle("FFmpeg")
        self.ffmpeg_install_popup.setFixedSize(300, 100)
        
        layout = QVBoxLayout(self.ffmpeg_install_popup)
        label = QLabel("Идет установка FFmpeg...\nПожалуйста, подождите.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        self.ffmpeg_install_popup.show()

    def _close_ffmpeg_installing_popup(self):
        """Закрывает окно 'Установка FFmpeg...'."""
        if hasattr(self, 'ffmpeg_install_popup') and self.ffmpeg_install_popup:
            self.ffmpeg_install_popup.close()
            self.ffmpeg_install_popup = None

    def _show_ffmpeg_error_popup(self):
        """Показывает МОДАЛЬНОЕ окно ошибки установки FFmpeg."""
        error_dialog = QDialog(self)
        error_dialog.setWindowTitle("Ошибка установки FFmpeg")
        error_dialog.setModal(True)
        
        layout = QVBoxLayout(error_dialog)
        
        message = (
            "Не удалось автоматически установить FFmpeg.\n\n"
            "Он необходим для некоторых функций программы (например, обработки аудио).\n\n"
            "Пожалуйста, скачайте FFmpeg вручную с официального сайта:\n"
            f"{"https://ffmpeg.org/download.html"}\n\n"
            f"Распакуйте архив и поместите файл 'ffmpeg.exe' в папку программы:\n"
            f"{Path('.').resolve()}"
        )
        
        label = QLabel(message)
        layout.addWidget(label)
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(error_dialog.accept)
        layout.addWidget(ok_button, alignment=Qt.AlignmentFlag.AlignCenter)
        
        error_dialog.exec()

    def _ffmpeg_install_thread_target(self):
        """Функция, выполняемая в отдельном потоке для установки FFmpeg."""
        QTimer.singleShot(0, self._show_ffmpeg_installing_popup)

        logger.info("Starting FFmpeg installation attempt...")
        success = install_ffmpeg()
        logger.info(f"FFmpeg installation attempt finished. Success: {success}")

        QTimer.singleShot(0, self._close_ffmpeg_installing_popup)

        if not success:
            QTimer.singleShot(0, self._show_ffmpeg_error_popup)

    def check_and_install_ffmpeg(self):
        """Проверяет наличие ffmpeg.exe и запускает установку в потоке, если его нет."""
        ffmpeg_path = Path(".") / "ffmpeg.exe"
        logger.info(f"Checking for FFmpeg at: {ffmpeg_path}")

        if not ffmpeg_path.exists():
            logger.info("FFmpeg not found. Starting installation process in a separate thread.")
            install_thread = threading.Thread(target=self._ffmpeg_install_thread_target, daemon=True)
            install_thread.start()
        else:
            logger.info("FFmpeg found. No installation needed.")

    def on_voice_language_selected(self, event=None):
        """Обработчик выбора языка озвучки."""
        if not hasattr(self, 'voice_language_var'):
            logger.warning("Переменная voice_language_var не найдена.")
            return

        selected_language = self.voice_language_var.currentText() if hasattr(self.voice_language_var, 'currentText') else self.voice_language_var
        logger.info(f"Выбран язык озвучки: {selected_language}")

        self._save_setting("VOICE_LANGUAGE", selected_language)

        if hasattr(self.local_voice, 'change_voice_language'):
            try:
                self.local_voice.change_voice_language(selected_language)
                logger.info(f"Язык в LocalVoice успешно изменен на {selected_language}.")
                self.update_local_model_status_indicator()
            except Exception as e:
                logger.error(f"Ошибка при вызове local_voice.change_voice_language: {e}")
        else:
            logger.warning("Метод 'change_voice_language' отсутствует в объекте local_voice.")
    # endregion

    # Методы вне регионов
    def paste_from_clipboard(self, event=None):
        try:
            clipboard_content = QApplication.clipboard().text()
            self.user_entry.insertPlainText(clipboard_content)
        except Exception:
            pass

    def copy_to_clipboard(self, event=None):
        try:
            if self.user_entry.textCursor().hasSelection():
                selected_text = self.user_entry.textCursor().selectedText()
                QApplication.clipboard().setText(selected_text)
        except Exception:
            pass

    def insert_dialog(self, input_text="", response="", system_text=""):
        MitaName = self.model.current_character.name
        cursor = self.chat_window.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        if input_text != "":
            self._insert_formatted_text(cursor, "Вы: ", QColor("gold"), bold=True)
            cursor.insertText(f"{input_text}\n")
        if system_text != "":
            self._insert_formatted_text(cursor, f"System to {MitaName}: ", QColor("white"), bold=True)
            cursor.insertText(f"{system_text}\n\n")
        if response != "":
            self._insert_formatted_text(cursor, f"{MitaName}: ", QColor("hot pink"), bold=True)
            cursor.insertText(f"{response}\n\n")

    def on_chat_scroll(self, event):
        """Обработчик события прокрутки чата."""
        if self.loading_more_history:
            return

        scrollbar = self.chat_window.verticalScrollBar()
        if scrollbar.value() == scrollbar.minimum():
            self.load_more_history()

    def trim_chat_display(self):
        """Удаляет сообщения из начала чата, оставляя только видимые + запас."""
        # Для PyQt6 эта функция может быть реализована иначе или не нужна
        pass

    def keypress(self, e):
        """Обработчик горячих клавиш"""
        # В PyQt6 обработка горячих клавиш обычно делается через QShortcut
        # Этот метод может быть не нужен
        pass

    def cmd_copy(self, widget):
        self.copy_to_clipboard()

    def cmd_cut(self, widget):
        # Для QTextEdit
        self.user_entry.cut()

    def cmd_paste(self, widget):
        self.paste_from_clipboard()

    def run(self):
        """Метод для совместимости с tkinter версией"""
        # В PyQt6 этот метод не нужен, так как запуск происходит через app.exec()
        pass


# Точка входа
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChatGUI()
    window.show()
    sys.exit(app.exec())