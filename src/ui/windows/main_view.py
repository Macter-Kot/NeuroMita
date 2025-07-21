import io
import base64
import re
import time
from pathlib import Path
import os
from PyQt6.QtCore import QSize
from styles.main_styles import get_stylesheet
from utils import _, process_text_to_voice
from main_logger import logger
import ui.gui_templates as gui_templates
from managers.settings_manager import CollapsibleSection
from ui.settings.voiceover_settings import LOCAL_VOICE_MODELS
import types

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QPropertyAnimation, QBuffer, QIODevice, QEvent 
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QScrollArea, QFrame, QSplitter,
    QMessageBox, QDialog, QProgressBar, QStackedWidget,
    QTextBrowser, QLineEdit, QFileDialog, QGraphicsOpacityEffect, QSizePolicy  
)
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont, QImage, QIcon, QPalette, QKeyEvent, QPixmap
import qtawesome as qta

from ui.settings import (
    api_settings, character_settings, chat_settings, g4f_settings, gamemaster_settings, general_model_settings,
    language_settings, microphone_settings, screen_analysis_settings,
    token_settings, voiceover_settings, command_replacer_settings, history_compressor,
    prompt_catalogue_settings
)

from ui.widgets import (status_indicators_widget)

from ui.widgets.overlay_widget import OverlayWidget
from ui.widgets.image_viewer_widget import ImageViewerWidget
from ui.widgets.image_preview_widget import ImagePreviewBar
from ui.widgets.mita_status_widget import MitaStatusWidget

from controllers.voice_model_controller import VoiceModelController

from core.events import get_event_bus, Events, Event
from PyQt6.QtCore import (Qt, QTimer, pyqtSignal, QPoint, QPropertyAnimation, QEasingCurve, QBuffer, QIODevice, QEvent)


class SettingsOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("SettingsOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget#SettingsOverlay {
                background-color: #1a1a1a;
                border-left: 4px solid #0f0f0f;
            }
            QWidget#SettingsOverlay QStackedWidget,
            QWidget#SettingsOverlay QStackedWidget > QWidget,
            QWidget#SettingsOverlay QScrollArea,
            QWidget#SettingsOverlay QScrollArea > QWidget > QWidget {
                background-color: transparent;
                border: none;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

    def add_container(self, container):
        self.stack.addWidget(container)

    def show_category(self, container):
        self.stack.setCurrentWidget(container)
        self.show()
        
        if isinstance(container, QScrollArea):
            container.verticalScrollBar().setValue(0)

