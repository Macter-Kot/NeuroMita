import io
import uuid
import sys
import win32gui
import asyncio
import threading
import re
import subprocess
import gettext
from pathlib import Path
import os
import base64
import json
import glob
import time
import requests
import importlib

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QPushButton, QLabel, QScrollArea, QMessageBox,
                             QCheckBox, QComboBox, QLineEdit, QDialog, QProgressBar, QFrame,
                             QSizePolicy)
from PyQt6.QtCore import Qt, QTimer, QObject, QEvent, pyqtSignal
from PyQt6.QtGui import (QIcon, QImage, QTextCursor, QTextImageFormat, QTextCharFormat,
                       QColor, QFont, QGuiApplication, QValidator, QKeySequence)

from pyqt_styles.styles import get_stylesheet

import guiTemplates
from AudioHandler import AudioHandler
from Logger import logger
from SettingsManager import SettingsManager
from chat_model import ChatModel
from server import ChatServer
from Silero import TelegramBotHandler
import sounddevice as sd
from ui.settings.voiceover_settings import LOCAL_VOICE_MODELS
from utils.ffmpeg_installer import install_ffmpeg
from utils.ModelsDownloader import ModelsDownloader
from utils import _, SH, process_text_to_voice
from ScreenCapture import ScreenCapture
from LocalVoice import LocalVoice
from SpeechRecognition import SpeechRecognition
from utils.PipInstaller import PipInstaller

from ui import status_indicators
from ui.settings import (
    api_settings, character_settings, chat_settings, common_settings,
    g4f_settings, gamemaster_settings, general_model_settings,
    language_settings, microphone_settings, screen_analysis_settings,
    token_settings, voiceover_settings, command_replacer_settings, history_compressor,
    prompt_catalogue_settings
)

class LoadingDialog(QDialog):
    def __init__(self, message, parent=None, indeterminate=True):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(" ")
        self.setObjectName("LoadingDialog")
        self.setFixedSize(350, 120)
        
        layout = QVBoxLayout(self)
        
        self.message_label = QLabel(message)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.message_label)
        
        self.progress_bar = QProgressBar()
        if indeterminate:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.cancel_button = QPushButton(_("Отменить", "Cancel"))
        layout.addWidget(self.cancel_button)
        layout.setAlignment(self.cancel_button, Qt.AlignmentFlag.AlignCenter)

    def update_progress(self, value):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(value)

    def set_message(self, message):
        self.message_label.setText(message)

