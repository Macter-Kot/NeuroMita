import io
import base64
import re
import time
from pathlib import Path
import os

from pyqt_styles.styles import get_stylesheet
from utils import _, process_text_to_voice
from main_logger import logger
import gui_templates
from settings_manager import CollapsibleSection
from ui.settings.voiceover_settings import LOCAL_VOICE_MODELS

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QPropertyAnimation, QBuffer, QIODevice, QEvent 
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QScrollArea, QFrame, QSplitter,
    QMessageBox, QComboBox, QCheckBox, QDialog, QProgressBar,
    QTextBrowser, QLineEdit, QFileDialog, QStyle, QGraphicsOpacityEffect
)
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont, QImage, QIcon, QPalette, QKeyEvent, QPixmap
import qtawesome as qta

from ui import chat_area, status_indicators, debug_area, news_area
from ui.settings import (
    api_settings, character_settings, chat_settings, common_settings,
    g4f_settings, gamemaster_settings, general_model_settings,
    language_settings, microphone_settings, screen_analysis_settings,
    token_settings, voiceover_settings, command_replacer_settings, history_compressor,
    prompt_catalogue_settings
)

from ui.overlay_widget import OverlayWidget
from ui.image_viewer_widget import ImageViewerWidget
from ui.image_preview_widget import ImagePreviewBar

from ui.mita_status_widget import MitaStatusWidget

from voice_model_controller import VoiceModelController