class SettingsIconButton(QPushButton):
    def __init__(self, icon_name, tooltip_text, parent=None):
        super().__init__(parent)
        self.setIcon(qta.icon(icon_name, color='#dcdcdc'))
        from PyQt6.QtCore import QSize
        icon_size = QApplication.style().pixelMetric(QApplication.style().PixelMetric.PM_SmallIconSize)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setToolTip(tooltip_text)
        self.setFixedSize(40, 40)
        self.is_active = False
        self.update_style()
        
    def set_active(self, active):
        self.is_active = active
        self.update_style()
        
    def update_style(self):
        if self.is_active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #8a2be2;
                    border: none;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #9932cc;
                }
                QPushButton:pressed {
                    background-color: #7b1fa2;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: rgba(138, 43, 226, 0.3);
                }
                QPushButton:pressed {
                    background-color: rgba(138, 43, 226, 0.5);
                }
            """)

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

    history_loaded_signal = pyqtSignal(dict)          
    more_history_loaded_signal = pyqtSignal(dict)     
    model_initialized_signal = pyqtSignal(dict)       
    model_init_cancelled_signal = pyqtSignal(dict)    
    model_init_failed_signal = pyqtSignal(dict)       
    show_tg_code_dialog_signal = pyqtSignal(dict)     
    show_tg_password_dialog_signal = pyqtSignal(dict) 
    reload_prompts_success_signal = pyqtSignal()      
    reload_prompts_failed_signal = pyqtSignal(dict)   
    display_loading_popup_signal = pyqtSignal(dict)   
    hide_loading_popup_signal = pyqtSignal()          

    clear_user_input_signal = pyqtSignal()
    update_chat_font_size_signal = pyqtSignal(int)
    switch_voiceover_settings_signal = pyqtSignal()
    load_chat_history_signal = pyqtSignal()
    check_triton_dependencies_signal = pyqtSignal()
    show_info_message_signal = pyqtSignal(dict)
    show_error_message_signal = pyqtSignal(dict)
    update_model_loading_status_signal = pyqtSignal(str)
    finish_model_loading_signal = pyqtSignal(dict)
    cancel_model_loading_signal = pyqtSignal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        
        self.SETTINGS_PANEL_WIDTH = 400
        
        self.event_bus = get_event_bus()
        self._connect_signals()
        
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
        self.setWindowIcon(QIcon('Icon.png'))

        self.staged_image_data = []

        self.ffmpeg_install_popup = None

        self.current_settings_category = None
        self.settings_containers = {}

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
        
        self.settings_animation = QPropertyAnimation(self.settings_overlay, b"maximumWidth")
        self.settings_animation.setDuration(250)
        self.settings_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)


        self.chat_window.installEventFilter(self)

        self.overlay = OverlayWidget(self)
        self.image_preview_bar = None
        self._init_image_preview()

        try:
            microphone_settings.load_mic_settings(self)
        except Exception as e:
            logger.info("Не удалось удачно получить настройки микрофона", e)

        QTimer.singleShot(500, self.initialize_last_local_model_on_startup)

        self.prepare_stream_signal.connect(self._on_stream_start)
        self.finish_stream_signal.connect(self._on_stream_finish)

        self.update_status_colors()

        self.last_voice_model_selected = None
        self.current_local_voice_id = None
        self.model_loading_cancelled = False

    def _connect_signals(self):
        self.history_loaded_signal.connect(self._on_history_loaded)
        self.more_history_loaded_signal.connect(self._on_more_history_loaded)
        self.model_initialized_signal.connect(self._on_model_initialized)
        self.model_init_cancelled_signal.connect(self._on_model_init_cancelled)
        self.model_init_failed_signal.connect(self._on_model_init_failed)
        self.show_tg_code_dialog_signal.connect(self._on_show_tg_code_dialog)
        self.show_tg_password_dialog_signal.connect(self._on_show_tg_password_dialog)
        self.reload_prompts_success_signal.connect(self._on_reload_prompts_success)
        self.reload_prompts_failed_signal.connect(self._on_reload_prompts_failed)
        self.display_loading_popup_signal.connect(self._on_display_loading_popup)
        self.hide_loading_popup_signal.connect(self._on_hide_loading_popup)
        self.update_chat_font_size_signal.connect(self.update_chat_font_size)
        self.switch_voiceover_settings_signal.connect(self.switch_voiceover_settings)
        self.load_chat_history_signal.connect(self.load_chat_history)
        self.check_triton_dependencies_signal.connect(self.check_triton_dependencies)
        self.clear_user_input_signal.connect(self._on_clear_user_input)
        self.show_info_message_signal.connect(self._on_show_info_message)
        self.show_error_message_signal.connect(self._on_show_error_message)
        self.update_model_loading_status_signal.connect(self._on_update_model_loading_status)
        self.finish_model_loading_signal.connect(self._on_finish_model_loading)
        self.cancel_model_loading_signal.connect(self._on_cancel_model_loading)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        self.setStyleSheet(get_stylesheet())
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.setup_chat_frame(main_layout)
        self.setup_settings_panel(main_layout)
        
        self._init_settings_containers()
        
        self.resize(1200, 800)
        
    def _on_hide_animation_finished(self):
        self.settings_overlay.hide()
        try:
            self.settings_animation.finished.disconnect(self._on_hide_animation_finished)
        except TypeError:
            pass

    def _init_settings_containers(self):
        callbacks = {
            "general":     self.setup_common_controls,
            "language":    language_settings.create_language_section,
            "api":         api_settings.setup_api_controls,
            "models":      general_model_settings.setup_general_settings_control,
            "voice":       voiceover_settings.setup_voiceover_controls,
            "microphone":  microphone_settings.setup_microphone_controls,
            "characters":  character_settings.setup_mita_controls,
            "prompts":     prompt_catalogue_settings.setup_prompt_catalogue_controls,
            "chat":        chat_settings.setup_chat_settings_controls,
            "screen":      screen_analysis_settings.setup_screen_analysis_controls,
            "tokens":      token_settings.setup_token_settings_controls,
            "commands":    command_replacer_settings.setup_command_replacer_controls,
            "history":     history_compressor.setup_history_compressor_controls,
            "gamemaster":  gamemaster_settings.setup_game_master_controls,
            "debug":       self._debug_wrapper,
            "news":        self._news_wrapper,
        }

        for key, fn in callbacks.items():
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            scroll_area.setObjectName(f"ScrollArea_{key}")
            
            # Отключаем горизонтальную полосу прокрутки
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            
            content_widget = QWidget()
            content_widget.setObjectName(f"ContentWidget_{key}")
            
            content_layout = QVBoxLayout(content_widget)
            content_layout.setContentsMargins(10, 10, 10, 10)  # Добавляем отступы
            content_layout.setSpacing(5)

            if isinstance(fn, types.MethodType) and fn.__self__ is self:
                fn(content_layout)
            else:
                fn(self, content_layout)
            
            content_layout.addStretch()
            
            scroll_area.setWidget(content_widget)

            self.settings_containers[key] = scroll_area
            self.settings_overlay.add_container(scroll_area)

    def show_settings_category(self, category):
        self.settings_animation.stop()

        is_hiding = (self.current_settings_category == category and self.settings_overlay.width() > 0)
        
        # Обновляем активное состояние кнопок
        for cat, btn in self.settings_buttons.items():
            btn.set_active(cat == category and not is_hiding)
        
        if is_hiding:
            self.current_settings_category = None
            self.settings_animation.setEndValue(0)
            
            try:
                self.settings_animation.finished.disconnect(self._on_hide_animation_finished)
            except TypeError:
                pass
            self.settings_animation.finished.connect(self._on_hide_animation_finished)

        else:
            self.current_settings_category = category
            cont = self.settings_containers.get(category)
            if not cont:
                return

            self.settings_overlay.show_category(cont)
            self.settings_animation.setEndValue(self.SETTINGS_PANEL_WIDTH)

        self.settings_animation.setStartValue(self.settings_overlay.width())
        self.settings_animation.start()

    def _create_debug_section(self, parent, layout):
        debug_label = QLabel(_('Отладочная информация', 'Debug Information'))
        debug_label.setObjectName('SeparatorLabel')
        layout.addWidget(debug_label)
        
        self.debug_window = QTextEdit()
        self.debug_window.setReadOnly(True)
        self.debug_window.setObjectName("DebugWindow")
        self.debug_window.setMinimumHeight(200)
        layout.addWidget(self.debug_window)
        
        status_indicators_widget.create_status_indicators(self, layout)
        
        self.update_debug_info()

    def _create_news_section(self, parent, layout):
        news_label = QLabel(self.get_news_content())
        news_label.setWordWrap(True)
        news_label.setObjectName('SeparatorLabel')
        layout.addWidget(news_label)

    def setup_news_control(self, parent):
        news_label = QLabel(self.get_news_content())
        news_label.setWordWrap(True)
        parent.addWidget(news_label)

    def setup_common_controls(self, parent_layout):
        common_config = [
            {'label': _('Скрывать (приватные) данные', 'Hide (private) data'), 'key': 'HIDE_PRIVATE',
            'type': 'checkbutton', 'default_checkbutton': True},
        ]
        gui_templates.create_settings_direct(self, parent_layout, common_config)

    def setup_debug_controls(self, parent):
        self.debug_window = QTextEdit()
        self.debug_window.setReadOnly(True)
        self.debug_window.setObjectName("DebugWindow")
        self.debug_window.setMinimumHeight(200)
        parent.addWidget(self.debug_window)
        
        status_indicators_widget.create_status_indicators(self, parent)
        
        self.update_debug_info()

    def setup_settings_panel(self, main_layout):
        settings_panel = QWidget()
        settings_panel.setFixedWidth(50)
        settings_panel.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
            }
        """)
        
        panel_layout = QVBoxLayout(settings_panel)
        panel_layout.setContentsMargins(5, 10, 5, 10)
        panel_layout.setSpacing(5)
        
        self.settings_overlay = SettingsOverlay(self)
        self.settings_overlay.setMaximumWidth(0)
        self.settings_overlay.hide()
        
        # Сохраняем кнопки для управления активным состоянием
        self.settings_buttons = {}
        
        settings_categories = [
            ("fa5s.cog", _("Общие", "General"), "general"),
            ("fa5s.language", _("Язык", "Language"), "language"), 
            ("fa5s.plug", _("API", "API"), "api"),
            ("fa5s.robot", _("Модели", "Models"), "models"),
            ("fa5s.volume-up", _("Озвучка", "Voice"), "voice"),
            ("fa5s.microphone", _("Микрофон", "Microphone"), "microphone"),
            ("fa5s.user", _("Персонажи", "Characters"), "characters"),
            ("fa5s.list", _("Промпты", "Prompts"), "prompts"),
            ("fa5s.comments", _("Чат", "Chat"), "chat"),
            ("fa5s.desktop", _("Экран", "Screen"), "screen"),
            ("fa5s.coins", _("Токены", "Tokens"), "tokens"),
            ("fa5s.exchange-alt", _("Команды", "Commands"), "commands"),
            ("fa5s.compress", _("История", "History"), "history"),
            ("fa5s.gamepad", _("Игра", "Game"), "gamemaster"),
            ("fa5s.bug", _("Отладка", "Debug"), "debug"),
            ("fa5s.newspaper", _("Новости", "News"), "news"),
        ]
        
        for icon_name, tooltip, category in settings_categories:
            btn = SettingsIconButton(icon_name, tooltip)
            btn.clicked.connect(lambda checked, cat=category, b=btn: self.show_settings_category(cat))
            panel_layout.addWidget(btn)
            self.settings_buttons[category] = btn
        
        panel_layout.addStretch()
        
        main_layout.addWidget(self.settings_overlay)
        main_layout.addWidget(settings_panel)

    def setup_chat_frame(self, main_layout):
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(10, 10, 10, 10)
        chat_layout.setSpacing(5)
        
        # Верхняя панель с кнопками и статусами
        top_panel_layout = QHBoxLayout()
        
        # Кнопки слева
        self.clear_chat_button = QPushButton(_("Очистить", "Clear"))
        self.clear_chat_button.clicked.connect(self.clear_chat_display)
        self.clear_chat_button.setMaximumHeight(30)
        
        self.load_history_button = QPushButton(_("Взять из истории", "Load from history"))
        self.load_history_button.clicked.connect(self.load_chat_history)
        self.load_history_button.setMaximumHeight(30)
        
        top_panel_layout.addWidget(self.clear_chat_button)
        top_panel_layout.addWidget(self.load_history_button)
        
        # Статус индикаторы правее от кнопок (с небольшим отступом)
        top_panel_layout.addSpacing(20)  # Отступ между кнопками и индикаторами
        
        # Создаем статус индикаторы
        from ui.widgets import status_indicators_widget
        status_indicators_widget.create_status_indicators_inline(self, top_panel_layout)
        
        top_panel_layout.addStretch()  # Растяжка справа
        
        chat_layout.addLayout(top_panel_layout)
        
        # Остальная часть остается без изменений...
        self.chat_window = QTextBrowser()
        self.chat_window.setOpenExternalLinks(False)
        self.chat_window.setReadOnly(True)
        initial_font_size = int(self._get_setting("CHAT_FONT_SIZE", 12))
        font = QFont("Arial", initial_font_size)
        self.chat_window.setFont(font)
        
        chat_layout.addWidget(self.chat_window, 1)

        self._create_scroll_to_bottom_button()

        self.mita_status = MitaStatusWidget(self.chat_window)
        self._position_mita_status()
        
        input_frame = QFrame()
        input_frame.setStyleSheet(get_stylesheet())
        input_layout = QVBoxLayout(input_frame)
        
        self.token_count_label = QLabel(_("Токены: 0/0 | Стоимость: 0.00 ₽", "Tokens: 0/0 | Cost: 0.00 ₽"))
        self.token_count_label.setStyleSheet("font-size: 10px;")
        input_layout.addWidget(self.token_count_label)
        
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
        
        from PyQt6.QtWidgets import QGridLayout
        container_layout = QGridLayout(input_container)
        container_layout.setContentsMargins(5, 5, 5, 5)
        container_layout.setSpacing(5)
        
        self.user_entry = QTextEdit()
        self.user_entry.setMinimumHeight(24)
        self.user_entry.setMaximumHeight(80)
        self.user_entry.setFixedHeight(36)
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
        
        self.user_entry.textChanged.connect(self._adjust_input_height)
        self.user_entry.textChanged.connect(self._update_send_button_state)
        
        container_layout.addWidget(self.user_entry, 0, 0, 1, 2)
        
        button_container = QWidget()
        button_container.setFixedHeight(24)
        button_container.setStyleSheet("""
            background-color: transparent;
            border: none;
        """)
        button_layout_inner = QHBoxLayout(button_container)
        button_layout_inner.setContentsMargins(0, 0, 0, 0)
        button_layout_inner.setSpacing(4)
        
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
        
        container_layout.addWidget(button_container, 1, 0)
        
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
        
        send_container = QWidget()
        send_container.setStyleSheet("""
            background-color: transparent;
            border: none;
        """)
        send_layout = QHBoxLayout(send_container)
        send_layout.setContentsMargins(0, 0, 0, 0)
        send_layout.addStretch()
        send_layout.addWidget(self.send_button)
        
        container_layout.addWidget(send_container, 1, 1)
        
        input_layout.addWidget(input_container)

        self.attachment_label = QLabel("")
        self.attachment_label.setVisible(False)
        self.clear_attach_btn = QPushButton("")
        self.clear_attach_btn.setVisible(False)

        chat_layout.addWidget(input_frame)

        self._update_send_button_state()
        
        main_layout.addWidget(chat_widget, 1)

    def _debug_wrapper(self, parent_layout):
        debug_label = QLabel(_('Отладочная информация', 'Debug Information'))
        debug_label.setObjectName('SeparatorLabel')
        parent_layout.addWidget(debug_label)
        
        self.debug_window = QTextEdit()
        self.debug_window.setReadOnly(True)
        self.debug_window.setObjectName("DebugWindow")
        self.debug_window.setMinimumHeight(200)
        parent_layout.addWidget(self.debug_window)
        
        self.update_debug_info()

    def _news_wrapper(self, parent_layout):
        self.setup_news_control(parent_layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay.resize(self.size())
        
        QTimer.singleShot(0, self._position_mita_status)

    def _adjust_input_height(self):
        doc = self.user_entry.document()
        doc_height = doc.size().height()
        
        new_height = int(doc_height + 10)
        
        new_height = max(36, min(new_height, 80))
        
        self.user_entry.setFixedHeight(new_height)

    def _update_send_button_state(self):
        has_text = bool(self.user_entry.toPlainText().strip())
        has_images = bool(self.staged_image_data)
        
        has_auto_images = False
        if self._get_setting("ENABLE_SCREEN_ANALYSIS", False):
            frames = self.event_bus.emit_and_wait(Events.CAPTURE_SCREEN, {'limit': 1}, timeout=0.5)
            has_auto_images = bool(frames and frames[0])
            
        if self._get_setting("ENABLE_CAMERA_CAPTURE", False):
            camera_frames = self.event_bus.emit_and_wait(Events.GET_CAMERA_FRAMES, {'limit': 1}, timeout=0.5)
            has_auto_images = has_auto_images or bool(camera_frames and camera_frames[0])
        
        is_enabled = has_text or has_images or has_auto_images
        
        self.send_button.setEnabled(is_enabled)
        
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
        hide_tags = self._get_setting("HIDE_CHAT_TAGS", False)

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

        show_timestamps = self._get_setting("SHOW_CHAT_TIMESTAMPS", False)
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
            character_name = self._get_character_name()
            self._insert_formatted_text(cursor, f"{character_name}: ", QColor("hot pink"), bold=True)

    def _insert_formatted_text(self, cursor, text, color=None, bold=False, italic=False):
        char_format = QTextCharFormat()
        
        if color:
            char_format.setForeground(color)
        else:
            default_text_color = self.chat_window.palette().color(QPalette.ColorRole.Text)
            char_format.setForeground(default_text_color)
        
        font = QFont("Arial", int(self._get_setting("CHAT_FONT_SIZE", 12)))
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

        success = self.event_bus.emit_and_wait(Events.SCHEDULE_G4F_UPDATE, {'version': target_version}, timeout=1.0)
        
        if success and success[0]:
            QMessageBox.information(self, _("Запланировано", "Scheduled"),
                _("Версия g4f '{version}' будет установлена/обновлена при следующем запуске программы.",
                  "g4f version '{version}' will be installed/updated the next time the program starts.").format(
                    version=target_version))
        else:
            QMessageBox.critical(self, _("Ошибка сохранения", "Save Error"),
                _("Не удалось сохранить настройки для обновления. Пожалуйста, проверьте логи.",
                  "Failed to save settings for the update. Please check the logs."))

    def update_status_colors(self):
        game_connected = self.event_bus.emit_and_wait(Events.GET_GAME_CONNECTION, timeout=0.5)
        silero_connected = self.event_bus.emit_and_wait(Events.GET_SILERO_STATUS, timeout=0.5)
        mic_active = self.event_bus.emit_and_wait(Events.GET_MIC_STATUS, timeout=0.5)
        screen_capture_active = self.event_bus.emit_and_wait(Events.GET_SCREEN_CAPTURE_STATUS, timeout=0.5)
        camera_capture_active = self.event_bus.emit_and_wait(Events.GET_CAMERA_CAPTURE_STATUS, timeout=0.5)
        
        if hasattr(self, 'game_status_checkbox'):
            self.game_status_checkbox.setChecked(bool(game_connected and game_connected[0]))
            
        if hasattr(self, 'silero_status_checkbox'):
            self.silero_status_checkbox.setChecked(bool(silero_connected and silero_connected[0]))
            
        if hasattr(self, 'mic_status_checkbox'):
            self.mic_status_checkbox.setChecked(bool(mic_active and mic_active[0]))
            
        if hasattr(self, 'screen_capture_status_checkbox'):
            self.screen_capture_status_checkbox.setChecked(bool(screen_capture_active and screen_capture_active[0]))
            
        if hasattr(self, 'camera_capture_status_checkbox'):
            self.camera_capture_status_checkbox.setChecked(bool(camera_capture_active and camera_capture_active[0]))

    def load_chat_history(self):
        self.clear_chat_display()
        
        self.event_bus.emit(Events.LOAD_HISTORY)

    def _on_history_loaded(self, data: dict):
        messages = data.get('messages', [])
        
        for entry in messages:
            role = entry["role"]
            content = entry["content"]
            message_time = entry.get("time", "???")
            try:
                self.insert_message(role, content, message_time=message_time)
            except Exception as ex:
                logger.error(f"_on_history_loaded: НУ Я ПОНЯЛ: {str(ex)}")
        
        self.update_debug_info()
        
        self.chat_window.verticalScrollBar().setValue(
            self.chat_window.verticalScrollBar().maximum()
        )

    

    

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
            
            debug_info_result = self.event_bus.emit_and_wait(Events.GET_DEBUG_INFO, timeout=0.5)
            debug_info = debug_info_result[0] if debug_info_result else "Debug info not available"
            
            self.debug_window.insertPlainText(debug_info)

    def update_token_count(self, event=None):
        show_token_info = self._get_setting("SHOW_TOKEN_INFO", True)

        if show_token_info:
            current_context_tokens = self.event_bus.emit_and_wait(Events.GET_CURRENT_CONTEXT_TOKENS, timeout=0.5)
            current_context_tokens = current_context_tokens[0] if current_context_tokens else 0
            
            max_model_tokens = int(self._get_setting("MAX_MODEL_TOKENS", 32000))
            
            cost = self.event_bus.emit_and_wait(Events.CALCULATE_COST, timeout=0.5)
            cost = cost[0] if cost else 0.0

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
        self.event_bus.emit(Events.CLEAR_CHAT)

    def send_message(self, system_input: str = "", image_data: list[bytes] = None):
        user_input = self.user_entry.toPlainText().strip()
        current_image_data = []
        staged_image_data = self.staged_image_data.copy()

        if self._get_setting("ENABLE_SCREEN_ANALYSIS", False):
            history_limit = int(self._get_setting("SCREEN_CAPTURE_HISTORY_LIMIT", 1))
            frames = self.event_bus.emit_and_wait(Events.CAPTURE_SCREEN, {'limit': history_limit}, timeout=0.5)
            if frames and frames[0]:
                current_image_data.extend(frames[0])
            else:
                logger.info("Анализ экрана включен, но кадры не готовы или история пуста.")

        all_image_data = (image_data or []) + current_image_data + staged_image_data

        if self._get_setting("ENABLE_CAMERA_CAPTURE", False):
            history_limit = int(self._get_setting("CAMERA_CAPTURE_HISTORY_LIMIT", 1))
            camera_frames = self.event_bus.emit_and_wait(Events.GET_CAMERA_FRAMES, {'limit': history_limit}, timeout=0.5)
            if camera_frames and camera_frames[0]:
                all_image_data.extend(camera_frames[0])
                logger.info(f"Добавлено {len(camera_frames[0])} кадров с камеры для отправки.")
            else:
                logger.info("Захват с камеры включен, но кадры не готовы или история пуста.")

        if not user_input and not system_input and not all_image_data:
            return

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

        self.event_bus.emit(Events.SEND_MESSAGE, {
            'user_input': user_input,
            'system_input': system_input,
            'image_data': all_image_data
        })

        if staged_image_data:
            self.event_bus.emit(Events.CLEAR_STAGED_IMAGES)
            self.staged_image_data.clear()
            if self.image_preview_bar:
                self.image_preview_bar.clear()
                self._hide_image_preview_bar()

    def load_more_history(self):
        self.event_bus.emit(Events.LOAD_MORE_HISTORY)

    def _on_more_history_loaded(self, data: dict):
        messages_to_prepend = data.get('messages', [])
        
        if not messages_to_prepend:
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
        
        logger.info(f"Загружено еще {len(messages_to_prepend)} сообщений.")

    def _save_setting(self, key, value):
        self.event_bus.emit(Events.SAVE_SETTING, {'key': key, 'value': value})

    def _get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def _get_character_name(self):
        result = self.event_bus.emit_and_wait(Events.GET_CHARACTER_NAME, timeout=0.5)
        return result[0] if result else "Assistant"

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

    def closeEvent(self, event):
        self.event_bus.emit(Events.STOP_SCREEN_CAPTURE)
        self.event_bus.emit(Events.STOP_CAMERA_CAPTURE)
        self.event_bus.emit(Events.DELETE_SOUND_FILES)
        self.event_bus.emit(Events.STOP_SERVER)
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

        if selected_model_id in ["medium+", "medium+low"]:
            pass

        self._save_setting("NM_CURRENT_VOICEOVER", selected_model_id)
        self.current_local_voice_id = selected_model_id

        self.update_local_model_status_indicator()
        
        is_initialized = self.event_bus.emit_and_wait(Events.CHECK_MODEL_INITIALIZED, {'model_id': selected_model_id}, timeout=0.5)
        
        if not (is_initialized and is_initialized[0]):
            self.show_model_loading_window(selected_model)
        else:
            success = self.event_bus.emit_and_wait(Events.SELECT_VOICE_MODEL, {'model_id': selected_model_id}, timeout=1.0)
            
            if success and success[0]:
                self.last_voice_model_selected = selected_model
                self.update_local_voice_combobox()
                logger.info(f"Переключился на уже инициализированную модель «{selected_model_id}»")
            else:
                QMessageBox.critical(self, 'Ошибка', 'Не удалось активировать модель')

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
        
        self.model_loading_cancelled = False
        
        def progress_callback(status_type, message):
            if status_type == "status":
                QTimer.singleShot(0, lambda: self.loading_status_label.setText(message))
        
        self.event_bus.emit(Events.INIT_VOICE_MODEL, {
            'model_id': model_id,
            'progress_callback': progress_callback
        })
        
        self.loading_dialog.show()

    def _on_model_initialized(self, data: dict):
        model_id = data.get('model_id')
        
        if hasattr(self, 'loading_dialog') and self.loading_dialog:
            self.loading_dialog.close()
        
        success = self.event_bus.emit_and_wait(Events.SELECT_VOICE_MODEL, {'model_id': model_id}, timeout=1.0)
        
        if success and success[0]:
            for model in LOCAL_VOICE_MODELS:
                if model["id"] == model_id:
                    self.last_voice_model_selected = model
                    break
            
            QMessageBox.information(self, _("Успешно", "Success"),
                _("Модель {} успешно инициализирована!", "Model {} initialized successfully!").format(model_id))
            
            self.update_local_voice_combobox()
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось активировать модель после инициализации")

    def _on_model_init_cancelled(self, data: dict):
        if hasattr(self, 'loading_dialog') and self.loading_dialog:
            self.loading_dialog.close()

    def _on_model_init_failed(self, data: dict):
        model_id = data.get('model_id')
        error = data.get('error', 'Unknown error')
        
        if hasattr(self, 'loading_dialog') and self.loading_dialog:
            self.loading_dialog.close()
        
        QMessageBox.critical(self, "Ошибка",
            f"Не удалось инициализировать модель {model_id}.\n{error}")

    def cancel_model_loading(self, loading_window):
        logger.info("Загрузка модели отменена пользователем.")
        self.model_loading_cancelled = True
        if loading_window:
            loading_window.close()

        restored_model_id = None
        if self.last_voice_model_selected:
            if hasattr(self, 'local_voice_combobox'):
                self.local_voice_combobox.setCurrentText(self.last_voice_model_selected["name"])
            restored_model_id = self.last_voice_model_selected["id"]
            self._save_setting("NM_CURRENT_VOICEOVER", restored_model_id)
            self.current_local_voice_id = restored_model_id
        else:
            if hasattr(self, 'local_voice_combobox'):
                self.local_voice_combobox.setCurrentText('')
            self._save_setting("NM_CURRENT_VOICEOVER", None)
            self.current_local_voice_id = None

        self.update_local_model_status_indicator()

    def initialize_last_local_model_on_startup(self):
        if self._get_setting("LOCAL_VOICE_LOAD_LAST", False):
            logger.info("Проверка автозагрузки последней локальной модели...")
            last_model_id = self._get_setting("NM_CURRENT_VOICEOVER", None)

            if last_model_id:
                logger.info(f"Найдена последняя модель для автозагрузки: {last_model_id}")
                model_to_load = None
                for model in LOCAL_VOICE_MODELS:
                    if model["id"] == last_model_id:
                        model_to_load = model
                        break

                if model_to_load:
                    is_installed = self.event_bus.emit_and_wait(Events.CHECK_MODEL_INSTALLED, {'model_id': last_model_id}, timeout=0.5)
                    
                    if is_installed and is_installed[0]:
                        is_initialized = self.event_bus.emit_and_wait(Events.CHECK_MODEL_INITIALIZED, {'model_id': last_model_id}, timeout=0.5)
                        
                        if not (is_initialized and is_initialized[0]):
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
            current_model_id_combo = self._get_setting("NM_CURRENT_VOICEOVER", None)

            if current_model_id_combo:
                is_installed = self.event_bus.emit_and_wait(Events.CHECK_MODEL_INSTALLED, {'model_id': current_model_id_combo}, timeout=0.5)
                if is_installed and is_installed[0]:
                    is_initialized = self.event_bus.emit_and_wait(Events.CHECK_MODEL_INITIALIZED, {'model_id': current_model_id_combo}, timeout=0.5)
                    if not (is_initialized and is_initialized[0]):
                        show_combobox_indicator = True
                else:
                    show_combobox_indicator = True

            self.local_model_status_label.setVisible(show_combobox_indicator)

        show_section_warning = False
        if (hasattr(self, 'voiceover_section_warning_label') and 
                self.voiceover_section_warning_label and
                hasattr(self, 'voiceover_section') and 
                self.voiceover_section):

            voiceover_method = self._get_setting("VOICEOVER_METHOD", "TG")
            current_model_id_section = self._get_setting("NM_CURRENT_VOICEOVER", None)

            if voiceover_method == "Local" and current_model_id_section:
                is_installed = self.event_bus.emit_and_wait(Events.CHECK_MODEL_INSTALLED, {'model_id': current_model_id_section}, timeout=0.5)
                if is_installed and is_installed[0]:
                    is_initialized = self.event_bus.emit_and_wait(Events.CHECK_MODEL_INITIALIZED, {'model_id': current_model_id_section}, timeout=0.5)
                    if not (is_initialized and is_initialized[0]):
                        show_section_warning = True
                else:
                    show_section_warning = True

            if hasattr(self.voiceover_section, 'warning_label'):
                self.voiceover_section.warning_label.setVisible(show_section_warning)

    def switch_voiceover_settings(self, selected_method: str | None = None) -> None:
        if selected_method is not None:
            self._save_setting("VOICEOVER_METHOD", selected_method)

        use_voice        = bool(self._get_setting("USE_VOICEOVER",  True))
        current_method   =      self._get_setting("VOICEOVER_METHOD", "TG")

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

        self.check_triton_dependencies()

    def update_local_voice_combobox(self):
        if not hasattr(self, 'local_voice_combobox') or self.local_voice_combobox is None:
            logger.warning("update_local_voice_combobox: виджет local_voice_combobox не найден.")
            return

        self.local_voice_combobox.blockSignals(True)

        try:
            installed_models_names = []
            for model in LOCAL_VOICE_MODELS:
                is_installed = self.event_bus.emit_and_wait(Events.CHECK_MODEL_INSTALLED, {'model_id': model["id"]}, timeout=0.5)
                if is_installed and is_installed[0]:
                    installed_models_names.append(model["name"])
            
            logger.info(f'Доступные модели: {installed_models_names}')

            current_items = [self.local_voice_combobox.itemText(i) for i in range(self.local_voice_combobox.count())]

            if installed_models_names != current_items:
                self.local_voice_combobox.clear()
                self.local_voice_combobox.addItems(installed_models_names)
                logger.info(f"Обновлен список локальных моделей: {installed_models_names}")

            current_model_id = self._get_setting("NM_CURRENT_VOICEOVER", None)
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
                            if self._get_setting("NM_CURRENT_VOICEOVER") != model["id"]:
                                self._save_setting("NM_CURRENT_VOICEOVER", model["id"])
                                self.current_local_voice_id = model["id"]
                            break
            else:
                if self.local_voice_combobox.currentText() != '':
                    self.local_voice_combobox.setCurrentText('')
                if self._get_setting("NM_CURRENT_VOICEOVER") is not None:
                    self._save_setting("NM_CURRENT_VOICEOVER", None)
                    self.current_local_voice_id = None
        finally:
            self.local_voice_combobox.blockSignals(False)

        self.update_local_model_status_indicator()
        self.check_triton_dependencies()

    def check_triton_dependencies(self):
        if hasattr(self, 'triton_warning_label') and self.triton_warning_label:
            self.triton_warning_label.deleteLater()
            delattr(self, 'triton_warning_label')

        if self._get_setting("VOICEOVER_METHOD") != "Local":
            return
        if not hasattr(self, 'local_settings_frame') or not self.local_settings_frame:
            return

        triton_found = False
        try:
            import triton
            triton_found = True
            logger.debug("Зависимости Triton найдены (через import triton).")
        except ImportError as e:
            logger.info(f"Зависимости Triton не найдены! Игнорируйте это предупреждение, если не используете \"Fish Speech+ / + RVC\" озвучку. Exception импорта: {e}")
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

                self.event_bus.emit(Events.REFRESH_VOICE_MODULES)
                self.update_local_voice_combobox()

                current_model_id = self._get_setting("NM_CURRENT_VOICEOVER", None)
                if current_model_id and current_model_id not in installed_models_ids:
                    logger.warning(f"Текущая модель {current_model_id} была удалена. Сбрасываем выбор.")
                    new_model_id = installed_models_ids[0] if installed_models_ids else None
                    self._save_setting("NM_CURRENT_VOICEOVER", new_model_id)
                    self.current_local_voice_id = new_model_id
                    self.update_local_voice_combobox()

            def check_installed_func(model_id):
                result = self.event_bus.emit_and_wait(Events.CHECK_MODEL_INSTALLED, {'model_id': model_id}, timeout=0.5)
                return result[0] if result else False

            class LocalVoiceStub:
                def is_model_installed(self, model_id):
                    return check_installed_func(model_id)

            from PyQt6.QtWidgets import QDialog
            install_dialog = QDialog(self)
            install_dialog.setWindowTitle(_("Управление локальными моделями", "Manage Local Models"))
            install_dialog.setModal(False)
            install_dialog.resize(875, 800)
            
            dialog_layout = QVBoxLayout(install_dialog)
            dialog_layout.setContentsMargins(0, 0, 0, 0)
            
            controller = VoiceModelController(
                view_parent=install_dialog,
                config_dir=config_dir,
                on_save_callback=on_save_callback,
                local_voice=LocalVoiceStub(),
                check_installed_func=check_installed_func,
            )
            
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

        success = self.event_bus.emit_and_wait(Events.CHANGE_VOICE_LANGUAGE, {'language': selected_language}, timeout=1.0)
        
        if success and success[0]:
            logger.info(f"Язык успешно изменен на {selected_language}.")
            self.update_local_model_status_indicator()
        else:
            logger.warning("Не удалось изменить язык озвучки")

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
        MitaName = self._get_character_name()
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

    def attach_images(self):
        file_paths, t = QFileDialog.getOpenFileNames(
            self,
            _("Выберите изображения", "Select Images"),
            "",
            _("Файлы изображений (*.png *.jpg *.jpeg *.bmp *.gif)", "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)")
        )

        if file_paths:
            for file_path in file_paths:
                self.event_bus.emit(Events.STAGE_IMAGE, {'image_data': file_path})
            
            for file_path in file_paths:
                try:
                    with open(file_path, "rb") as f:
                        img_data = f.read()
                        self.staged_image_data.append(img_data)
                        
                        self._show_image_preview_bar()
                        self.image_preview_bar.add_image(img_data)
                except Exception as e:
                    logger.error(f"Ошибка чтения файла {file_path}: {e}")
            
            logger.info(f"Прикреплены изображения: {file_paths}")
            self._update_send_button_state()

    def send_screen_capture(self):
        logger.info("Запрошена отправка скриншота.")
        
        frames = self.event_bus.emit_and_wait(Events.CAPTURE_SCREEN, {'limit': 1}, timeout=0.5)
        
        if not frames or not frames[0]:
            QMessageBox.warning(self, _("Ошибка", "Error"),
                                _("Не удалось захватить экран. Убедитесь, что анализ экрана включен в настройках.",
                                "Failed to capture the screen. Make sure screen analysis is enabled in settings."))
            return

        for frame_data in frames[0]:
            self.staged_image_data.append(frame_data)
            self.event_bus.emit(Events.STAGE_IMAGE, {'image_data': frame_data})
        
        self._show_image_preview_bar()
        for frame_data in frames[0]:
            self.image_preview_bar.add_image(frame_data)
        
        self._update_send_button_state()

    def _clear_staged_images(self):
        self.event_bus.emit(Events.CLEAR_STAGED_IMAGES)
        
        self.staged_image_data.clear()
        if self.image_preview_bar:
            self.image_preview_bar.clear()
            self._hide_image_preview_bar()
        
        self._update_send_button_state()

    def _clipboard_image_to_controller(self) -> bool:
        cb = QApplication.clipboard()
        if not cb.mimeData().hasImage():
            return False

        qimg = cb.image()
        if qimg.isNull():
            return False

        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buf, "PNG")
        img_bytes = buf.data().data()

        self.staged_image_data.append(img_bytes)
        
        self.event_bus.emit(Events.STAGE_IMAGE, {'image_data': img_bytes})

        self._show_image_preview_bar()
        self.image_preview_bar.add_image(img_bytes)
        
        self._update_send_button_state()
        
        return True

    def _init_image_preview(self):
        self.staged_image_data = []
        
    def _show_image_preview_bar(self):
        if not self.image_preview_bar:
            input_frame = None
            
            widget = self.user_entry
            while widget:
                if isinstance(widget, QFrame) and widget.objectName() != "":
                    break
                if hasattr(widget, 'layout') and widget.layout():
                    for i in range(widget.layout().count()):
                        item = widget.layout().itemAt(i)
                        if item and item.widget() == self.token_count_label:
                            input_frame = widget
                            break
                if input_frame:
                    break
                widget = widget.parent()
            
            if not input_frame:
                input_frame = self.token_count_label.parent()
            
            if input_frame:
                self.image_preview_bar = ImagePreviewBar(input_frame)
                self.image_preview_bar.thumbnail_clicked.connect(self._show_full_image)
                self.image_preview_bar.remove_requested.connect(self._remove_staged_image)
                
                input_frame.layout().insertWidget(1, self.image_preview_bar)
        
        self.image_preview_bar.show()

    def _remove_staged_image(self, index):
        if 0 <= index < len(self.staged_image_data):
            self.staged_image_data.pop(index)
            
            self.image_preview_bar.remove_at(index)
            
            if len(self.staged_image_data) == 0:
                self._hide_image_preview_bar()
            
            self._update_send_button_state()

    def _hide_image_preview_bar(self):
        if self.image_preview_bar:
            self.image_preview_bar.hide()
            
    def _show_full_image(self, image_data):
        try:
            if isinstance(image_data, str) and image_data.startswith("data:image"):
                base64_data = image_data.split(",")[1]
                img_bytes = base64.b64decode(base64_data)
            elif isinstance(image_data, bytes):
                img_bytes = image_data
            else:
                return
                
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes)
            
            viewer = ImageViewerWidget(pixmap)
            viewer.close_requested.connect(self.overlay.hide_animated)
            
            self.overlay.set_content(viewer)
            self.overlay.show_animated()
            
        except Exception as e:
            logger.error(f"Ошибка при показе изображения: {e}")


    def _on_show_tg_code_dialog(self, data: dict):
        code_future = data.get('future')
        
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
                if code_future and not code_future.done():
                    loop = self.event_bus.emit_and_wait(Events.GET_EVENT_LOOP, timeout=1.0)
                    if loop and loop[0] and loop[0].is_running():
                        loop[0].call_soon_threadsafe(code_future.set_result, code)
                dialog.accept()
            else:
                QMessageBox.critical(dialog, "Ошибка", "Введите код подтверждения")
        
        def on_reject():
            if code_future and not code_future.done():
                loop = self.event_bus.emit_and_wait(Events.GET_EVENT_LOOP, timeout=1.0)
                if loop and loop[0] and loop[0].is_running():
                    import asyncio
                    loop[0].call_soon_threadsafe(code_future.set_exception, asyncio.CancelledError("Ввод кода отменен"))

        btn = QPushButton("Подтвердить")
        btn.clicked.connect(submit_code)
        layout.addWidget(btn)
        code_entry.returnPressed.connect(submit_code)
        
        dialog.rejected.connect(on_reject)
        dialog.exec()


    def _on_show_tg_password_dialog(self, data: dict):
        password_future = data.get('future')
        
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
                if password_future and not password_future.done():
                    loop = self.event_bus.emit_and_wait(Events.GET_EVENT_LOOP, timeout=1.0)
                    if loop and loop[0] and loop[0].is_running():
                        loop[0].call_soon_threadsafe(password_future.set_result, pwd)
                dialog.accept()
            else:
                QMessageBox.critical(dialog, "Ошибка", "Введите пароль")
                
        def on_reject():
            if password_future and not password_future.done():
                loop = self.event_bus.emit_and_wait(Events.GET_EVENT_LOOP, timeout=1.0)
                if loop and loop[0] and loop[0].is_running():
                    import asyncio
                    loop[0].call_soon_threadsafe(password_future.set_exception, asyncio.CancelledError("Ввод пароля отменен"))

        btn = QPushButton("Подтвердить")
        btn.clicked.connect(submit_password)
        layout.addWidget(btn)
        password_entry.returnPressed.connect(submit_password)
        
        dialog.rejected.connect(on_reject)
        dialog.exec()

    def _position_mita_status(self):
        if not hasattr(self, 'mita_status') or not self.mita_status:
            return
            
        chat_width = self.chat_window.width()
        chat_height = self.chat_window.height()
        
        status_width = min(300, chat_width - 20)
        status_height = 40
        
        x = (chat_width - status_width) // 2
        y = chat_height - status_height + 3
        
        self.mita_status.setGeometry(x, y, status_width, status_height)

    def _show_thinking_slot(self, character_name: str):
        if hasattr(self, 'mita_status') and self.mita_status:
            logger.info('Показываем статус "Думает" для персонажа: %s', character_name)
            self.mita_status.show_thinking(character_name)

    def _show_error_slot(self, error_message: str):
        if hasattr(self, 'mita_status') and self.mita_status:
            logger.info('Показываем статус ошибки: %s', error_message)
            self.mita_status.show_error(error_message)

    def _hide_status_slot(self):
        if hasattr(self, 'mita_status') and self.mita_status:
            logger.info('Скрываем статус')
            self.mita_status.hide_animated()
    
    def _pulse_error_slot(self):
        if hasattr(self, 'mita_status') and self.mita_status:
            self.mita_status.pulse_error_animation()

    def _on_stream_start(self):
        pass

    def _on_stream_finish(self):
        print("[DEBUG] Стрим завершен, скрываем статус")
        self.event_bus.emit(Events.HIDE_MITA_STATUS)

    def _on_reload_prompts_success(self):
        QMessageBox.information(self, _("Успешно", "Success"), 
            _("Промпты успешно скачаны и перезагружены.", "Prompts successfully downloaded and reloaded."))
    
    def _on_reload_prompts_failed(self, data: dict):
        error = data.get('error', 'Unknown error')
        if error == "Event loop not running":
            QMessageBox.critical(self, _("Ошибка", "Error"), 
                _("Не удалось запустить асинхронную загрузку промптов.", "Failed to start asynchronous prompt download."))
        else:
            QMessageBox.critical(self, _("Ошибка", "Error"), 
                _("Не удалось скачать промпты с GitHub. Проверьте подключение к интернету.", 
                  "Failed to download prompts from GitHub. Check your internet connection."))
    
    def _show_loading_popup(self, message):
        self.event_bus.emit(Events.SHOW_LOADING_POPUP, {"message": message})
    
    def _on_display_loading_popup(self, data: dict):
        message = data.get('message', 'Loading...')
        
        if not hasattr(self, 'loading_popup'):
            from PyQt6.QtWidgets import QProgressDialog
            self.loading_popup = QProgressDialog(message, None, 0, 0, self)
            self.loading_popup.setWindowTitle(_("Загрузка", "Loading"))
            self.loading_popup.setModal(True)
            self.loading_popup.setCancelButton(None)
            self.loading_popup.setMinimumDuration(0)
        else:
            self.loading_popup.setLabelText(message)
        
        self.loading_popup.show()
    
    def _close_loading_popup(self):
        self.event_bus.emit(Events.CLOSE_LOADING_POPUP)
    
    def _on_hide_loading_popup(self):
        if hasattr(self, 'loading_popup') and self.loading_popup:
            self.loading_popup.close()

    def _on_clear_user_input(self):
        if self.user_entry:
            self.user_entry.clear()

    def _on_show_info_message(self, data: dict):
        title = data.get('title', 'Информация')
        message = data.get('message', '')
        QMessageBox.information(self, title, message)

    def _on_show_error_message(self, data: dict):
        title = data.get('title', 'Ошибка')
        message = data.get('message', '')
        QMessageBox.critical(self, title, message)

    def _on_update_model_loading_status(self, status: str):
        if hasattr(self, 'loading_status_label'):
            self.loading_status_label.setText(status)

    def _on_finish_model_loading(self, data: dict):
        model_id = data.get('model_id')
        if hasattr(self, 'finish_model_loading') and hasattr(self, 'loading_dialog'):
            self.finish_model_loading(model_id, self.loading_dialog)

    def _on_cancel_model_loading(self):
        if hasattr(self, 'cancel_model_loading') and hasattr(self, 'loading_dialog'):
            self.cancel_model_loading(self.loading_dialog)

    # region Следующие функции надо бы перенести в более подходящее место

    def create_settings_section(self, parent_layout, title, settings_config, icon_name=None):
        """Обёртка для обратной совместимости с модулями настроек"""
        # Создаём контейнер для заголовка
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 10)
        header_layout.setSpacing(5)
        
        # Создаём заголовок
        title_label = QLabel(title)
        title_label.setObjectName('SectionTitle')
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet('''
            QLabel#SectionTitle {
                font-size: 14px;
                font-weight: bold;
                color: #ffffff;
                padding: 5px 0;
            }
        ''')
        header_layout.addWidget(title_label)
        
        # Создаём разделитель
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet('''
            QFrame {
                background-color: #4a4a4a;
                max-height: 2px;
                margin: 0 10px;
            }
        ''')
        header_layout.addWidget(separator)
        
        parent_layout.addWidget(header_widget)
        
        # Создаём настройки
        gui_templates.create_settings_direct(self, parent_layout, settings_config)

    def create_settings_flat(self, parent_layout, title, settings_config, icon_name=None):
        """Создаёт настройки без секции (плоско) - для микрофона, озвучки, персонажей и промптов"""
        # Просто создаём настройки напрямую без заголовка секции
        gui_templates.create_settings_direct(self, parent_layout, settings_config)

    # endregion