class CollapsibleSection(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.is_collapsed = True
        self.init_ui(title)

    def init_ui(self, title):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.header = QWidget()
        self.header.setObjectName("CollapsibleHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(5, 3, 5, 3)

        self.arrow_label = QLabel("▶")
        self.arrow_label.setObjectName("CollapsibleArrow")
        self.arrow_label.setFixedWidth(15)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("CollapsibleTitle")
        
        self.warning_label = QLabel("⚠️")
        self.warning_label.setObjectName("WarningIcon")
        self.warning_label.setVisible(False)
        self.warning_label.setToolTip(_("Модель не инициализирована или не установлена.", "Model not initialized or not installed."))

        header_layout.addWidget(self.arrow_label)
        header_layout.addWidget(self.warning_label)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.content_frame = QWidget()
        self.content_frame.setObjectName("CollapsibleContent")
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(10, 5, 10, 5)
        self.content_frame.setVisible(False)

        main_layout.addWidget(self.header)
        main_layout.addWidget(self.content_frame)

        self.header.mousePressEvent = self.toggle

    def toggle(self, event=None):
        self.is_collapsed = not self.is_collapsed
        self.arrow_label.setText("▶" if self.is_collapsed else "▼")
        self.content_frame.setVisible(not self.is_collapsed)

    def collapse(self):
        if not self.is_collapsed:
            self.toggle()

    def expand(self):
        if self.is_collapsed:
            self.toggle()
            
    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

class ChatGUI(QMainWindow):
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
            self.settings = SettingsManager(self.config_path)
            self.load_api_settings(False)
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

        self.model = ChatModel(self, self.api_key, self.api_key_res, self.api_url, self.api_model, self.makeRequest, self.pip_installer)
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

        self.lazy_load_batch_size = 50
        self.total_messages_in_history = 0
        self.loaded_messages_offset = 0
        self.loading_more_history = False

        self.setWindowIcon(QIcon('icon.png'))
        self.setWindowTitle(_("Чат с NeuroMita", "NeuroMita Chat"))
        
        self.ffmpeg_install_popup = None
        QTimer.singleShot(100, self.check_and_install_ffmpeg)

        self.delete_all_sound_files()

        self.silero_connected = False
        self.game_connected = False
        self.mic_recognition_active = False
        self.screen_capture_active = False
        self.camera_capture_active = False
        
        self._images_in_chat = []

        self.setup_ui()
        self.load_chat_history()
        
        QApplication.instance().installEventFilter(self)

        try:
            microphone_settings.load_mic_settings(self)
        except Exception as e:
            logger.info("Не удалось удачно получить настройки микрофона", e)

        self.loop_ready_event = threading.Event()
        self.loop = None
        self.asyncio_thread = threading.Thread(target=self.start_asyncio_loop, daemon=True)
        self.asyncio_thread.start()
        self.start_silero_async()

        initial_recognizer_type = self.settings.get("RECOGNIZER_TYPE", "google")
        initial_vosk_model = self.settings.get("VOSK_MODEL", "vosk-model-ru-0.10")
        SpeechRecognition.set_recognizer_type(initial_recognizer_type)
        SpeechRecognition.vosk_model = initial_vosk_model

        self.check_talk_timer = QTimer(self)
        self.check_talk_timer.timeout.connect(self.check_text_to_talk_or_send)
        self.check_talk_timer.start(100)

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

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.matches(QKeySequence.StandardKey.Copy):
                if isinstance(source, (QLineEdit, QTextEdit)) and source.hasFocus():
                    source.copy()
                    return True
            if event.matches(QKeySequence.StandardKey.Paste):
                if isinstance(source, (QLineEdit, QTextEdit)) and source.hasFocus():
                    source.paste()
                    return True
            elif event.matches(QKeySequence.StandardKey.Cut):
                if isinstance(source, (QLineEdit, QTextEdit)) and source.hasFocus():
                    source.cut()
                    return True
        return super().eventFilter(source, event)

    def start_asyncio_loop(self):
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
        logger.info("Ожидание готовности цикла событий...")
        self.loop_ready_event.wait()
        if self.loop and self.loop.is_running():
            logger.info("Запускаем Silero через цикл событий.")
            asyncio.run_coroutine_threadsafe(self.startSilero(), self.loop)
        else:
            logger.info("Ошибка: Цикл событий asyncio не запущен.")

    async def startSilero(self):
        logger.info("Telegram Bot запускается!")
        try:
            if not self.api_id or not self.api_hash or not self.phone:
                logger.info("Ошибка: отсутствуют необходимые данные для Telegram бота")
                self.silero_connected = False
                QTimer.singleShot(0, self.update_status_colors)
                return

            logger.info(f"Передаю в тг {SH(self.api_id)},{SH(self.api_hash)},{SH(self.phone)} (Должно быть не пусто)")
            self.bot_handler = TelegramBotHandler(self, self.api_id, self.api_hash, self.phone, self.settings.get("AUDIO_BOT", "@silero_voice_bot"))

            try:
                await self.bot_handler.start()
                self.bot_handler_ready = True
                if hasattr(self.bot_handler, 'client') and self.bot_handler.client.is_connected():
                    self.silero_connected = True
                    logger.info("ТГ успешно подключен")
                else:
                    self.silero_connected = False
                    logger.info("ТГ не подключен")
            except Exception as e:
                logger.info(f"Ошибка при запуске Telegram бота: {e}")
                self.bot_handler_ready = False
                self.silero_connected = False
        except Exception as e:
            logger.info(f"Критическая ошибка при инициализации Telegram Bot: {e}")
            self.silero_connected = False
            self.bot_handler_ready = False
        QTimer.singleShot(0, self.update_status_colors)

    def run_in_thread(self, response):
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
        logger.info("Попытка получить фразу")
        self.waiting_answer = True
        await self.bot_handler.send_and_receive(response, speaker_command, id)
        self.waiting_answer = False
        logger.info("Завершение получения фразы")

    def check_text_to_talk_or_send(self):
        if bool(self.settings.get("SILERO_USE")) and self.textToTalk:
            self.voice_text()

        if self.image_request_timer_running:
            self.send_interval_image()

        if bool(self.settings.get("MIC_INSTANT_SENT")):
            if not self.waiting_answer:
                text_from_recognition = SpeechRecognition.receive_text()
                if text_from_recognition:
                    current_text = self.user_entry.toPlainText()
                    self.user_entry.setPlainText(current_text + text_from_recognition)
                    self.user_input = self.user_entry.toPlainText().strip()
                    if not self.dialog_active:
                        self.send_instantly()
        elif bool(self.settings.get("MIC_ACTIVE")) and self.user_entry:
            text_from_recognition = SpeechRecognition.receive_text()
            if text_from_recognition:
                self.user_entry.moveCursor(QTextCursor.MoveOperation.End)
                self.user_entry.insertPlainText(text_from_recognition)
                self.user_input = self.user_entry.toPlainText().strip()

    def send_interval_image(self):
        current_time = time.time()
        interval = float(self.settings.get("IMAGE_REQUEST_INTERVAL", 20.0))
        delta = current_time - self.last_image_request_time
        if delta >= interval:
            image_data = []
            if self.settings.get("ENABLE_SCREEN_ANALYSIS", False):
                logger.info(f"Отправка периодического запроса с изображением ({delta:.2f}/{interval:.2f} сек).")
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
        self.send_message()

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
                QTimer.singleShot(0, self.load_chat_history)

    def setup_ui(self):
        self.setStyleSheet(get_stylesheet())
        self.resize(1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        left_widget = self.setup_left_frame()
        right_widget = self.setup_right_frame()

        main_layout.addWidget(left_widget, stretch=1)
        main_layout.addWidget(right_widget, stretch=1)
       
    def setup_left_frame(self):
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)

        button_frame_above_chat = QWidget()
        button_layout = QHBoxLayout(button_frame_above_chat)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.clear_chat_button = QPushButton(_("Очистить", "Clear"))
        self.clear_chat_button.setObjectName("ClearButton")
        self.clear_chat_button.clicked.connect(self.clear_chat_display)
        button_layout.addWidget(self.clear_chat_button)

        self.load_history_button = QPushButton(_("Взять из истории", "Load from history"))
        self.load_history_button.setObjectName("LoadHistoryButton")
        self.load_history_button.clicked.connect(self.load_chat_history)
        button_layout.addWidget(self.load_history_button)

        self.chat_window = QTextEdit()
        self.chat_window.setReadOnly(True)
        self.chat_window.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        initial_font_size = int(self.settings.get("CHAT_FONT_SIZE", 12))
        self.setup_tags_configurations(initial_font_size)
        
        input_frame = QWidget()
        input_frame.setStyleSheet("background-color: #252525; border-radius: 4px;")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(5, 5, 5, 5)
        input_layout.setSpacing(5)
        
        self.token_count_label = QLabel(_("Токены: 0/0 | Стоимость: 0.00 ₽", "Tokens: 0/0 | Cost: 0.00 ₽"))
        self.token_count_label.setObjectName("TokenCountLabel")

        self.user_entry = QTextEdit()
        self.user_entry.setFixedHeight(70)
        self.user_entry.installEventFilter(self)
        
        class UserEntryEventFilter(QObject):
            def __init__(self, parent_gui):
                super().__init__()
                self.parent_gui = parent_gui
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.KeyPress and obj is self.parent_gui.user_entry:
                    if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                        self.parent_gui.on_enter_pressed()
                        return True
                return super().eventFilter(obj, event)
        self.user_entry_filter = UserEntryEventFilter(self)
        self.user_entry.installEventFilter(self.user_entry_filter)
        
        send_button_layout = QHBoxLayout()
        send_button_layout.addStretch()
        self.send_button = QPushButton(_("Отправить", "Send"))
        self.send_button.setObjectName("SendButton")
        self.send_button.clicked.connect(self.send_message)
        send_button_layout.addWidget(self.send_button)

        input_layout.addWidget(self.token_count_label)
        input_layout.addWidget(self.user_entry)
        input_layout.addLayout(send_button_layout)
        
        left_layout.addWidget(button_frame_above_chat)
        # ИСПРАВЛЕНИЕ: Добавляем чат с коэффициентом растяжения 1
        left_layout.addWidget(self.chat_window, 1) 
        # Добавляем панель ввода без растяжения (коэффициент 0 по умолчанию)
        left_layout.addWidget(input_frame)
        
        return left_widget

    def setup_tags_configurations(self, initial_font_size):
        self.formats = {}
        
        default_format = QTextCharFormat()
        default_font = QFont("Arial", initial_font_size)
        default_format.setFont(default_font)
        default_format.setForeground(QColor("#e0e0e0"))
        self.formats['default'] = default_format
        
        mita_format = QTextCharFormat()
        mita_font = QFont("Arial", initial_font_size, QFont.Weight.Bold)
        mita_format.setFont(mita_font)
        mita_format.setForeground(QColor("#ff8ddb")) # Pinkish color from screenshot
        self.formats['Mita'] = mita_format

        tag_green_format = QTextCharFormat()
        tag_green_font = QFont("Arial", initial_font_size)
        tag_green_format.setFont(tag_green_font)
        tag_green_format.setForeground(QColor("#77ff77")) # Softer green
        self.formats['tag_green'] = tag_green_format

        player_format = QTextCharFormat()
        player_font = QFont("Arial", initial_font_size, QFont.Weight.Bold)
        player_format.setFont(player_font)
        player_format.setForeground(QColor("#87cefa")) # Light blue for player
        self.formats['Player'] = player_format

        system_format = QTextCharFormat()
        system_font = QFont("Arial", initial_font_size, QFont.Weight.Bold)
        system_format.setFont(system_font)
        system_format.setForeground(QColor("#f0f0f0"))
        self.formats['System'] = system_format
        
        bold_format = QTextCharFormat()
        bold_font = QFont("Arial", initial_font_size, QFont.Weight.Bold)
        bold_format.setFont(bold_font)
        self.formats['bold'] = bold_format

        italic_format = QTextCharFormat()
        italic_font = QFont("Arial", initial_font_size)
        italic_font.setItalic(True)
        italic_format.setFont(italic_font)
        self.formats['italic'] = italic_format

        timestamp_format = QTextCharFormat()
        timestamp_font = QFont("Arial", initial_font_size - 2)
        timestamp_font.setItalic(True)
        timestamp_format.setFont(timestamp_font)
        timestamp_format.setForeground(QColor("#888888"))
        self.formats['timestamp'] = timestamp_format
        
        # Format for memory/hint tags like in the screenshot
        memory_hint_format = QTextCharFormat()
        memory_hint_font = QFont("Arial", initial_font_size)
        memory_hint_format.setFont(memory_hint_font)
        memory_hint_format.setForeground(QColor("#50c878")) # Emerald green
        self.formats['memory_hint'] = memory_hint_format

    def setup_right_frame(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        self.settings_widget = QWidget()
        self.settings_layout = QVBoxLayout(self.settings_widget)
        self.settings_layout.setContentsMargins(5, 5, 5, 5)
        self.settings_layout.setSpacing(5)
        self.settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll_area.setWidget(self.settings_widget)
        
        status_indicators.create_status_indicators(self, self.settings_layout)
        language_settings.create_language_section(self, self.settings_layout)
        api_settings.setup_api_controls(self, self.settings_layout)
        g4f_settings.setup_g4f_controls(self, self.settings_layout)
        general_model_settings.setup_general_settings_control(self, self.settings_layout)
        voiceover_settings.setup_voiceover_controls(self, self.settings_layout)
        microphone_settings.setup_microphone_controls(self, self.settings_layout)
        character_settings.setup_mita_controls(self, self.settings_layout)
        prompt_catalogue_settings.setup_prompt_catalogue_controls(self, self.settings_layout)
        
        # Эти функции теперь используют централизованные шаблоны
        self.setup_debug_controls(self.settings_layout)
        self.setup_common_controls(self.settings_layout)
        gamemaster_settings.setup_game_master_controls(self, self.settings_layout)
        history_compressor.setup_history_compressor_controls(self, self.settings_layout)
        chat_settings.setup_chat_settings_controls(self, self.settings_layout)
        screen_analysis_settings.setup_screen_analysis_controls(self, self.settings_layout)
        token_settings.setup_token_settings_controls(self, self.settings_layout)
        command_replacer_settings.setup_command_replacer_controls(self, self.settings_layout)
        self.setup_news_control(self.settings_layout)

        for i in range(self.settings_layout.count()):
            widget = self.settings_layout.itemAt(i).widget()
            if isinstance(widget, CollapsibleSection):
                widget.collapse()

        return scroll_area

    def insert_message(self, role, content, insert_at_start=False, message_time=""):
        logger.info(f"insert_message вызван. Роль: {role}, Содержимое: {str(content)[:50]}...")
        
        self.chat_window.setReadOnly(False)
        cursor = self.chat_window.textCursor()
        
        if insert_at_start:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)

        show_timestamps = self.settings.get("SHOW_CHAT_TIMESTAMPS", False)
        if show_timestamps:
            timestamp_str = f"[{message_time}] " if message_time else time.strftime("[%H:%M:%S] ")
            cursor.insertText(timestamp_str, self.formats['timestamp'])

        if role == "user":
            cursor.insertText(_("Вы: ", "You: "), self.formats['Player'])
        elif role == "assistant":
            cursor.insertText(f"{self.model.current_character.name}: ", self.formats['Mita'])
        elif role == "System":
            cursor.insertText(f"System to {self.model.current_character.name}: ", self.formats['System'])

        processed_content_parts = []
        has_image_content = False

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        processed_content_parts.append({"type": "text", "content": item.get("text", "")})
                    elif item.get("type") == "image_url":
                        has_image_content = True
                        self.process_image_for_chat(cursor, item)

            if has_image_content and not any(part.get("content", "").strip() for part in processed_content_parts if part["type"] == "text"):
                processed_content_parts.insert(0, {"type": "text", "content": _("<Изображение экрана>", "<Screen Image>") + "\n"})

        elif isinstance(content, str):
            processed_content_parts.append({"type": "text", "content": content})
        
        self.process_and_insert_text_parts(cursor, processed_content_parts)

        if role == "user":
            cursor.insertText("\n")
        elif role in {"assistant", "system"}:
            cursor.insertText("\n\n")

        self.chat_window.setReadOnly(True)
        if not insert_at_start:
            self.chat_window.ensureCursorVisible()

    def append_message(self, text):
        self.chat_window.setReadOnly(False)
        cursor = self.chat_window.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter, QTextCursor.MoveMode.MoveAnchor, 2)
        cursor.insertText(text)
        self.chat_window.setReadOnly(True)
        self.chat_window.ensureCursorVisible()

    def process_image_for_chat(self, cursor, item):
        image_data_base64 = item.get("image_url", {}).get("url", "")
        if image_data_base64.startswith("data:image/jpeg;base64,"):
            image_data_base64 = image_data_base64.replace("data:image/jpeg;base64,", "")
        elif image_data_base64.startswith("data:image/png;base64,"):
            image_data_base64 = image_data_base64.replace("data:image/png;base64,", "")
        
        try:
            image_bytes = base64.b64decode(image_data_base64)
            q_image = QImage.fromData(image_bytes)
            
            max_width = 400
            max_height = 300
            if q_image.width() > max_width or q_image.height() > max_height:
                q_image = q_image.scaled(max_width, max_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

            image_name = f"temp_image_{uuid.uuid4()}.png"
            q_image.save(image_name)
            
            image_format = QTextImageFormat()
            image_format.setName(image_name)
            image_format.setWidth(q_image.width())
            image_format.setHeight(q_image.height())
            
            cursor.insertImage(image_format)
            self._images_in_chat.append(image_name)
            return True
        except Exception as e:
            logger.error(f"Ошибка при декодировании или обработке изображения: {e}")
            cursor.insertText(_("<Ошибка загрузки изображения>", "<Image load error>"), self.formats['default'])
            return False

    def process_and_insert_text_parts(self, cursor, content_parts):
        hide_tags = self.settings.get("HIDE_CHAT_TAGS", False)

        for part in content_parts:
            if part["type"] == "text":
                text_content = part["content"]
                if hide_tags:
                    text_content = process_text_to_voice(text_content)
                    cursor.insertText(text_content, self.formats['default'])
                    continue

                # Improved regex to capture memory/hint tags
                pattern = r'(<memory>.*?</memory>|<hint>.*?</hint>|<([^>]+)>)(.*?)(</\2>)|(<([^>]+)>)|(\[b\](.*?)\[\/b\])|(\[i\](.*?)\[\/i\])|(\[color=(.*?)\](.*?)\[\/color\])'
                
                last_end = 0
                for match in re.finditer(pattern, text_content, re.DOTALL):
                    start, end = match.span()
                    
                    # Insert text before the current match
                    if start > last_end:
                        cursor.insertText(text_content[last_end:start], self.formats['default'])
                    
                    # Process the matched tag
                    full_tag_match = match.group(0)
                    if full_tag_match.startswith(('<memory>', '<hint>')):
                        cursor.insertText(full_tag_match, self.formats['memory_hint'])
                    elif match.group(1): # Paired XML-like tags <p>...</p>
                        cursor.insertText(match.group(2), self.formats['tag_green']) # Opening tag
                        cursor.insertText(match.group(3), self.formats['default']) # Content
                        cursor.insertText(match.group(4), self.formats['tag_green']) # Closing tag
                    elif match.group(5): # Single XML-like tag <e>
                        cursor.insertText(match.group(5), self.formats['tag_green'])
                    elif match.group(7): # Bold [b]...[/b]
                        cursor.insertText(match.group(7), self.formats['bold'])
                    elif match.group(9): # Italic [i]...[/i]
                        cursor.insertText(match.group(9), self.formats['italic'])
                    elif match.group(11) and match.group(12): # Color [color=...]...[/color]
                        color_str = match.group(11)
                        color_text = match.group(12)
                        color_format = QTextCharFormat()
                        try:
                            color_format.setForeground(QColor(color_str))
                            cursor.insertText(color_text, color_format)
                        except:
                            logger.warning(f"Invalid color format: {color_str}. Using default.")
                            cursor.insertText(color_text, self.formats['default'])
                    
                    last_end = end
                
                # Insert any remaining text after the last match
                if last_end < len(text_content):
                    cursor.insertText(text_content[last_end:], self.formats['default'])

    def _check_and_perform_pending_update(self):
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
        logger.info("Запрос на планирование обновления g4f...")
        target_version = None
        if hasattr(self, 'g4f_version_entry') and self.g4f_version_entry:
            target_version = self.g4f_version_entry.text().strip()
            if not target_version:
                QMessageBox.critical(self, _("Ошибка", "Error"),
                                     _("Пожалуйста, введите версию g4f или 'latest'.", "Please enter a g4f version or 'latest'."))
                return
        else:
            logger.error("Виджет entry для версии g4f не найден.")
            QMessageBox.critical(self, _("Ошибка", "Error"),
                                 _("Не найден элемент интерфейса для ввода версии.", "UI element for version input not found."))
            return

        try:
            self.settings.set("G4F_TARGET_VERSION", target_version)
            self.settings.set("G4F_UPDATE_PENDING", True)
            self.settings.set("G4F_VERSION", target_version)
            self.settings.save_settings()
            logger.info(f"Обновление g4f до версии '{target_version}' запланировано на следующий запуск.")
            QMessageBox.information(
                self,
                _("Запланировано", "Scheduled"),
                _("Версия g4f '{version}' будет установлена/обновлена при следующем запуске программы.",
                  "g4f version '{version}' will be installed/updated the next time the program starts.").format(version=target_version)
            )
        except Exception as e:
            logger.error(f"Ошибка при сохранении настроек для запланированного обновления: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                _("Ошибка сохранения", "Save Error"),
                _("Не удалось сохранить настройки для обновления. Пожалуйста, проверьте логи.", "Failed to save settings for the update. Please check the logs.")
            )

    def update_game_connection(self, is_connected):
        self.ConnectedToGame = is_connected
        QTimer.singleShot(0, self.update_status_colors)

    def update_all(self):
        self.update_status_colors()
        self.update_debug_info()

    def update_status_colors(self):
        self.game_connected = self.ConnectedToGame
        if hasattr(self, 'game_status_checkbox'):
            self.game_status_checkbox.setChecked(self.game_connected)
            game_color = "#00ff00" if self.game_connected else "#ffffff"
            self.game_status_checkbox.setStyleSheet(f"color: {game_color};")

        if hasattr(self, 'silero_status_checkbox'):
            self.silero_status_checkbox.setChecked(self.silero_connected)
            silero_color = "#00ff00" if self.silero_connected else "#ffffff"
            self.silero_status_checkbox.setStyleSheet(f"color: {silero_color};")
            
        if hasattr(self, 'mic_status_checkbox'):
            self.mic_status_checkbox.setChecked(self.mic_recognition_active)
            mic_color = "#00ff00" if self.mic_recognition_active else "#ffffff"
            self.mic_status_checkbox.setStyleSheet(f"color: {mic_color};")

        if hasattr(self, 'screen_capture_status_checkbox'):
            self.screen_capture_status_checkbox.setChecked(self.screen_capture_active)
            screen_color = "#00ff00" if self.screen_capture_active else "#ffffff"
            self.screen_capture_status_checkbox.setStyleSheet(f"color: {screen_color};")
            
        if hasattr(self, 'camera_capture_status_checkbox'):
            self.camera_capture_status_checkbox.setChecked(self.camera_capture_active)
            camera_color = "#00ff00" if self.camera_capture_active else "#ffffff"
            self.camera_capture_status_checkbox.setStyleSheet(f"color: {camera_color};")

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
        
        self.chat_window.verticalScrollBar().valueChanged.connect(self.on_chat_scroll)
        
        self.update_debug_info()
        self.update_token_count()
        self.chat_window.ensureCursorVisible()

    def setup_debug_controls(self, parent_layout):
        section = CollapsibleSection(_("Отладка", "Debug"), self)
        parent_layout.addWidget(section)
        
        self.debug_window = QTextEdit()
        self.debug_window.setObjectName("DebugWindow")
        self.debug_window.setFixedHeight(150)
        self.debug_window.setReadOnly(True)
        section.add_widget(self.debug_window)
        
        self.update_debug_info()

    def setup_model_controls(self, parent_layout):
        mita_config = [
            {'label': _('Использовать gpt4free', 'Use gpt4free'), 'key': 'gpt4free', 'type': 'checkbutton', 'default_checkbutton': False},
            {'label': _('gpt4free | Модель gpt4free', 'gpt4free | model gpt4free'), 'key': 'gpt4free_model', 'type': 'entry', 'default': "gemini-1.5-flash"},
        ]
        self.create_settings_section(parent_layout, _("Настройки gpt4free модели", "Gpt4free settings"), mita_config)

    def setup_common_controls(self, parent_layout):
        common_config = [
            {'label': _('Скрывать (приватные) данные', 'Hide (private) data'), 'key': 'HIDE_PRIVATE', 'type': 'checkbutton', 'default_checkbutton': True},
        ]
        # Используем шаблон для создания секции
        guiTemplates.create_settings_section(self, parent_layout, _("Общие настройки", "Common settings"), common_config)

    def validate_number_0_60(self, new_value):
        if not new_value.isdigit(): return False
        return 0 <= int(new_value) <= 60

    def validate_float_0_1(self, new_value):
        try:
            val = float(new_value)
            return 0.0 <= val <= 1.0
        except (ValueError, TypeError): return False

    def validate_float_positive(self, new_value):
        try:
            val = float(new_value)
            return val > 0.0
        except (ValueError, TypeError): return False

    def validate_float_positive_or_zero(self, new_value):
        if new_value == "": return True
        try:
            value = float(new_value)
            return value >= 0.0
        except (ValueError, TypeError): return False

    def validate_positive_integer(self, new_value):
        if new_value == "": return True
        try:
            value = int(new_value)
            return value > 0
        except (ValueError, TypeError): return False

    def validate_positive_integer_or_zero(self, new_value):
        if new_value == "": return True
        try:
            value = int(new_value)
            return value >= 0
        except (ValueError, TypeError): return False

    def validate_float_0_to_1(self, new_value):
        if new_value == "": return True
        try:
            value = float(new_value)
            return 0.0 <= value <= 1.0
        except (ValueError, TypeError): return False

    def validate_float_0_to_2(self, new_value):
        if new_value == "": return True
        try:
            value = float(new_value)
            return 0.0 <= value <= 2.0
        except (ValueError, TypeError): return False

    def validate_float_minus2_to_2(self, new_value):
        if new_value == "": return True
        try:
            value = float(new_value)
            return -2.0 <= value <= 2.0
        except (ValueError, TypeError): return False

    def load_api_settings(self, update_model):
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
            if update_model and hasattr(self, 'model'):
                if self.api_key: self.model.api_key = self.api_key
                if self.api_url: self.model.api_url = self.api_url
                if self.api_model: self.model.api_model = self.api_model
                self.model.makeRequest = self.makeRequest
                self.model.update_openai_client()
            logger.info("Настройки загружены из файла")
        except Exception as e:
            logger.info(f"Ошибка загрузки: {e}")

    def update_debug_info(self):
        if self.debug_window:
            self.debug_window.clear()
            debug_info = self.model.current_character.current_variables_string()
            self.debug_window.setText(debug_info)

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
                    current_context_tokens, max_model_tokens, max_model_tokens, cost))
            self.token_count_label.show()
        else:
            self.token_count_label.hide()
        self.update_debug_info()

    def insert_dialog(self, input_text="", response="", system_text=""):
        MitaName = self.model.current_character.name
        if input_text:
            self.insert_message("user", f"{input_text}\n")
        if system_text:
            self.insert_message("System", f"{system_text}\n\n")
        if response:
            self.insert_message("assistant", f"{response}\n\n")

    def clear_chat_display(self):
        self.chat_window.clear()
        if self._images_in_chat:
            for img_path in self._images_in_chat:
                if os.path.exists(img_path):
                    try:
                        os.remove(img_path)
                    except OSError as e:
                        logger.error(f"Could not remove temp image {img_path}: {e}")
            self._images_in_chat.clear()

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
            if hasattr(self, 'camera_capture') and self.camera_capture and self.camera_capture.is_running():
                history_limit = int(self.settings.get("CAMERA_CAPTURE_HISTORY_LIMIT", 1))
                camera_frames = self.camera_capture.get_recent_frames(history_limit)
                if camera_frames:
                    all_image_data.extend(camera_frames)
                    logger.info(f"Добавлено {len(camera_frames)} кадров с камеры для отправки.")
                else:
                    logger.info("Захват с камеры включен, но кадры не готовы или история пуста.")

        if not user_input and not system_input and not all_image_data:
            return

        self.last_image_request_time = time.time()

        display_content = []
        if user_input:
            display_content.append({"type": "text", "content": user_input})
            self.user_entry.clear()
            
        if all_image_data:
            if not user_input:
                 display_content.append({"type": "text", "content": _("<Изображение экрана>", "<Screen Image>") + "\n"})
            for img in all_image_data:
                display_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(img).decode('utf-8')}"}})

        if display_content:
            self.insert_message("user", display_content)

        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.async_send_message(user_input, system_input, all_image_data), self.loop)

    async def async_send_message(self, user_input: str, system_input: str = "", image_data: list[bytes] = None):
        try:
            response = await asyncio.wait_for(
                self.loop.run_in_executor(None, lambda: self.model.generate_response(user_input, system_input, image_data)),
                timeout=60.0
            )
            QTimer.singleShot(0, lambda: self.insert_message("assistant", response))
            QTimer.singleShot(0, self.update_all)
            QTimer.singleShot(0, self.update_token_count)
            if self.server and self.server.client_socket:
                try:
                    self.server.send_message_to_server(response)
                    logger.info("Сообщение отправлено на сервер (связь с игрой есть)")
                except Exception as e:
                    logger.info(f"Ошибка при отправке сообщения на сервер: {e}")
            else:
                logger.info("Нет активного подключения к клиенту игры")
        except asyncio.TimeoutError:
            logger.info("Тайм-аут: генерация ответа заняла слишком много времени.")

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
            logger.info(
                f"Поток захвата с камеры запущен с индексом {camera_index}, интервалом {interval}, качеством {quality}, {fps} FPS, историей {max_history_frames} кадров, разрешением {capture_width}x{capture_height}.")
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
            logger.info(
                f"Поток захвата экрана запущен с интервалом {interval}, качеством {quality}, {fps} FPS, историей {max_history_frames} кадров, разрешением {capture_width}x{capture_height}.")

            self.screen_capture_active = True
            if self.settings.get("SEND_IMAGE_REQUESTS", False):
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

    def on_chat_scroll(self, value):
        if self.loading_more_history:
            return
        if value == self.chat_window.verticalScrollBar().minimum():
            self.load_more_history()

    def load_more_history(self):
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

            scrollbar = self.chat_window.verticalScrollBar()
            old_scroll_max = scrollbar.maximum()

            for entry in reversed(messages_to_prepend):
                role = entry["role"]
                content = entry["content"]
                message_time = entry.get("time", "???")
                self.insert_message(role, content, insert_at_start=True, message_time=message_time)

            QApplication.processEvents()
            new_scroll_max = scrollbar.maximum()
            scrollbar.setValue(new_scroll_max - old_scroll_max)

            self.loaded_messages_offset += len(messages_to_prepend)
            logger.info(f"Загружено еще {len(messages_to_prepend)} сообщений. Всего загружено: {self.loaded_messages_offset}")

        finally:
            self.loading_more_history = False

    def _show_loading_popup(self, message):
        self.loading_popup = LoadingDialog(message, self)
        self.loading_popup.cancel_button.hide()
        self.loading_popup.show()

    def _close_loading_popup(self):
        if hasattr(self, 'loading_popup') and self.loading_popup:
            self.loading_popup.close()
            self.loading_popup = None

    def all_settings_actions(self, key, value):
        if key in ["SILERO_USE", "VOICEOVER_METHOD", "AUDIO_BOT"]:
            if hasattr(self, 'switch_voiceover_settings'):
                self.switch_voiceover_settings()

        if key == "SILERO_TIME":
            if self.bot_handler:
                self.bot_handler.silero_time_limit = int(value)

        if key == "AUDIO_BOT":
            if value.startswith("@CrazyMitaAIbot"):
                QMessageBox.information(self, "Информация", "VinerX: наши товарищи из CrazyMitaAIbot предоставляет озвучку бесплатно буквально со своих пк, будет время - загляните к ним в тг, скажите спасибо)")
            if self.bot_handler:
                self.bot_handler.tg_bot = value

        elif key == "CHARACTER":
            self.model.current_character_to_change = value
            self.model.check_change_current_character()

        elif key == "NM_API_MODEL": self.model.api_model = value.strip()
        elif key == "NM_API_KEY": self.model.api_key = value.strip()
        elif key == "NM_API_URL": self.model.api_url = value.strip()
        elif key == "NM_API_REQ": self.model.makeRequest = bool(value)
        elif key == "gpt4free_model": self.model.gpt4free_model = value.strip()
        
        elif key == "MODEL_MAX_RESPONSE_TOKENS": self.model.max_response_tokens = int(value)
        elif key == "MODEL_TEMPERATURE": self.model.temperature = float(value)
        elif key == "MODEL_PRESENCE_PENALTY": self.model.presence_penalty = float(value)
        elif key == "MODEL_FREQUENCY_PENALTY": self.model.frequency_penalty = float(value)
        elif key == "MODEL_LOG_PROBABILITY": self.model.log_probability = float(value)
        elif key == "MODEL_TOP_K": self.model.top_k = int(value)
        elif key == "MODEL_TOP_P": self.model.top_p = float(value)
        elif key == "MODEL_THOUGHT_PROCESS": self.model.thinking_budget = float(value)

        elif key == "MODEL_MESSAGE_LIMIT": self.model.memory_limit = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_COUNT": self.model.max_request_attempts = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_TIME": self.model.request_delay = float(value)
        
        elif key == "MIC_ACTIVE":
            if bool(value):
                SpeechRecognition.speach_recognition_start(self.device_id, self.loop)
                self.mic_recognition_active = True
            else:
                SpeechRecognition.speach_recognition_stop()
                self.mic_recognition_active = False
            self.update_status_colors()

        elif key == "ENABLE_SCREEN_ANALYSIS":
            if bool(value): self.start_screen_capture_thread()
            else: self.stop_screen_capture_thread()
        elif key == "ENABLE_CAMERA_CAPTURE":
            if bool(value): self.start_camera_capture_thread()
            else: self.stop_camera_capture_thread()
        elif key in ["SCREEN_CAPTURE_INTERVAL", "SCREEN_CAPTURE_QUALITY", "SCREEN_CAPTURE_FPS", "SCREEN_CAPTURE_HISTORY_LIMIT", "SCREEN_CAPTURE_TRANSFER_LIMIT", "SCREEN_CAPTURE_WIDTH", "SCREEN_CAPTURE_HEIGHT"]:
            if self.screen_capture_instance and self.screen_capture_instance.is_running():
                logger.info(f"Настройка захвата экрана '{key}' изменена на '{value}'. Перезапускаю поток захвата.")
                self.stop_screen_capture_thread()
                self.start_screen_capture_thread()
        elif key == "SEND_IMAGE_REQUESTS":
            if bool(value): self.start_image_request_timer()
            else: self.stop_image_request_timer()
        elif key == "IMAGE_REQUEST_INTERVAL":
            if self.image_request_timer_running:
                logger.info(f"Настройка интервала запросов изображений изменена на '{value}'. Перезапускаю таймер.")
                self.stop_image_request_timer()
                self.start_image_request_timer()
        elif key in ["EXCLUDE_GUI_WINDOW", "EXCLUDE_WINDOW_TITLE"]:
            exclude_gui = self.settings.get("EXCLUDE_GUI_WINDOW", False)
            exclude_title = self.settings.get("EXCLUDE_WINDOW_TITLE", "")
            hwnd_to_pass = None
            if exclude_gui:
                hwnd_to_pass = self.winId()
                logger.info(f"Получен HWND окна GUI для исключения: {hwnd_to_pass}")
            elif exclude_title:
                try:
                    hwnd_to_pass = win32gui.FindWindow(None, exclude_title)
                    if hwnd_to_pass:
                        logger.info(f"Найден HWND для заголовка '{exclude_title}': {hwnd_to_pass}")
                    else:
                        logger.warning(f"Окно с заголовком '{exclude_title}' не найдено.")
                except Exception as e:
                    logger.error(f"Ошибка при поиске окна по заголовку '{exclude_title}': {e}")
            if self.screen_capture_instance:
                self.screen_capture_instance.set_exclusion_parameters(hwnd_to_pass, exclude_title, exclude_gui or bool(exclude_title))
            if self.screen_capture_instance and self.screen_capture_instance.is_running():
                logger.info(f"Настройка исключения окна '{key}' изменена на '{value}'. Перезапускаю поток захвата.")
                self.stop_screen_capture_thread()
                self.start_screen_capture_thread()
        elif key == "RECOGNIZER_TYPE":
            SpeechRecognition.active = False
            time.sleep(0.1)
            SpeechRecognition.set_recognizer_type(value)
            if self.settings.get("MIC_ACTIVE", False):
                SpeechRecognition.active = True
                SpeechRecognition.speach_recognition_start(self.device_id, self.loop)
            if hasattr(self, 'update_vosk_model_visibility'):
                microphone_settings.update_vosk_model_visibility(self, value)
        elif key == "VOSK_MODEL": SpeechRecognition.vosk_model = value
        elif key == "SILENCE_THRESHOLD": SpeechRecognition.SILENCE_THRESHOLD = float(value)
        elif key == "SILENCE_DURATION": SpeechRecognition.SILENCE_DURATION = float(value)
        elif key == "VOSK_PROCESS_INTERVAL": SpeechRecognition.VOSK_PROCESS_INTERVAL = float(value)
        
        elif key == "IMAGE_QUALITY_REDUCTION_ENABLED": self.model.image_quality_reduction_enabled = bool(value)
        elif key == "IMAGE_QUALITY_REDUCTION_START_INDEX": self.model.image_quality_reduction_start_index = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_USE_PERCENTAGE": self.model.image_quality_reduction_use_percentage = bool(value)
        elif key == "IMAGE_QUALITY_REDUCTION_MIN_QUALITY": self.model.image_quality_reduction_min_quality = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_DECREASE_RATE": self.model.image_quality_reduction_decrease_rate = int(value)

        elif key == "ENABLE_HISTORY_COMPRESSION_ON_LIMIT": self.model.enable_history_compression_on_limit = bool(value)
        elif key == "ENABLE_HISTORY_COMPRESSION_PERIODIC": self.model.enable_history_compression_periodic = bool(value)
        elif key == "HISTORY_COMPRESSION_OUTPUT_TARGET": self.model.history_compression_output_target = str(value)
        elif key == "HISTORY_COMPRESSION_PERIODIC_INTERVAL": self.model.history_compression_periodic_interval = int(value)
        elif key == "HISTORY_COMPRESSION_MIN_PERCENT_TO_COMPRESS": self.model.history_compression_min_messages_to_compress = float(value)

        elif key == "CHAT_FONT_SIZE":
            try:
                font_size = int(value)
                self.setup_tags_configurations(font_size)
                self.load_chat_history()
                logger.info(f"Размер шрифта чата изменен на: {font_size}")
            except (ValueError, Exception) as e:
                logger.error(f"Ошибка при изменении размера шрифта чата: {e}")
        elif key in ["SHOW_CHAT_TIMESTAMPS", "MAX_CHAT_HISTORY_DISPLAY", "HIDE_CHAT_TAGS"]:
            self.load_chat_history()
            logger.info(f"Настройка '{key}' изменена на: {value}. История чата перезагружена.")

        elif key in ["SHOW_TOKEN_INFO", "TOKEN_COST_INPUT", "TOKEN_COST_OUTPUT", "MAX_MODEL_TOKENS"]:
            self.update_token_count()

    def create_settings_section(self, parent_layout, title, settings_config):
        return guiTemplates.create_settings_section(self, parent_layout, title, settings_config)

    def create_setting_widget(self, parent, label, setting_key, widget_type='entry',
                              options=None, default='', default_checkbutton=False, validation=None, tooltip=None,
                              width=None, height=None, command=None, hide=False, widget_name=None):
        return guiTemplates.create_setting_widget(
            gui=self,
            parent=parent,
            label=label,
            setting_key=setting_key,
            widget_type=widget_type,
            options=options,
            default=default,
            default_checkbutton=default_checkbutton,
            validation=validation,
            tooltip=tooltip,
            hide=hide,
            command=command,
            widget_name=widget_name or setting_key
        )

    def _save_setting(self, key, value):
        self.settings.set(key, value)
        self.settings.save_settings()
        self.all_settings_actions(key, value)

    def get_news_content(self):
        try:
            response = requests.get('https://raw.githubusercontent.com/VinerX/NeuroMita/main/NEWS.md', timeout=10)
            if response.status_code == 200:
                return response.text
            return _('Не удалось загрузить новости', 'Failed to load news')
        except Exception as e:
            logger.info(f"Ошибка при получении новостей: {e}")
            return _('Ошибка при загрузке новостей', 'Error loading news')

    def setup_news_control(self, parent_layout):
        section = CollapsibleSection(_("Новости", "News"), self)
        parent_layout.addWidget(section)
        
        news_label = QLabel(self.get_news_content())
        news_label.setWordWrap(True)
        news_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        section.add_widget(news_label)

    def closeEvent(self, event):
        self.check_talk_timer.stop()
        self.stop_screen_capture_thread()
        self.stop_camera_capture_thread()
        self.delete_all_sound_files()
        self.stop_server()
        logger.info("Закрываемся")
        super().closeEvent(event)

    def close_app(self):
        logger.info("Завершение программы...")
        self.close()

    @staticmethod
    def delete_all_sound_files():
        for ext in ["*.wav", "*.mp3", "*.png"]:
            files = glob.glob(ext)
            for file in files:
                try:
                    os.remove(file)
                    logger.info(f"Удален файл: {file}")
                except Exception as e:
                    logger.info(f"Ошибка при удалении файла {file}: {e}")

    async def run_local_voiceover(self, text):
        result_path = None
        try:
            character = self.model.current_character if hasattr(self.model, "current_character") else None
            output_file = f"MitaVoices/output_{uuid.uuid4()}.wav"
            absolute_audio_path = os.path.abspath(output_file)
            os.makedirs(os.path.dirname(absolute_audio_path), exist_ok=True)
            result_path = await self.local_voice.voiceover(text=text, output_file=absolute_audio_path, character=character)
            if result_path:
                logger.info(f"Локальная озвучка сохранена в: {result_path}")
                if not self.ConnectedToGame and self.settings.get("VOICEOVER_LOCAL_CHAT"):
                    await AudioHandler.handle_voice_file(result_path, self.settings.get("LOCAL_VOICE_DELETE_AUDIO", True) if os.environ.get("ENABLE_VOICE_DELETE_CHECKBOX", "0") == "1" else True)
                elif self.ConnectedToGame:
                    self.patch_to_sound_file = result_path
                    logger.info(f"Путь к файлу для игры: {self.patch_to_sound_file}")
                else:
                    logger.info("Озвучка в локальном чате отключена.")
            else:
                logger.error("Локальная озвучка не удалась, файл не создан.")
        except Exception as e:
            logger.error(f"Ошибка при выполнении локальной озвучки: {e}")

    def on_local_voice_selected(self, model_name):
        if not model_name:
            self.update_local_model_status_indicator()
            return

        selected_model_id = None
        selected_model = None
        for model in LOCAL_VOICE_MODELS:
            if model["name"] == model_name:
                selected_model = model
                selected_model_id = model["id"]
                break

        if not selected_model_id:
            QMessageBox.critical(self, _("Ошибка", "Error"), _("Не удалось определить ID выбранной модели", "Could not determine ID of selected model"))
            self.update_local_model_status_indicator()
            return
        
        if selected_model_id in ["medium+", "medium+low"] and self.local_voice.first_compiled == False:
            reply = QMessageBox.question(self, _("Внимание", "Warning"),
                _("Невозможно перекомпилировать модель Fish Speech в Fish Speech+ - требуется перезапуск программы. \n\n Перезапустить?",
                  "Cannot recompile Fish Speech model to Fish Speech+ - program restart required. \n\n Restart?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                if self.last_voice_model_selected:
                    self.local_voice_combobox.setCurrentText(self.last_voice_model_selected["name"])
                else:
                    self.local_voice_combobox.setCurrentIndex(-1)
                    self.settings.set("NM_CURRENT_VOICEOVER", None)
                    self.settings.save_settings()
                self.update_local_model_status_indicator()
                return
            else:
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
        model_id = model["id"]
        model_name = model["name"]

        downloader = ModelsDownloader(target_dir=".")
        logger.info(f"Проверка/загрузка файлов для '{model_name}'...")

        models_are_ready = downloader.download_models_if_needed(self)

        if not models_are_ready:
            logger.warning(f"Файлы моделей для '{model_name}' не готовы (загрузка не удалась или отменена).")
            QMessageBox.critical(self, _("Ошибка", "Error"), _("Не удалось подготовить файлы моделей. Инициализация отменена.", "Failed to prepare model files. Initialization cancelled."))
            return

        logger.info(f"Модели для '{model_name}' готовы. Запуск инициализации...")

        loading_window = LoadingDialog(_("Инициализация модели", "Initializing model") + f" {model_name}", self)
        loading_window.setWindowTitle(_("Загрузка модели", "Loading model") + f" {model_name}")
        
        self.model_loading_cancelled = False
        
        def on_cancel():
            self.cancel_model_loading(loading_window)
        loading_window.cancel_button.clicked.connect(on_cancel)
        
        loading_thread = threading.Thread(
            target=self.init_model_thread,
            args=(model_id, loading_window),
            daemon=True
        )
        loading_thread.start()
        
        loading_window.exec()

    def cancel_model_loading(self, loading_window):
        logger.info("Загрузка модели отменена пользователем.")
        self.model_loading_cancelled = True
        loading_window.reject()

        restored_model_id = None
        if self.last_voice_model_selected:
            if hasattr(self, 'local_voice_combobox'):
                self.local_voice_combobox.setCurrentText(self.last_voice_model_selected["name"])
            restored_model_id = self.last_voice_model_selected["id"]
            self.settings.set("NM_CURRENT_VOICEOVER", restored_model_id)
            self.current_local_voice_id = restored_model_id
        else:
            if hasattr(self, 'local_voice_combobox'):
                self.local_voice_combobox.setCurrentIndex(-1)
            self.settings.set("NM_CURRENT_VOICEOVER", None)
            self.current_local_voice_id = None

        self.settings.save_settings()
        self.update_local_model_status_indicator()

    def init_model_thread(self, model_id, loading_window):
        try:
            QTimer.singleShot(0, lambda: loading_window.set_message(_("Загрузка настроек...", "Loading settings...")))
            success = False
            if not self.model_loading_cancelled:
                QTimer.singleShot(0, lambda: loading_window.set_message(_("Инициализация модели...", "Initializing model...")))
                success = self.local_voice.initialize_model(model_id, init=True)
            
            if self.model_loading_cancelled:
                return

            if success:
                QTimer.singleShot(0, lambda: self.finish_model_loading(model_id, loading_window))
            else:
                error_message = _("Не удалось инициализировать модель. Проверьте логи.", "Failed to initialize model. Check logs.")
                QTimer.singleShot(0, lambda: [
                    QMessageBox.critical(loading_window, _("Ошибка инициализации", "Initialization Error"), error_message),
                    self.cancel_model_loading(loading_window)
                ])
        except Exception as e:
            logger.error(f"Критическая ошибка в потоке инициализации модели {model_id}: {e}", exc_info=True)
            if not self.model_loading_cancelled:
                error_message = _("Критическая ошибка при инициализации модели: ", "Critical error during model initialization: ") + str(e)
                QTimer.singleShot(0, lambda: [
                    QMessageBox.critical(loading_window, _("Ошибка", "Error"), error_message),
                    self.cancel_model_loading(loading_window)
                ])

    def finish_model_loading(self, model_id, loading_window):
        logger.info(f"Модель {model_id} успешно инициализирована.")
        loading_window.accept()
        
        self.local_voice.current_model = model_id
        
        self.last_voice_model_selected = None
        for model in LOCAL_VOICE_MODELS:
            if model["id"] == model_id:
                self.last_voice_model_selected = model
                break

        self.settings.set("NM_CURRENT_VOICEOVER", model_id)
        self.settings.save_settings()
        self.current_local_voice_id = model_id

        QMessageBox.information(self, _("Успешно", "Success"), _("Модель {} успешно инициализирована!", "Model {} initialized successfully!").format(model_id))
        self.update_local_voice_combobox()

    def initialize_last_local_model_on_startup(self):
        if self.settings.get("LOCAL_VOICE_LOAD_LAST", False):
            logger.info("Проверка автозагрузки последней локальной модели...")
            last_model_id = self.settings.get("NM_CURRENT_VOICEOVER", None)
            if last_model_id:
                logger.info(f"Найдена последняя модель для автозагрузки: {last_model_id}")
                model_to_load = next((m for m in LOCAL_VOICE_MODELS if m["id"] == last_model_id), None)
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
        if hasattr(self, 'local_model_status_label'):
            show_combobox_indicator = False
            current_model_id_combo = self.settings.get("NM_CURRENT_VOICEOVER", None)
            if current_model_id_combo:
                model_installed_combo = self.local_voice.is_model_installed(current_model_id_combo)
                if not model_installed_combo or not self.local_voice.is_model_initialized(current_model_id_combo):
                    show_combobox_indicator = True
            self.local_model_status_label.setVisible(show_combobox_indicator)

        if hasattr(self, 'voiceover_section') and hasattr(self.voiceover_section, 'warning_label'):
            show_section_warning = False
            voiceover_method = self.settings.get("VOICEOVER_METHOD", "TG")
            current_model_id_section = self.settings.get("NM_CURRENT_VOICEOVER", None)
            if voiceover_method == "Local" and current_model_id_section:
                if not self.local_voice.is_model_installed(current_model_id_section) or not self.local_voice.is_model_initialized(current_model_id_section):
                    show_section_warning = True
            self.voiceover_section.warning_label.setVisible(show_section_warning)

    def switch_voiceover_settings(self):
        use_voice = self.settings.get("SILERO_USE", False)
        current_method = self.settings.get("VOICEOVER_METHOD", "TG")

        if hasattr(self, 'use_voice_checkbox_frame'):
            is_checked = self.settings.get('SILERO_USE', False)
            if hasattr(self, 'method_frame'): self.method_frame.setVisible(is_checked)
            if hasattr(self, 'tg_settings_frame'): self.tg_settings_frame.setVisible(is_checked and current_method == "TG")
            if hasattr(self, 'local_settings_frame'): self.local_settings_frame.setVisible(is_checked and current_method == "Local")

        if use_voice and current_method == "Local":
            self.update_local_voice_combobox()
            self.update_local_model_status_indicator()
        
        self.voiceover_method = current_method
        self.check_triton_dependencies()
        
    def update_local_voice_combobox(self):
        if not hasattr(self, 'local_voice_combobox'): return

        installed_models_names = [model["name"] for model in LOCAL_VOICE_MODELS if self.local_voice.is_model_installed(model["id"])]
        
        current_text = self.local_voice_combobox.currentText()
        self.local_voice_combobox.blockSignals(True)
        self.local_voice_combobox.clear()
        self.local_voice_combobox.addItems(installed_models_names)
        self.local_voice_combobox.blockSignals(False)

        current_model_id = self.settings.get("NM_CURRENT_VOICEOVER", None)
        current_model_name = next((m["name"] for m in LOCAL_VOICE_MODELS if m["id"] == current_model_id), "")

        if current_model_name and current_model_name in installed_models_names:
            self.local_voice_combobox.setCurrentText(current_model_name)
        elif installed_models_names:
            self.local_voice_combobox.setCurrentIndex(0)
        else:
            self.local_voice_combobox.setCurrentIndex(-1)
            
        self.update_local_model_status_indicator()
        self.check_triton_dependencies()

    def check_triton_dependencies(self):
        # Удаляем старое предупреждение, если оно есть
        if hasattr(self, 'triton_warning_label_frame') and self.triton_warning_label_frame:
            self.triton_warning_label_frame.deleteLater()
            delattr(self, 'triton_warning_label_frame')

        # Условие показа предупреждения
        if self.settings.get("VOICEOVER_METHOD") != "Local" or not hasattr(self, 'local_settings_frame'):
            return

        try:
            import triton
        except (ImportError, Exception):
            logger.warning("Зависимости Triton не найдены! Модели Fish Speech+ могут не работать.")
            
            # Создаем виджет через шаблон, чтобы он был в том же стиле
            self.triton_warning_label_frame = guiTemplates.create_setting_widget(
                gui=self,
                parent=self.local_settings_frame,
                label=_("⚠️ Triton не найден! Модели medium+ и medium+low могут не работать.", 
                        "⚠️ Triton not found! Models medium+ and medium+low might not work."),
                widget_type='text' # Используем тип 'text' для создания стилизованного QLabel
            )
            # Применяем специальный стиль через ID
            if self.triton_warning_label_frame:
                label_widget = self.triton_warning_label_frame.findChild(QLabel)
                if label_widget:
                    label_widget.setObjectName("TritonWarningLabel")
                # Вставляем предупреждение в начало секции локальных настроек
                if hasattr(self, 'local_settings_frame') and self.local_settings_frame.layout():
                    self.local_settings_frame.layout().insertWidget(0, self.triton_warning_label_frame)
    
    def open_local_model_installation_window(self):
        try:
            from voice_model_settings import VoiceModelSettingsWindow
            config_dir = "Settings"
            os.makedirs(config_dir, exist_ok=True)

            def on_save_callback(settings_data):
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

            self.install_window = QDialog(self)
            self.install_window.setWindowTitle(_("Управление локальными моделями", "Manage Local Models"))
            
            VoiceModelSettingsWindow(
                master=self.install_window,
                config_dir=config_dir,
                on_save_callback=on_save_callback,
                local_voice=self.local_voice,
                check_installed_func=self.check_module_installed,
            )
            self.install_window.exec()
        except ImportError:
            logger.error("Не найден модуль voice_model_settings.py. Установка моделей недоступна.")
            QMessageBox.critical(self, _("Ошибка", "Error"), _("Не найден файл voice_model_settings.py", "voice_model_settings.py not found."))
        except Exception as e:
            logger.error(f"Ошибка при открытии окна установки моделей: {e}", exc_info=True)
            QMessageBox.critical(self, _("Ошибка", "Error"), _("Не удалось открыть окно установки моделей.", "Failed to open model installation window."))

    def refresh_local_voice_modules(self):
        import importlib, sys
        logger.info("Попытка обновления модулей локальной озвучки...")
        modules_to_check = { "tts_with_rvc": "TTS_RVC", "fish_speech_lib.inference": "FishSpeech", "triton": None }
        lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Lib")
        if lib_path not in sys.path: sys.path.insert(0, lib_path)

        for module_name, class_name in modules_to_check.items():
            try:
                if module_name in sys.modules:
                    importlib.reload(sys.modules[module_name])
                else:
                    importlib.import_module(module_name)
                if class_name:
                    actual_class = getattr(sys.modules[module_name], class_name)
                    if module_name == "tts_with_rvc": self.local_voice.tts_rvc_module = actual_class
                    elif module_name == "fish_speech_lib.inference": self.local_voice.fish_speech_module = actual_class
                logger.info(f"Модуль {module_name} успешно обработан.")
            except ImportError:
                logger.warning(f"Модуль {module_name} не найден или не установлен.")
                if module_name == "tts_with_rvc": self.local_voice.tts_rvc_module = None
                elif module_name == "fish_speech_lib.inference": self.local_voice.fish_speech_module = None
            except Exception as e:
                logger.error(f"Ошибка при обработке модуля {module_name}: {e}", exc_info=True)
        self.check_triton_dependencies()

    def check_module_installed(self, module_name):
        logger.info(f"Проверка установки модуля: {module_name}")
        try:
            spec = importlib.util.find_spec(module_name)
            return spec is not None and spec.loader is not None
        except (ValueError, Exception) as e:
            logger.error(f"Ошибка при проверке модуля {module_name}: {e}")
            return False

    def check_available_vram(self):
        logger.warning("Проверка VRAM не реализована, возвращается фиктивное значение.")
        return 100

    def _show_ffmpeg_installing_popup(self):
        if self.ffmpeg_install_popup and self.ffmpeg_install_popup.isVisible(): return
        self.ffmpeg_install_popup = LoadingDialog("Идет установка FFmpeg...\nПожалуйста, подождите.", self)
        self.ffmpeg_install_popup.cancel_button.hide()
        self.ffmpeg_install_popup.setModal(False)
        self.ffmpeg_install_popup.show()

    def _close_ffmpeg_installing_popup(self):
        if self.ffmpeg_install_popup:
            self.ffmpeg_install_popup.close()
            self.ffmpeg_install_popup = None

    def _show_ffmpeg_error_popup(self):
        message = (
            "Не удалось автоматически установить FFmpeg.\n\n"
            "Он необходим для некоторых функций программы (например, обработки аудио).\n\n"
            "Пожалуйста, скачайте FFmpeg вручную с официального сайта:\n"
            f"{"https://ffmpeg.org/download.html"}\n\n"
            f"Распакуйте архив и поместите файл 'ffmpeg.exe' в папку программы:\n"
            f"{Path(".").resolve()}"
        )
        QMessageBox.critical(self, "Ошибка установки FFmpeg", message)

    def _ffmpeg_install_thread_target(self):
        QTimer.singleShot(0, self._show_ffmpeg_installing_popup)
        logger.info("Starting FFmpeg installation attempt...")
        success = install_ffmpeg()
        logger.info(f"FFmpeg installation attempt finished. Success: {success}")
        QTimer.singleShot(0, self._close_ffmpeg_installing_popup)
        if not success:
            QTimer.singleShot(0, self._show_ffmpeg_error_popup)

    def check_and_install_ffmpeg(self):
        ffmpeg_path = Path(".") / "ffmpeg.exe"
        logger.info(f"Checking for FFmpeg at: {ffmpeg_path}")
        if not ffmpeg_path.exists():
            logger.info("FFmpeg not found. Starting installation process in a separate thread.")
            install_thread = threading.Thread(target=self._ffmpeg_install_thread_target, daemon=True)
            install_thread.start()
        else:
            logger.info("FFmpeg found. No installation needed.")

    def on_voice_language_selected(self, selected_language):
        if not hasattr(self, 'voice_language_var'):
            logger.warning("Переменная voice_language_var не найдена.")
            return

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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    # This is needed for Windows to show the app icon in the taskbar
    if sys.platform == 'win32':
        import ctypes
        myappid = 'mycompany.myproduct.subproduct.version'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        
    # Replace the tkinter CollapsibleSection with the PyQt one for modules that use it
    guiTemplates.CollapsibleSection = CollapsibleSection
    # SettingsManager.CollapsibleSection = CollapsibleSection # If it were used there
    
    main_win = ChatGUI()
    main_win.show()
    sys.exit(app.exec())