class ChatGUI(QMainWindow):
    update_chat_signal = pyqtSignal(str, str, bool, str)
    update_status_signal = pyqtSignal()
    update_debug_signal = pyqtSignal()

    prepare_stream_signal = pyqtSignal()
    append_stream_chunk_signal = pyqtSignal(str)
    finish_stream_signal = pyqtSignal()

    
    show_thinking_signal = pyqtSignal(str)
    show_error_signal = pyqtSignal(str)
    hide_status_signal = pyqtSignal()
    pulse_error_signal = pyqtSignal()

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        
        self.voice_language_var = None
        self.local_voice_combobox = None
        self.debug_window = None
        self.mic_combobox = None
        self.chat_window = None
        self.token_count_label = None
        self.user_entry = None
        self.attachment_label = None
        self.attach_button = None
        self.send_screen_button = None

        self.setWindowTitle(_("Чат с NeuroMita", "NeuroMita Chat"))
        self.setWindowIcon(QIcon('src/Icon.png'))

        
        self.staged_image_data = []

        self.ffmpeg_install_popup = None

        self.update_chat_signal.connect(self._insert_message_slot)
        self.update_status_signal.connect(self.update_status_colors)
        self.update_debug_signal.connect(self.update_debug_info)

        self.prepare_stream_signal.connect(self._prepare_stream_slot)
        self.append_stream_chunk_signal.connect(self._append_stream_chunk_slot)
        self.finish_stream_signal.connect(self._finish_stream_slot)

        
        self.show_thinking_signal.connect(self._show_thinking_slot)
        self.show_error_signal.connect(self._show_error_slot)
        self.hide_status_signal.connect(self._hide_status_slot)
        self.pulse_error_signal.connect(self._pulse_error_slot)

        self.setup_ui()
        self.chat_window.installEventFilter(self)

        self.overlay = OverlayWidget(self)
        self.image_preview_bar = None
        self._init_image_preview()

        self.load_chat_history()

        try:
            microphone_settings.load_mic_settings(self)
        except Exception as e:
            logger.info("Не удалось удачно получить настройки микрофона", e)

        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.controller.check_text_to_talk_or_send)
        self.check_timer.start(150)

        QTimer.singleShot(500, self.initialize_last_local_model_on_startup)

        
        self.prepare_stream_signal.connect(self._on_stream_start)
        self.finish_stream_signal.connect(self._on_stream_finish)

        self.update_status_colors()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        self.setStyleSheet(get_stylesheet())
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        left_widget = QWidget()
        splitter.addWidget(left_widget)
        self.setup_left_frame(left_widget)
        
        right_widget = QWidget()
        splitter.addWidget(right_widget)
        self.setup_right_frame(right_widget)
        
        splitter.setSizes([700, 500])
        
        main_layout.addWidget(splitter)
        
        self.resize(1200, 800)

    def setup_left_frame(self, parent):
        layout = QVBoxLayout(parent)
        layout.setSpacing(5)
        
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
        
        self.chat_window = QTextBrowser()
        self.chat_window.setOpenExternalLinks(False)
        self.chat_window.setReadOnly(True)
        initial_font_size = int(self.controller.settings.get("CHAT_FONT_SIZE", 12))
        font = QFont("Arial", initial_font_size)
        self.chat_window.setFont(font)
        
        layout.addWidget(self.chat_window, 1)

        self._create_scroll_to_bottom_button()

        
        self.mita_status = MitaStatusWidget(self.chat_window)
        self._position_mita_status()
        
        input_frame = QFrame()
        input_frame.setStyleSheet(get_stylesheet())
        input_layout = QVBoxLayout(input_frame)
        
        self.token_count_label = QLabel(_("Токены: 0/0 | Стоимость: 0.00 ₽", "Tokens: 0/0 | Cost: 0.00 ₽"))
        self.token_count_label.setStyleSheet("font-size: 10px;")
        input_layout.addWidget(self.token_count_label)
        
        # Создаем контейнер для поля ввода с кнопками внутри
        input_container = QWidget()
        input_container.setStyleSheet("""
            QWidget {
                background-color: #252525;
                border: 1px solid #4a4a4a;
                border-radius: 3px;
            }
            QWidget:focus-within {
                border: 1px solid #8a2be2;
            }
        """)
        
        # Используем QGridLayout для более точного позиционирования
        from PyQt6.QtWidgets import QGridLayout
        container_layout = QGridLayout(input_container)
        container_layout.setContentsMargins(5, 5, 5, 5)
        container_layout.setSpacing(5)
        
        # Поле ввода текста
        self.user_entry = QTextEdit()
        self.user_entry.setMinimumHeight(24)  # Минимум как у кнопок
        self.user_entry.setMaximumHeight(80)  # Максимум для расширения
        self.user_entry.setFixedHeight(36)    # Начальная высота = 1.5 * 24
        self.user_entry.installEventFilter(self)
        self.user_entry.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: none;
                color: #dcdcdc;
                padding: 2px;
            }
            QTextEdit:focus {
                background-color: transparent;
                border: none;
            }
        """)
        
        # Подключаем автоматическое изменение размера
        self.user_entry.textChanged.connect(self._adjust_input_height)
        self.user_entry.textChanged.connect(self._update_send_button_state)
        
        # Добавляем поле ввода в сетку (занимает всю верхнюю часть)
        container_layout.addWidget(self.user_entry, 0, 0, 1, 2)
        
        # Контейнер для кнопок внизу слева БЕЗ БОРДЕРА
        button_container = QWidget()
        button_container.setFixedHeight(24)
        button_container.setStyleSheet("""
            background-color: transparent;
            border: none;
        """)
        button_layout_inner = QHBoxLayout(button_container)
        button_layout_inner.setContentsMargins(0, 0, 0, 0)
        button_layout_inner.setSpacing(4)
        
        # Кнопка прикрепить - круглая без бордера
        self.attach_button = QPushButton(qta.icon('fa6s.paperclip', color='#b0b0b0', scale_factor=0.7), '')
        self.attach_button.clicked.connect(self.attach_images)
        self.attach_button.setFixedSize(20, 20)
        self.attach_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_button.setToolTip(_("Прикрепить изображения", "Attach images"))
        self.attach_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: 0px;
                border-radius: 10px;
                padding: 3px;
            }
            QPushButton:hover {
                background-color: rgba(138, 43, 226, 0.3);
            }
            QPushButton:pressed {
                background-color: rgba(138, 43, 226, 0.5);
            }
        """)
        
        # Кнопка скриншот - круглая без бордера  
        self.send_screen_button = QPushButton(qta.icon('fa6s.camera', color='#b0b0b0', scale_factor=0.7), '')
        self.send_screen_button.clicked.connect(self.send_screen_capture)
        self.send_screen_button.setFixedSize(20, 20)
        self.send_screen_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_screen_button.setToolTip(_("Сделать скриншот экрана", "Take screenshot"))
        self.send_screen_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: 0px;
                border-radius: 10px;
                padding: 3px;
            }
            QPushButton:hover {
                background-color: rgba(138, 43, 226, 0.3);
            }
            QPushButton:pressed {
                background-color: rgba(138, 43, 226, 0.5);
            }
        """)
        
        button_layout_inner.addWidget(self.attach_button)
        button_layout_inner.addWidget(self.send_screen_button)
        button_layout_inner.addStretch()
        
        # Добавляем кнопки в левый нижний угол
        container_layout.addWidget(button_container, 1, 0)
        
        # Кнопка отправить в правом нижнем углу с иконкой
        self.send_button = QPushButton(qta.icon('fa6s.paper-plane', color='white', scale_factor=0.8), '')
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setFixedSize(28, 28)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setToolTip(_("Отправить сообщение", "Send message"))
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #8a2be2;
                border: 0px;
                border-radius: 14px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #9932CC;
            }
            QPushButton:pressed {
                background-color: #9400D3;
            }
        """)
        
        # Контейнер для кнопки отправки БЕЗ БОРДЕРА
        send_container = QWidget()
        send_container.setStyleSheet("""
            background-color: transparent;
            border: none;
        """)
        send_layout = QHBoxLayout(send_container)
        send_layout.setContentsMargins(0, 0, 0, 0)
        send_layout.addStretch()
        send_layout.addWidget(self.send_button)
        
        # Добавляем кнопку отправки в правый нижний угол
        container_layout.addWidget(send_container, 1, 1)
        
        input_layout.addWidget(input_container)

        # Скрытые элементы для совместимости (убираем их из UI)
        self.attachment_label = QLabel("")
        self.attachment_label.setVisible(False)
        self.clear_attach_btn = QPushButton("")
        self.clear_attach_btn.setVisible(False)

        layout.addWidget(input_frame)

        self._update_send_button_state()
        

    def _adjust_input_height(self):
        """Автоматически подстраивает высоту поля ввода под содержимое"""
        doc = self.user_entry.document()
        doc_height = doc.size().height()
        
        # Добавляем небольшой отступ
        new_height = int(doc_height + 10)
        
        # Ограничиваем минимальной и максимальной высотой
        new_height = max(36, min(new_height, 80))
        
        self.user_entry.setFixedHeight(new_height)

    def _update_send_button_state(self):
        """Обновляет доступность кнопки отправки в зависимости от наличия контента"""
        has_text = bool(self.user_entry.toPlainText().strip())
        has_images = bool(self.staged_image_data) or bool(getattr(self.controller, 'staged_images', []))
        
        # Проверяем также автоматические изображения если они включены
        has_auto_images = False
        if hasattr(self.controller, 'settings'):
            if self.controller.settings.get("ENABLE_SCREEN_ANALYSIS", False):
                if hasattr(self.controller, 'screen_capture_instance'):
                    frames = self.controller.screen_capture_instance.get_recent_frames(1)
                    has_auto_images = bool(frames)
            
            if self.controller.settings.get("ENABLE_CAMERA_CAPTURE", False):
                if hasattr(self.controller, 'camera_capture') and self.controller.camera_capture is not None:
                    if self.controller.camera_capture.is_running():
                        camera_frames = self.controller.camera_capture.get_recent_frames(1)
                        has_auto_images = has_auto_images or bool(camera_frames)
        
        # Кнопка активна если есть текст ИЛИ изображения
        is_enabled = has_text or has_images or has_auto_images
        
        self.send_button.setEnabled(is_enabled)
        
        # Визуально показываем состояние
        if is_enabled:
            self.send_button.setStyleSheet("""
                QPushButton {
                    background-color: #8a2be2;
                    border: 0px;
                    border-radius: 14px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #9932CC;
                }
                QPushButton:pressed {
                    background-color: #9400D3;
                }
            """)
        else:
            self.send_button.setStyleSheet("""
                QPushButton {
                    background-color: #4a4a4a;
                    border: 0px;
                    border-radius: 14px;
                    padding: 5px;
                }
                QPushButton:disabled {
                    background-color: #4a4a4a;
                    color: #666666;
                }
            """)

    def _create_scroll_to_bottom_button(self):
        btn = QPushButton(qta.icon('fa6s.angle-down', color='white'), '', self.chat_window)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setObjectName("ScrollToBottomButton")
        btn.setFixedSize(34, 34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton#ScrollToBottomButton{
                border:none;
                border-radius:17px;
                background-color:#9146ff;
            }
            QPushButton#ScrollToBottomButton:hover{
                background-color:#a96dff;
            }
            QPushButton#ScrollToBottomButton:focus{
                outline:none;
                border:none;
            }
        """)
        opacity = QGraphicsOpacityEffect(btn)
        btn.setGraphicsEffect(opacity)
        anim = QPropertyAnimation(opacity, b"opacity", btn)
        anim.setDuration(250)
        btn._opacity_anim = anim
        btn.hide()

        btn.clicked.connect(
            lambda: self.chat_window.verticalScrollBar().setValue(
                self.chat_window.verticalScrollBar().maximum())
        )

        self.scroll_to_bottom_btn   = btn
        self.scroll_to_bottom_anim  = anim

        self.chat_window.verticalScrollBar().valueChanged.connect(self._handle_chat_scroll)
        self.chat_window.viewport().installEventFilter(self)
        self._handle_chat_scroll()

    def _handle_chat_scroll(self):
        bar = self.chat_window.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 5
        if at_bottom:
            self._fade_out_scroll_button()
        else:
            self._fade_in_scroll_button()
        self._reposition_scroll_button()

    def _fade_in_scroll_button(self):
        if not self.scroll_to_bottom_btn.isVisible():
            self.scroll_to_bottom_btn.show()
        self.scroll_to_bottom_anim.stop()
        self.scroll_to_bottom_anim.setStartValue(self.scroll_to_bottom_btn.graphicsEffect().opacity())
        self.scroll_to_bottom_anim.setEndValue(1.0)
        self.scroll_to_bottom_anim.start()

    def _fade_out_scroll_button(self):
        if not self.scroll_to_bottom_btn.isVisible():
            return
        self.scroll_to_bottom_anim.stop()
        self.scroll_to_bottom_anim.setStartValue(self.scroll_to_bottom_btn.graphicsEffect().opacity())
        self.scroll_to_bottom_anim.setEndValue(0.0)
        self.scroll_to_bottom_anim.start()
        self.scroll_to_bottom_anim.finished.connect(
            lambda: self.scroll_to_bottom_btn.hide() if
            self.scroll_to_bottom_btn.graphicsEffect().opacity() == 0 else None)

    def _reposition_scroll_button(self):
        margin = 12
        vp = self.chat_window.viewport()
        x = vp.width()  - self.scroll_to_bottom_btn.width()  - margin
        y = vp.height() - self.scroll_to_bottom_btn.height() - margin
        self.scroll_to_bottom_btn.move(QPoint(x, y))

    def eventFilter(self, obj, event):
        if obj == self.chat_window.viewport() and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Paint):
            if hasattr(self, 'scroll_to_bottom_btn'):
                self._reposition_scroll_button()

        if obj == self.user_entry and event.type() == QEvent.Type.KeyPress:
            if not isinstance(event, QKeyEvent) and not hasattr(event, "key"):
                return super().eventFilter(obj, event)

            key = event.key()
            modifiers = event.modifiers()

            if key == Qt.Key.Key_V and modifiers & Qt.KeyboardModifier.ControlModifier:
                if self._clipboard_image_to_controller():
                    return True

            if key == Qt.Key.Key_Return and not (
                    modifiers & Qt.KeyboardModifier.ShiftModifier):
                self.send_message()
                return True

        if obj == self.chat_window and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._position_mita_status)

        return super().eventFilter(obj, event)

    def setup_right_frame(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setSpacing(10)
        
        status_indicators.create_status_indicators(self, settings_layout)
        language_settings.create_language_section(self, settings_layout)
        api_settings.setup_api_controls(self, settings_layout)
        g4f_settings.setup_g4f_controls(self, settings_layout)
        general_model_settings.setup_general_settings_control(self, settings_layout)
        voiceover_settings.setup_voiceover_controls(self, settings_layout)
        microphone_settings.setup_microphone_controls(self, settings_layout)
        character_settings.setup_mita_controls(self, settings_layout)
        prompt_catalogue_settings.setup_prompt_catalogue_controls(self, settings_layout)
        self.setup_debug_controls(settings_layout)
        self.setup_common_controls(settings_layout)
        gamemaster_settings.setup_game_master_controls(self, settings_layout)
        history_compressor.setup_history_compressor_controls(self, settings_layout)
        chat_settings.setup_chat_settings_controls(self, settings_layout)
        screen_analysis_settings.setup_screen_analysis_controls(self, settings_layout)
        token_settings.setup_token_settings_controls(self, settings_layout)
        command_replacer_settings.setup_command_replacer_controls(self, settings_layout)
        self.setup_news_control(settings_layout)
        
        settings_layout.addStretch()
        
        scroll_area.setWidget(settings_widget)
        layout.addWidget(scroll_area)
        
        for i in range(settings_layout.count()):
            widget = settings_layout.itemAt(i).widget()
            if isinstance(widget, CollapsibleSection):
                widget.collapse()

    def _insert_message_slot(self, role, content, insert_at_start, message_time):
        self.insert_message(role, content, insert_at_start, message_time)

    def insert_message(self, role, content, insert_at_start=False, message_time=""):
        logger.info(f"insert_message вызван. Роль: {role}, Содержимое: {str(content)[:50]}...")

        if not hasattr(self, '_images_in_chat'):
            self._images_in_chat = []

        processed_content_parts = []
        has_image_content = False

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

        processed_text_parts = []
        hide_tags = self.controller.settings.get("HIDE_CHAT_TAGS", False)

        for part in processed_content_parts:
            if part["type"] == "text":
                text_content = part["content"]
                if hide_tags:
                    text_content = process_text_to_voice(text_content)
                    processed_text_parts.append({"type": "text", "content": text_content, "tag": "default"})
                else:
                    matches = list(re.finditer(r'(<([^>]+)>)(.*?)(</\2>)|(<([^>]+)>)', text_content))
                    last_end = 0
                    if not matches:
                        processed_text_parts.append({"type": "text", "content": text_content, "tag": "default"})
                    else:
                        for match in matches:
                            start, end = match.span()
                            if start > last_end:
                                processed_text_parts.append(
                                    {"type": "text", "content": text_content[last_end:start], "tag": "default"})

                            if match.group(1) is not None:
                                processed_text_parts.append(
                                    {"type": "text", "content": match.group(1), "tag": "tag_green"})
                                processed_text_parts.append(
                                    {"type": "text", "content": match.group(3), "tag": "default"})
                                processed_text_parts.append(
                                    {"type": "text", "content": match.group(4), "tag": "tag_green"})
                            elif match.group(5) is not None:
                                processed_text_parts.append({"type": "text", "content": match.group(5), "tag": "tag_green"})

                            last_end = end

                        if last_end < len(text_content):
                            processed_text_parts.append(
                                {"type": "text", "content": text_content[last_end:], "tag": "default"})
            else:
                processed_text_parts.append(part)

        cursor = self.chat_window.textCursor()

        show_timestamps = self.controller.settings.get("SHOW_CHAT_TIMESTAMPS", False)
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

        if show_timestamps:
            self._insert_formatted_text(cursor, timestamp_str, QColor("#888888"), italic=True)

        self.insert_speaker_name(cursor, role)

        for part in processed_text_parts:
            if part["type"] == "text":
                color = None
                if part["tag"] == "tag_green":
                    color = QColor("#00FF00")
                self._insert_formatted_text(cursor, part["content"], color)
            elif part["type"] == "image":
                cursor.insertImage(part["content"])
                cursor.insertText("\n")

        self.insert_message_end(cursor, role)

        if not insert_at_start:
            self.chat_window.verticalScrollBar().setValue(
                self.chat_window.verticalScrollBar().maximum()
            )

    def insert_message_end(self, cursor = None, role = "assistant"):
        if not cursor:
            cursor = self.chat_window.textCursor()

        if role == "user":
            cursor.insertText("\n")
        elif role in {"assistant", "system"}:
            cursor.insertText("\n\n")

    def insert_speaker_name(self, cursor = None, role = "assistant"):
        if not cursor:
            cursor = self.chat_window.textCursor()
        if role == "user":
            self._insert_formatted_text(cursor, _("Вы: ", "You: "), QColor("gold"), bold=True)
        elif role == "assistant":
            self._insert_formatted_text(cursor, f"{self.controller.model.current_character.name}: ", QColor("hot pink"), bold=True)

    def _insert_formatted_text(self, cursor, text, color=None, bold=False, italic=False):
        char_format = QTextCharFormat()
        
        if color:
            char_format.setForeground(color)
        else:
            default_text_color = self.chat_window.palette().color(QPalette.ColorRole.Text)
            char_format.setForeground(default_text_color)
        
        font = QFont("Arial", int(self.controller.settings.get("CHAT_FONT_SIZE", 12)))
        if bold:
            font.setBold(True)
        if italic:
            font.setItalic(True)
        
        char_format.setFont(font)
        cursor.insertText(text, char_format)

    def append_message(self, text):
        cursor = self.chat_window.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._insert_formatted_text(cursor,text)
        self.chat_window.verticalScrollBar().setValue(
            self.chat_window.verticalScrollBar().maximum()
        )

    def _prepare_stream_slot(self):
        self.insert_speaker_name(role="assistant")

    def _append_stream_chunk_slot(self, chunk):
        self.append_message(chunk)

    def _finish_stream_slot(self):
        self.insert_message_end(role="assistant")

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
            
            max_width = 400
            max_height = 300
            original_width, original_height = image.size
            
            if original_width > max_width or original_height > max_height:
                ratio = min(max_width / original_width, max_height / original_height)
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
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

    def trigger_g4f_reinstall_schedule(self):
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
            self.controller.settings.set("G4F_TARGET_VERSION", target_version)
            self.controller.settings.set("G4F_UPDATE_PENDING", True)
            self.controller.settings.set("G4F_VERSION", target_version)
            self.controller.settings.save_settings()
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

    def update_status_colors(self):
        self.game_connected_checkbox_var = self.controller.ConnectedToGame
        
        if hasattr(self, 'game_status_checkbox'):
            self.game_status_checkbox.setChecked(self.controller.ConnectedToGame)
            
        if hasattr(self, 'silero_status_checkbox'):
            self.silero_status_checkbox.setChecked(self.controller.silero_connected)
            
        if hasattr(self, 'mic_status_checkbox'):
            self.mic_status_checkbox.setChecked(self.controller.mic_recognition_active)
            
        if hasattr(self, 'screen_capture_status_checkbox'):
            self.screen_capture_status_checkbox.setChecked(self.controller.screen_capture_active)
            
        if hasattr(self, 'camera_capture_status_checkbox'):
            self.camera_capture_status_checkbox.setChecked(self.controller.camera_capture_active)

    def load_chat_history(self):
        self.clear_chat_display()
        self.controller.loaded_messages_offset = 0
        self.controller.total_messages_in_history = 0
        self.controller.loading_more_history = False

        chat_history = self.controller.model.current_character.load_history()
        all_messages = chat_history["messages"]
        self.controller.total_messages_in_history = len(all_messages)
        logger.info(f"[{time.strftime('%H:%M:%S')}] Всего сообщений в истории: {self.controller.total_messages_in_history}")

        max_display_messages = int(self.controller.settings.get("MAX_CHAT_HISTORY_DISPLAY", 100))
        start_index = max(0, self.controller.total_messages_in_history - max_display_messages)
        messages_to_load = all_messages[start_index:]

        for entry in messages_to_load:
            role = entry["role"]
            content = entry["content"]
            message_time = entry.get("time", "???")
            self.insert_message(role, content, message_time=message_time)

        self.controller.loaded_messages_offset = len(messages_to_load)
        logger.info(f"[{time.strftime('%H:%M:%S')}] Загружено {self.controller.loaded_messages_offset} последних сообщений.")

        self.update_debug_info()
        
        self.chat_window.verticalScrollBar().setValue(
            self.chat_window.verticalScrollBar().maximum()
        )

    def setup_debug_controls(self, parent_layout):
        section = CollapsibleSection(_("Отладка", "Debug"), parent_layout.widget())
        
        self.debug_window = QTextEdit()
        self.debug_window.setReadOnly(True)
        self.debug_window.setObjectName("DebugWindow")
        
        section.content_layout.addWidget(self.debug_window)
        parent_layout.addWidget(section)
        
        self.update_debug_info()

    def setup_common_controls(self, parent_layout):
        common_config = [
            {'label': _('Скрывать (приватные) данные', 'Hide (private) data'), 'key': 'HIDE_PRIVATE',
             'type': 'checkbutton', 'default_checkbutton': True},
        ]
        self.create_settings_section(parent_layout, _("Общие настройки", "Common settings"), common_config)

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

    def update_debug_info(self):
        if hasattr(self, 'debug_window') and self.debug_window:
            self.debug_window.clear()
            debug_info = self.controller.model.current_character.current_variables_string()
            self.debug_window.insertPlainText(debug_info)

    def update_token_count(self, event=None):
        show_token_info = self.controller.settings.get("SHOW_TOKEN_INFO", True)

        if show_token_info and self.controller.model.hasTokenizer:
            current_context_tokens = self.controller.model.get_current_context_token_count()

            token_cost_input = float(self.controller.settings.get("TOKEN_COST_INPUT", 0.000001))
            token_cost_output = float(self.controller.settings.get("TOKEN_COST_OUTPUT", 0.000002))
            max_model_tokens = int(self.controller.settings.get("MAX_MODEL_TOKENS", 32000))

            self.controller.model.token_cost_input = token_cost_input
            self.controller.model.token_cost_output = token_cost_output
            self.controller.model.max_model_tokens = max_model_tokens

            cost = self.controller.model.calculate_cost_for_current_context()

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

    def update_chat_font_size(self, font_size):
        base_font = QFont("Arial", font_size)
        self.chat_window.setFont(base_font)

    def clear_chat_display(self):
        self.chat_window.clear()

    def send_message(self, system_input: str = "", image_data: list[bytes] = None):
        user_input = self.user_entry.toPlainText().strip()
        current_image_data = []
        staged_image_data = []

        if self.controller.staged_images:
            try:
                for image_path in self.controller.staged_images:
                    with open(image_path, "rb") as f:
                        staged_image_data.append(f.read())
                logger.info(f"Загружено {len(staged_image_data)} байт-кодов из прикрепленных изображений.")
            except Exception as e:
                logger.error(f"Ошибка чтения прикрепленного файла: {e}")
                QMessageBox.critical(self, _("Ошибка файла", "File Error"),
                                    _("Не удалось прочитать один из прикрепленных файлов.",
                                    "Could not read one of the attached files."))
                return

        if self.controller.settings.get("ENABLE_SCREEN_ANALYSIS", False):
            history_limit = int(self.controller.settings.get("SCREEN_CAPTURE_HISTORY_LIMIT", 1))
            frames = self.controller.screen_capture_instance.get_recent_frames(history_limit)
            if frames:
                current_image_data.extend(frames)
            else:
                logger.info("Анализ экрана включен, но кадры не готовы или история пуста.")

        all_image_data = (image_data or []) + current_image_data + staged_image_data

        if self.controller.settings.get("ENABLE_CAMERA_CAPTURE", False):
            if hasattr(self.controller, 'camera_capture') and self.controller.camera_capture is not None and self.controller.camera_capture.is_running():
                history_limit = int(self.controller.settings.get("CAMERA_CAPTURE_HISTORY_LIMIT", 1))
                camera_frames = self.controller.camera_capture.get_recent_frames(history_limit)
                if camera_frames:
                    all_image_data.extend(camera_frames)
                    logger.info(f"Добавлено {len(camera_frames)} кадров с камеры для отправки.")
                else:
                    logger.info("Захват с камеры включен, но кадры не готовы или история пуста.")

        if not user_input and not system_input and not all_image_data:
            return
        
        self.controller.last_image_request_time = time.time()

        if user_input:
            self.insert_message("user", user_input)
            self.user_entry.clear()

        if all_image_data:
            image_content_for_display = [{"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{base64.b64encode(img).decode('utf-8')}"}} for img in all_image_data]

            if not user_input:
                label = _("<Изображения>", "<Images>")
                if staged_image_data and not current_image_data and not (image_data or []):
                    label = _("<Прикрепленные изображения>", "<Attached Images>")
                elif (current_image_data or (image_data or [])) and not staged_image_data:
                    label = _("<Изображение экрана>", "<Screen Image>")

                image_content_for_display.insert(0, {"type": "text", "content": label + "\n"})

            self.insert_message("user", image_content_for_display)

        if self.controller.loop and self.controller.loop.is_running():
            import asyncio
            asyncio.run_coroutine_threadsafe(self.controller.async_send_message(user_input, system_input, all_image_data),
                                            self.controller.loop)

        if self.controller.staged_images:
            self.controller.staged_images.clear()
            logger.info("Список прикрепленных изображений очищен.")
            
            # Очищаем превью
            self.staged_image_data.clear()
            if self.image_preview_bar:
                self.image_preview_bar.clear()
                self._hide_image_preview_bar()



    def load_more_history(self):
        if self.controller.loaded_messages_offset >= self.controller.total_messages_in_history:
            return

        self.controller.loading_more_history = True
        try:
            chat_history = self.controller.model.current_character.load_history()
            all_messages = chat_history["messages"]

            end_index = self.controller.total_messages_in_history - self.controller.loaded_messages_offset
            start_index = max(0, end_index - self.controller.lazy_load_batch_size)
            messages_to_prepend = all_messages[start_index:end_index]

            if not messages_to_prepend:
                self.controller.loading_more_history = False
                return

            scrollbar = self.chat_window.verticalScrollBar()
            old_value = scrollbar.value()
            old_max = scrollbar.maximum()

            for entry in reversed(messages_to_prepend):
                role = entry["role"]
                content = entry["content"]
                message_time = entry.get("time", "???")
                self.insert_message(role, content, insert_at_start=True, message_time=message_time)

            QTimer.singleShot(0, lambda: scrollbar.setValue(scrollbar.maximum() - old_max + old_value))

            self.controller.loaded_messages_offset += len(messages_to_prepend)
            logger.info(f"Загружено еще {len(messages_to_prepend)} сообщений. Всего загружено: {self.controller.loaded_messages_offset}")

        finally:
            self.controller.loading_more_history = False

    def create_settings_section(self, parent_layout, title, settings_config, icon_name=None):
        return gui_templates.create_settings_section(self, parent_layout, title, settings_config, icon_name=icon_name)

    def create_setting_widget(self, parent, label, setting_key='', widget_type='entry',
                              options=None, default='', default_checkbutton=False, validation=None, tooltip=None,
                              width=None, height=None, command=None, hide=False):
        return gui_templates.create_setting_widget(self, parent, label, setting_key, widget_type,
                                                  options, default, default_checkbutton, validation, tooltip,
                                                  width, height, command, hide)

    def _save_setting(self, key, value):
        self.controller.settings.set(key, value)
        self.controller.settings.save_settings()
        self.controller.all_settings_actions(key, value)

    def get_news_content(self):
        try:
            import requests
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
        self.controller.stop_screen_capture_thread()
        self.controller.stop_camera_capture_thread()
        self.controller.delete_all_sound_files()
        self.controller.stop_server()
        logger.info("Закрываемся")
        event.accept()

    def close_app(self):
        logger.info("Завершение программы...")
        self.close()

    def on_local_voice_selected(self, event=None):
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

        if selected_model_id in ["medium+", "medium+low"] and self.controller.local_voice.first_compiled == False:
            reply = QMessageBox.question(self, _("Внимание", "Warning"),
                _("Невозможно перекомпилировать модель Fish Speech в Fish Speech+ - требуется перезапуск программы. \n\n Перезапустить?",
                  "Cannot recompile Fish Speech model to Fish Speech+ - program restart required. \n\n Restart?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                
            if reply != QMessageBox.StandardButton.Yes:
                if self.controller.last_voice_model_selected:
                    self.local_voice_combobox.setCurrentText(self.controller.last_voice_model_selected["name"])
                else:
                    self.local_voice_combobox.setCurrentText('')
                    self.controller.settings.set("NM_CURRENT_VOICEOVER", None)
                    self.controller.settings.save_settings()
                self.update_local_model_status_indicator()
                return
            else:
                import sys, subprocess
                python = sys.executable
                script = os.path.abspath(sys.argv[0])
                subprocess.Popen([python, script] + sys.argv[1:])
                self.close()
                return

        self.controller.settings.set("NM_CURRENT_VOICEOVER", selected_model_id)
        self.controller.settings.save_settings()
        self.controller.current_local_voice_id = selected_model_id

        self.update_local_model_status_indicator()
        if not self.controller.local_voice.is_model_initialized(selected_model_id):
            self.show_model_loading_window(selected_model)
        else:
            try:
                self.controller.local_voice.select_model(selected_model_id)
            except Exception as e:
                logger.error(f'Не удалось активировать модель {selected_model_id}: {e}')
                QMessageBox.critical(self, 'Ошибка', f'Не удалось активировать модель\n{e}')
                return

            self.controller.settings.set("NM_CURRENT_VOICEOVER", selected_model_id)
            self.controller.settings.save_settings()

            self.controller.current_local_voice_id   = selected_model_id
            self.controller.last_voice_model_selected = selected_model
            self.update_local_model_status_indicator()
            self.update_local_voice_combobox()
            logger.info(f"Переключился на уже инициализированную модель «{selected_model_id}»")
            return

    def show_model_loading_window(self, model):
        model_id = model["id"]
        model_name = model["name"]

        if not os.path.exists('models'):
            logger.warning(f"Файлы моделей для '{model_name}' не готовы (загрузка не удалась или отменена).")
            QMessageBox.critical(self, _("Ошибка", "Error"),
               _("Не найдена папка Models. Инициализация отменена.",
               "Failed to find Models folder. Initialization cancelled."))
            return

        logger.info(f"Модели для '{model_name}' готовы. Запуск инициализации...")

        self.loading_dialog = QDialog(self)
        self.loading_dialog.setWindowTitle(_("Загрузка модели", "Loading model") + f" {model_name}")
        self.loading_dialog.setFixedSize(400, 300)
        self.loading_dialog.setModal(True)
        
        layout = QVBoxLayout(self.loading_dialog)
        
        title_label = QLabel(_("Инициализация модели", "Initializing model") + f" {model_name}")
        title_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        wait_label = QLabel(_("Пожалуйста, подождите...", "Please wait..."))
        wait_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(wait_label)
        
        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 0)
        layout.addWidget(self.loading_progress)
        
        self.loading_status_label = QLabel(_("Инициализация...", "Initializing..."))
        self.loading_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.loading_status_label)
        
        cancel_button = QPushButton(_("Отменить", "Cancel"))
        cancel_button.clicked.connect(lambda: self.cancel_model_loading(self.loading_dialog))
        layout.addWidget(cancel_button, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.controller.model_loading_cancelled = False
        
        import threading
        loading_thread = threading.Thread(
            target=self.controller.init_model_thread,
            args=(model_id, self.loading_dialog, self.loading_status_label, self.loading_progress),
            daemon=True
        )
        loading_thread.start()
        
        self.loading_dialog.show()

    def cancel_model_loading(self, loading_window):
        logger.info("Загрузка модели отменена пользователем.")
        self.controller.model_loading_cancelled = True
        if loading_window:
            loading_window.close()

        restored_model_id = None
        if self.controller.last_voice_model_selected:
            if hasattr(self, 'local_voice_combobox'):
                self.local_voice_combobox.setCurrentText(self.controller.last_voice_model_selected["name"])
            restored_model_id = self.controller.last_voice_model_selected["id"]
            self.controller.settings.set("NM_CURRENT_VOICEOVER", restored_model_id)
            self.controller.current_local_voice_id = restored_model_id
        else:
            if hasattr(self, 'local_voice_combobox'):
                self.local_voice_combobox.setCurrentText('')
            self.controller.settings.set("NM_CURRENT_VOICEOVER", None)
            self.controller.current_local_voice_id = None

        self.controller.settings.save_settings()
        self.update_local_model_status_indicator()

    def finish_model_loading(self, model_id, loading_window):
        logger.info(f"Модель {model_id} успешно инициализирована.")
        if loading_window:
            loading_window.close()

        try:
            self.controller.local_voice.select_model(model_id)
        except Exception as e:
            logger.error(f"Не удалось активировать модель {model_id}: {e}")
            QMessageBox.critical(self, "Ошибка",
                                f"Не удалось активировать модель {model_id}.\n{e}")
            return

        self.controller.last_voice_model_selected = None
        for model in LOCAL_VOICE_MODELS:
            if model["id"] == model_id:
                self.controller.last_voice_model_selected = model
                break

        self.controller.settings.set("NM_CURRENT_VOICEOVER", model_id)
        self.controller.settings.save_settings()
        self.controller.current_local_voice_id = model_id

        QMessageBox.information(self, _("Успешно", "Success"),
            _("Модель {} успешно инициализирована!", "Model {} initialized successfully!").format(model_id))
        
        self.update_local_voice_combobox()

    def initialize_last_local_model_on_startup(self):
        if self.controller.settings.get("LOCAL_VOICE_LOAD_LAST", False):
            logger.info("Проверка автозагрузки последней локальной модели...")
            last_model_id = self.controller.settings.get("NM_CURRENT_VOICEOVER", None)

            if last_model_id:
                logger.info(f"Найдена последняя модель для автозагрузки: {last_model_id}")
                model_to_load = None
                for model in LOCAL_VOICE_MODELS:
                    if model["id"] == last_model_id:
                        model_to_load = model
                        break

                if model_to_load:
                    if self.controller.local_voice.is_model_installed(last_model_id):
                        if not self.controller.local_voice.is_model_initialized(last_model_id):
                            logger.info(f"Модель {last_model_id} установлена, но не инициализирована. Запуск инициализации...")
                            self.show_model_loading_window(model_to_load)
                        else:
                            logger.info(f"Модель {last_model_id} уже инициализирована.")
                            self.controller.last_voice_model_selected = model_to_load
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
            current_model_id_combo = self.controller.settings.get("NM_CURRENT_VOICEOVER", None)

            if current_model_id_combo:
                model_installed_combo = self.controller.local_voice.is_model_installed(current_model_id_combo)
                if model_installed_combo:
                    if not self.controller.local_voice.is_model_initialized(current_model_id_combo):
                        show_combobox_indicator = True
                else:
                    show_combobox_indicator = True

            self.local_model_status_label.setVisible(show_combobox_indicator)

        show_section_warning = False
        if (hasattr(self, 'voiceover_section_warning_label') and 
                self.voiceover_section_warning_label and
                hasattr(self, 'voiceover_section') and 
                self.voiceover_section):

            voiceover_method = self.controller.settings.get("VOICEOVER_METHOD", "TG")
            current_model_id_section = self.controller.settings.get("NM_CURRENT_VOICEOVER", None)

            if voiceover_method == "Local" and current_model_id_section:
                model_installed_section = self.controller.local_voice.is_model_installed(current_model_id_section)
                if model_installed_section:
                    if not self.controller.local_voice.is_model_initialized(current_model_id_section):
                        show_section_warning = True
                else:
                    show_section_warning = True

            if hasattr(self.voiceover_section, 'warning_label'):
                self.voiceover_section.warning_label.setVisible(show_section_warning)

    def switch_voiceover_settings(self, selected_method: str | None = None) -> None:
        if selected_method is not None:
            self._save_setting("VOICEOVER_METHOD", selected_method)

        use_voice        = bool(self.controller.settings.get("SILERO_USE",  True))
        current_method   =      self.controller.settings.get("VOICEOVER_METHOD", "TG")

        if not hasattr(self, "voiceover_section"):
            logger.error("Отсутствует voiceover_section – переключать нечего.")
            return

        method_row_widget  = getattr(self, "method_frame", None)
        tg_group_widget    = getattr(self, "tg_settings_frame", None)
        local_group_widget = getattr(self, "local_settings_frame", None)

        def set_row_visible(widget: QWidget | None, visible: bool):
            if widget is None:
                return
            widget.setVisible(visible)
            parent = widget.parentWidget()
            if parent is not None and parent != self.voiceover_section.content_frame:
                parent.setVisible(visible)

        set_row_visible(method_row_widget,  False)
        if tg_group_widget:
            tg_group_widget.setVisible(False)
        if local_group_widget:
            local_group_widget.setVisible(False)

        if not use_voice:
            return

        set_row_visible(method_row_widget, True)

        if current_method == "TG":
            if tg_group_widget:
                tg_group_widget.setVisible(True)

        elif current_method == "Local":
            if local_group_widget:
                local_group_widget.setVisible(True)
                self.update_local_voice_combobox()
                self.update_local_model_status_indicator()

        self.controller.voiceover_method = current_method
        self.check_triton_dependencies()

    def update_local_voice_combobox(self):
        if not hasattr(self, 'local_voice_combobox') or self.local_voice_combobox is None:
            logger.info(self.local_voice_combobox)
            logger.warning("update_local_voice_combobox: виджет local_voice_combobox не найден.")
            return

        self.local_voice_combobox.blockSignals(True)

        try:
            installed_models_names = [model["name"] for model in LOCAL_VOICE_MODELS if
                                      self.controller.local_voice.is_model_installed(model["id"])]
            logger.info(f'Доступные модели: {installed_models_names}')

            current_items = [self.local_voice_combobox.itemText(i) for i in range(self.local_voice_combobox.count())]

            if installed_models_names != current_items:
                self.local_voice_combobox.clear()
                self.local_voice_combobox.addItems(installed_models_names)
                logger.info(f"Обновлен список локальных моделей: {installed_models_names}")

            current_model_id = self.controller.settings.get("NM_CURRENT_VOICEOVER", None)
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
                            if self.controller.settings.get("NM_CURRENT_VOICEOVER") != model["id"]:
                                self.controller.settings.set("NM_CURRENT_VOICEOVER", model["id"])
                                self.controller.settings.save_settings()
                                self.controller.current_local_voice_id = model["id"]
                            break
            else:
                if self.local_voice_combobox.currentText() != '':
                    self.local_voice_combobox.setCurrentText('')
                if self.controller.settings.get("NM_CURRENT_VOICEOVER") is not None:
                    self.controller.settings.set("NM_CURRENT_VOICEOVER", None)
                    self.controller.settings.save_settings()
                    self.controller.current_local_voice_id = None
        finally:
            self.local_voice_combobox.blockSignals(False)

        self.update_local_model_status_indicator()
        self.check_triton_dependencies()

    def check_triton_dependencies(self):
        if hasattr(self, 'triton_warning_label') and self.triton_warning_label:
            self.triton_warning_label.deleteLater()
            delattr(self, 'triton_warning_label')

        if self.controller.settings.get("VOICEOVER_METHOD") != "Local":
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
        try:
            import os

            config_dir = "Settings"
            os.makedirs(config_dir, exist_ok=True)

            def on_save_callback(settings_data):
                installed_models_ids = settings_data.get("installed_models", [])
                logger.info(f"Сохранены установленные модели (из окна установки): {installed_models_ids}")

                self.controller.refresh_local_voice_modules()
                self.update_local_voice_combobox()

                current_model_id = self.controller.settings.get("NM_CURRENT_VOICEOVER", None)
                if current_model_id and current_model_id not in installed_models_ids:
                    logger.warning(f"Текущая модель {current_model_id} была удалена. Сбрасываем выбор.")
                    new_model_id = installed_models_ids[0] if installed_models_ids else None
                    self.controller.settings.set("NM_CURRENT_VOICEOVER", new_model_id)
                    self.controller.settings.save_settings()
                    self.controller.current_local_voice_id = new_model_id
                    self.update_local_voice_combobox()

            from PyQt6.QtWidgets import QDialog
            install_dialog = QDialog(self)
            install_dialog.setWindowTitle(_("Управление локальными моделями", "Manage Local Models"))
            install_dialog.setModal(False)
            install_dialog.resize(875, 800)
            
            dialog_layout = QVBoxLayout(install_dialog)
            dialog_layout.setContentsMargins(0, 0, 0, 0)
            
            # Создаем Controller, который создаст View внутри
            controller = VoiceModelController(
                view_parent=install_dialog,
                config_dir=config_dir,
                on_save_callback=on_save_callback,
                local_voice=self.controller.local_voice,
                check_installed_func=self.controller.check_module_installed,
            )
            
            # View уже добавлен в layout внутри Controller
            install_dialog.show()
            
        except ImportError:
            logger.error("Не найден модуль voice_model_controller.py. Установка моделей недоступна.")
            QMessageBox.critical(self, _("Ошибка", "Error"),
                _("Не найден файл voice_model_controller.py", "voice_model_controller.py not found."))
        except Exception as e:
            logger.error(f"Ошибка при открытии окна установки моделей: {e}", exc_info=True)
            QMessageBox.critical(self, _("Ошибка", "Error"), 
                _("Не удалось открыть окно установки моделей.", "Failed to open model installation window."))

    def _show_ffmpeg_installing_popup(self):
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
        if hasattr(self, 'ffmpeg_install_popup') and self.ffmpeg_install_popup:
            self.ffmpeg_install_popup.close()
            self.ffmpeg_install_popup = None

    def _show_ffmpeg_error_popup(self):
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

    def on_voice_language_selected(self, event=None):
        if not hasattr(self, 'voice_language_var'):
            logger.warning("Переменная voice_language_var не найдена.")
            return

        selected_language = self.voice_language_var.currentText() if hasattr(self.voice_language_var, 'currentText') else self.voice_language_var
        logger.info(f"Выбран язык озвучки: {selected_language}")

        self._save_setting("VOICE_LANGUAGE", selected_language)

        if hasattr(self.controller.local_voice, 'change_voice_language'):
            try:
                self.controller.local_voice.change_voice_language(selected_language)
                logger.info(f"Язык в LocalVoice успешно изменен на {selected_language}.")
                self.update_local_model_status_indicator()
            except Exception as e:
                logger.error(f"Ошибка при вызове local_voice.change_voice_language: {e}")
        else:
            logger.warning("Метод 'change_voice_language' отсутствует в объекте local_voice.")

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
        MitaName = self.controller.model.current_character.name
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

    # region изображения
    def attach_images(self):
        """Обновленный метод прикрепления изображений"""
        file_paths, t = QFileDialog.getOpenFileNames(
            self,
            _("Выберите изображения", "Select Images"),
            "",
            _("Файлы изображений (*.png *.jpg *.jpeg *.bmp *.gif)", "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)")
        )

        if file_paths:
            self.controller.staged_images.extend(file_paths)
            
            # Добавляем превью
            for file_path in file_paths:
                try:
                    with open(file_path, "rb") as f:
                        img_data = f.read()
                        self.staged_image_data.append(img_data)
                        
                        # Показываем превью
                        self._show_image_preview_bar()
                        self.image_preview_bar.add_image(img_data)
                except Exception as e:
                    logger.error(f"Ошибка чтения файла {file_path}: {e}")
            
            logger.info(f"Прикреплены изображения: {self.controller.staged_images}")
            # Обновляем состояние кнопки отправки
            self._update_send_button_state()



    def send_screen_capture(self):
        """Обновленный метод отправки скриншота"""
        logger.info("Запрошена отправка скриншота.")
        frames = self.controller.screen_capture_instance.get_recent_frames(1)

        if not frames:
            QMessageBox.warning(self, _("Ошибка", "Error"),
                                _("Не удалось захватить экран. Убедитесь, что анализ экрана включен в настройках.",
                                "Failed to capture the screen. Make sure screen analysis is enabled in settings."))
            return

        # Добавляем в staged для превью
        for frame_data in frames:
            self.staged_image_data.append(frame_data)
            self.controller.stage_image_bytes(frame_data)
        
        # Показываем превью
        self._show_image_preview_bar()
        for frame_data in frames:
            self.image_preview_bar.add_image(frame_data)
        
        # Обновляем состояние кнопки отправки
        self._update_send_button_state()

    def _clear_staged_images(self):
        self.controller.clear_staged_images()
        
        # Очищаем превью
        self.staged_image_data.clear()
        if self.image_preview_bar:
            self.image_preview_bar.clear()
            self._hide_image_preview_bar()
        
        # Обновляем состояние кнопки отправки
        self._update_send_button_state()

    # Обновите метод _clipboard_image_to_controller:
    def _clipboard_image_to_controller(self) -> bool:
        """
        Если в буфере обмена есть изображение – передаёт его байты
        контроллеру и обновляет UI. Возвращает True, если картинка
        была обработана.
        """
        cb = QApplication.clipboard()
        if not cb.mimeData().hasImage():
            return False

        qimg = cb.image()
        if qimg.isNull():
            return False

        # QImage → bytes (PNG)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buf, "PNG")
        img_bytes = buf.data().data()

        # Сохраняем данные для превью
        self.staged_image_data.append(img_bytes)
        
        # Делегируем бизнес-логику контроллеру
        self.controller.stage_image_bytes(img_bytes)

        # Показываем превью
        self._show_image_preview_bar()
        self.image_preview_bar.add_image(img_bytes)
        
        # Обновляем состояние кнопки отправки
        self._update_send_button_state()
        
        return True


    def _init_image_preview(self):
        """Инициализация системы превью изображений"""
        self.staged_image_data = []  # Храним данные изображений
        
    def _show_image_preview_bar(self):
        """Показать панель превью изображений"""
        if not self.image_preview_bar:
            # Находим input_frame (основной фрейм с токенами и полем ввода)
            # НЕ input_container, а именно input_frame
            input_frame = None
            
            # Ищем input_frame через иерархию виджетов
            widget = self.user_entry
            while widget:
                if isinstance(widget, QFrame) and widget.objectName() != "":
                    break
                if hasattr(widget, 'layout') and widget.layout():
                    # Проверяем, есть ли token_count_label среди дочерних виджетов
                    for i in range(widget.layout().count()):
                        item = widget.layout().itemAt(i)
                        if item and item.widget() == self.token_count_label:
                            input_frame = widget
                            break
                if input_frame:
                    break
                widget = widget.parent()
            
            # Если не нашли по иерархии, используем прямую ссылку
            if not input_frame:
                # input_frame - это родитель token_count_label
                input_frame = self.token_count_label.parent()
            
            if input_frame:
                # Создаем панель превью
                self.image_preview_bar = ImagePreviewBar(input_frame)
                self.image_preview_bar.thumbnail_clicked.connect(self._show_full_image)
                self.image_preview_bar.remove_requested.connect(self._remove_staged_image)
                
                # Вставляем между token_count_label (индекс 0) и input_row_layout (индекс 1)
                # Поэтому вставляем на позицию 1
                input_frame.layout().insertWidget(1, self.image_preview_bar)
        
        self.image_preview_bar.show()

    def _remove_staged_image(self, index):
        """Удалить изображение из списка прикрепленных"""
        if 0 <= index < len(self.staged_image_data):
            # Удаляем из данных
            self.staged_image_data.pop(index)
            
            # Удаляем из контроллера
            if 0 <= index < len(self.controller.staged_images):
                self.controller.staged_images.pop(index)
            
            # Удаляем превью
            self.image_preview_bar.remove_at(index)
            
            # Если больше нет изображений, скрываем панель превью
            if len(self.staged_image_data) == 0:
                self._hide_image_preview_bar()
            
            # Обновляем состояние кнопки отправки
            self._update_send_button_state()

    def _hide_image_preview_bar(self):
        """Скрыть панель превью"""
        if self.image_preview_bar:
            self.image_preview_bar.hide()
            
    def _show_full_image(self, image_data):
        """Показать полноразмерное изображение в overlay"""
        try:
            # Конвертируем данные в QPixmap
            if isinstance(image_data, str) and image_data.startswith("data:image"):
                base64_data = image_data.split(",")[1]
                img_bytes = base64.b64decode(base64_data)
            elif isinstance(image_data, bytes):
                img_bytes = image_data
            else:
                return
                
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes)
            
            # Создаем виджет просмотра
            viewer = ImageViewerWidget(pixmap)
            viewer.close_requested.connect(self.overlay.hide_animated)
            
            # Устанавливаем контент и показываем
            self.overlay.set_content(viewer)
            self.overlay.show_animated()
            
        except Exception as e:
            logger.error(f"Ошибка при показе изображения: {e}")
            
    def resizeEvent(self, event):
        """Обработка изменения размера окна"""
        super().resizeEvent(event)
        # Подгоняем размер overlay
        self.overlay.resize(self.size())
        # Репозиционируем статус Миты
        QTimer.singleShot(0, self._position_mita_status)

    # endregion

    def prompt_for_code(self, code_future):
        dialog = QDialog(self)
        dialog.setWindowTitle("Подтверждение Telegram")
        dialog.setFixedSize(300, 150)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dialog)
        label = QLabel("Введите код подтверждения:")
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(label)

        code_entry = QLineEdit()
        code_entry.setMaxLength(10)
        code_entry.setFocus()
        layout.addWidget(code_entry)

        def submit_code():
            code = code_entry.text().strip()
            if code:
                if self.controller.loop and self.controller.loop.is_running():
                    self.controller.loop.call_soon_threadsafe(code_future.set_result, code)
                dialog.accept()
            else:
                QMessageBox.critical(dialog, "Ошибка", "Введите код подтверждения")
        
        def on_reject():
            if self.controller.loop and self.controller.loop.is_running() and not code_future.done():
                import asyncio
                self.controller.loop.call_soon_threadsafe(code_future.set_exception, asyncio.CancelledError("Ввод кода отменен"))

        btn = QPushButton("Подтвердить")
        btn.clicked.connect(submit_code)
        layout.addWidget(btn)
        code_entry.returnPressed.connect(submit_code)
        
        dialog.rejected.connect(on_reject)
        dialog.exec()

    def prompt_for_password(self, password_future):
        dialog = QDialog(self)
        dialog.setWindowTitle("Двухфакторная аутентификация")
        dialog.setFixedSize(300, 150)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dialog)
        label = QLabel("Введите пароль:")
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(label)

        password_entry = QLineEdit()
        password_entry.setEchoMode(QLineEdit.EchoMode.Password)
        password_entry.setFocus()
        layout.addWidget(password_entry)

        def submit_password():
            pwd = password_entry.text().strip()
            if pwd:
                if self.controller.loop and self.controller.loop.is_running():
                    self.controller.loop.call_soon_threadsafe(password_future.set_result, pwd)
                dialog.accept()
            else:
                QMessageBox.critical(dialog, "Ошибка", "Введите пароль")
                
        def on_reject():
            if self.controller.loop and self.controller.loop.is_running() and not password_future.done():
                import asyncio
                self.controller.loop.call_soon_threadsafe(password_future.set_exception, asyncio.CancelledError("Ввод пароля отменен"))

        btn = QPushButton("Подтвердить")
        btn.clicked.connect(submit_password)
        layout.addWidget(btn)
        password_entry.returnPressed.connect(submit_password)
        
        dialog.rejected.connect(on_reject)
        dialog.exec()

    # region свойства для делегирования

    @property
    def settings(self):
        """Делегирует доступ к настройкам контроллера"""
        if self.controller:
            return self.controller.settings
        # Fallback для случая, когда контроллер еще не создан
        from settings_manager import SettingsManager
        return SettingsManager("Settings/settings.json")

    @property
    def model(self):
        """Делегирует доступ к модели контроллера"""
        if self.controller:
            return self.controller.model
        return None

    @property
    def loop(self):
        """Делегирует доступ к циклу событий контроллера"""
        if self.controller:
            return self.controller.loop
        return None

    
    # endregion

    def _save_setting(self, key, value):
        """Делегирует сохранение настроек контроллеру"""
        if self.controller:
            self.controller.settings.set(key, value)
            self.controller.settings.save_settings()
            self.controller.all_settings_actions(key, value)
    
    # region митастатус
    def _position_mita_status(self):
        """Позиционировать статус Миты внизу чата"""
        if not hasattr(self, 'mita_status') or not self.mita_status:
            return
            
        # Размеры чата
        chat_width = self.chat_window.width()
        chat_height = self.chat_window.height()
        
        # Размеры статуса
        status_width = min(300, chat_width - 20)
        status_height = 40
        
        x = (chat_width - status_width) // 2
        y = chat_height - status_height + 3
        
        self.mita_status.setGeometry(x, y, status_width, status_height)

    def _show_thinking_slot(self, character_name: str):
        """Слот для показа статуса 'думает'."""
        if hasattr(self, 'mita_status') and self.mita_status:
            logger.info('Показываем статус "Думает" для персонажа: %s', character_name)
            self.mita_status.show_thinking(character_name)

    def _show_error_slot(self, error_message: str):
        """Слот для показа статуса ошибки."""
        if hasattr(self, 'mita_status') and self.mita_status:
            logger.info('Показываем статус ошибки: %s', error_message)
            self.mita_status.show_error(error_message)

    def _hide_status_slot(self):
        """Слот для скрытия виджета статуса."""
        if hasattr(self, 'mita_status') and self.mita_status:
            logger.info('Скрываем статус')
            self.mita_status.hide_animated()
    
    def _pulse_error_slot(self):
        """Слот для 'пульсации' виджета статуса красным цветом."""
        if hasattr(self, 'mita_status') and self.mita_status:
            self.mita_status.pulse_error_animation()

    #endregion

    def _on_stream_start(self):
        """Вызывается при начале стрима"""
        # Статус уже должен быть показан, ничего не делаем
        pass

    def _on_stream_finish(self):
        """Вызывается при завершении стрима"""
        print("[DEBUG] Стрим завершен, скрываем статус")
        self.controller.hide_mita_status()