# voice_model_view.py

import os

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QFrame, QScrollArea, QLineEdit, QComboBox, QCheckBox,
                             QSizePolicy, QMessageBox, QApplication, QToolTip)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QEvent, QPoint, pyqtSlot
from PyQt6.QtGui import QFont, QCursor

from styles.voice_model_styles import get_stylesheet
from main_logger import logger
from utils import getTranslationVariant as _
from core.events import get_event_bus, Events
from ui.windows.voice_action_windows import VoiceInstallationWindow, VoiceActionWindow

class VoiceCollapsibleSection(QFrame):
    def __init__(self, parent, title, collapsed=False, update_scrollregion_func=None, clear_description_func=None):
        super().__init__(parent)
        
        def _angle_icon(kind: str, size: int = 10):
            """kind: 'right' | 'down'"""
            import qtawesome as qta
            name = "fa6s.angle-right" if kind == "right" else "fa6s.angle-down"
            return qta.icon(name, color="#f0f0f0").pixmap(size, size)

        self.update_scrollregion = update_scrollregion_func
        self.clear_description = clear_description_func or (lambda event=None: None)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 1)
        main_layout.setSpacing(0)
        
        # Header
        self.header_frame = QFrame()
        self.header_frame.setObjectName("VoiceCollapsibleHeader")
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(5, 2, 5, 2)
        
        # ► / ▼  →  иконки
        self.arrow = QLabel()
        self.arrow_pix_right = _angle_icon("right", 10)
        self.arrow_pix_down  = _angle_icon("down",  10)
        self.arrow.setPixmap(self.arrow_pix_right if collapsed else self.arrow_pix_down)
        self.arrow.setFixedWidth(15)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: white; font-weight: bold; font-size: 9pt;")
        
        header_layout.addWidget(self.arrow)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        # Content frame
        self.content_frame = QFrame()
        self.content_frame.setObjectName("VoiceCollapsibleContent")
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(1, 0, 1, 1)
        self.content_layout.setSpacing(1)
        
        main_layout.addWidget(self.header_frame)
        main_layout.addWidget(self.content_frame)
        
        # Click handlers
        self.header_frame.mousePressEvent = self.toggle
        self.arrow.mousePressEvent = self.toggle
        self.title_label.mousePressEvent = self.toggle
        
        self.is_collapsed = collapsed
        self.row_count = 0
        self.widgets = {}
        
        if self.is_collapsed:
            self.collapse(update_scroll=False)
        else:
            self.expand(update_scroll=False)

    def toggle(self, event=None):
        if self.is_collapsed:
            self.expand()
        else:
            self.collapse()
        self.is_collapsed = not self.is_collapsed
        if self.update_scrollregion:
            QTimer.singleShot(10, self.update_scrollregion)

    def collapse(self, update_scroll=True):
        self.arrow.setPixmap(self.arrow_pix_right)
        self.content_frame.setVisible(False)
        if update_scroll and self.update_scrollregion:
            QTimer.singleShot(10, self.update_scrollregion)

    def expand(self, update_scroll=True):
        self.arrow.setPixmap(self.arrow_pix_down)
        self.content_frame.setVisible(True)
        if update_scroll and self.update_scrollregion:
            QTimer.singleShot(10, self.update_scrollregion)

    def add_row(self, key, label_text, widget_type, options, setting_info, show_setting_description=None):
        row_height = 28
        is_locked = setting_info.get("locked", False)
        
        # Create horizontal layout for the row
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 1, 0, 0)
        
        # Label
        label_container = QFrame()
        label_container.setObjectName("VoiceSettingLabel")
        label_container.setFixedHeight(row_height)
        label_layout = QHBoxLayout(label_container)
        label_layout.setContentsMargins(10, 3, 10, 3)
        
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {'#888888' if is_locked else 'white'}; font-size: 8pt;")
        label_layout.addWidget(label)
        
        # Widget container
        widget_container = QFrame()
        widget_container.setObjectName("VoiceSettingWidget")
        widget_container.setFixedHeight(row_height)
        widget_layout = QHBoxLayout(widget_container)
        widget_layout.setContentsMargins(5, 2, 5, 2)
        
        widget = None
        widget_var = None
        current_value = options.get("default")
        
        if widget_type == "entry":
            widget = QLineEdit()
            widget.setEnabled(not is_locked)
            if current_value is not None:
                widget.setText(str(current_value))
            widget_var = widget
            widget_layout.addWidget(widget)
            
        elif widget_type == "combobox":
            widget = QComboBox()
            values_list = options.get("values", [])
            if not isinstance(values_list, (list, tuple)):
                values_list = []
            
            widget.addItems([str(v) for v in values_list])
            widget.setEnabled(not is_locked)
            
            if current_value is not None and values_list:
                str_value = str(current_value)
                str_values = [str(v) for v in values_list]
                try:
                    index = str_values.index(str_value)
                    widget.setCurrentIndex(index)
                except ValueError:
                    if values_list:
                        widget.setCurrentIndex(0)
            
            widget_var = widget
            widget_layout.addWidget(widget)
            
        elif widget_type == "checkbutton":
            widget = QCheckBox()
            widget.setEnabled(not is_locked)
            
            bool_value = False
            if isinstance(current_value, str):
                bool_value = current_value.lower() == 'true'
            elif current_value is not None:
                bool_value = bool(current_value)
            
            widget.setChecked(bool_value)
            widget_var = widget
            widget_layout.addWidget(widget)
            widget_layout.addStretch()
        
        if widget:
            self.widgets[key] = {'widget': widget, 'variable': widget_var}
            
            if show_setting_description:
                for w in [label_container, label, widget_container, widget]:
                    w.enterEvent = lambda e, k=key: show_setting_description(k)
                    w.leaveEvent = lambda e: self.clear_description()
        
        # Add row to content
        row_layout.addWidget(label_container, 4)
        row_layout.addWidget(widget_container, 5)
        
        self.content_layout.addLayout(row_layout)
        self.row_count += 1
        
        return widget

    def get_values(self):
        values = {}
        for key, data in self.widgets.items():
            widget = data.get('widget')
            value = None
            try:
                if isinstance(widget, QComboBox):
                    value = widget.currentText()
                elif isinstance(widget, QLineEdit):
                    value = widget.text()
                elif isinstance(widget, QCheckBox):
                    value = widget.isChecked()
                values[key] = value
            except Exception as e:
                logger.info(f"{_('Ошибка получения значения для', 'Error getting value for')} {key}: {e}")
                values[key] = None
        return values


class VoiceModelSettingsView(QWidget):

    
    update_description_signal = pyqtSignal(str)
    clear_description_signal = pyqtSignal()
    install_started_signal = pyqtSignal(str)
    install_finished_signal = pyqtSignal(dict)
    uninstall_started_signal = pyqtSignal(str) 
    uninstall_finished_signal = pyqtSignal(dict)
    refresh_panels_signal = pyqtSignal()
    refresh_settings_signal = pyqtSignal()

    ask_question_signal = pyqtSignal(str, str, object, object)
    create_voice_action_window_signal = pyqtSignal(str, str, object, object)


    def __init__(self):
        super().__init__()
        
        self.setWindowTitle(_("Настройки и Установка Локальных Моделей", "Settings and Installation of Local Models"))
        self.setMinimumSize(750, 500)
        self.resize(875, 800)
        
        # Apply stylesheet
        self.setStyleSheet(get_stylesheet())
        
        self.event_bus = get_event_bus()
        
        self.description_label_widget = None
        self.settings_sections = {}
        self.model_action_buttons = {}
        self.scrollable_frame_settings = None
        self.placeholder_label_settings = None
        self.top_frame_settings = None
        self.models_canvas = None
        self.settings_canvas = None
        self.models_scrollable_area = None

        self._initialize_layout()
        
        # Подписываемся на события обновления UI
        self.update_description_signal.connect(self._on_update_description)
        self.clear_description_signal.connect(self._on_clear_description)
        self.install_started_signal.connect(self._on_install_started)
        self.install_finished_signal.connect(self._on_install_finished)
        self.uninstall_started_signal.connect(self._on_uninstall_started)
        self.uninstall_finished_signal.connect(self._on_uninstall_finished)
        self.refresh_panels_signal.connect(self._on_refresh_panels)
        self.refresh_settings_signal.connect(self._on_refresh_settings)        
        self.ask_question_signal.connect(self._on_ask_question)
        self.create_voice_action_window_signal.connect(self._on_create_voice_action_window)
        
        # Инициализируем данные
        self._initialize_data()

    @pyqtSlot(str, str, object, object)
    def _on_ask_question(self, title, message, result_holder, local_loop):
        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        result_holder["answer"] = (reply == QMessageBox.StandardButton.Yes)
        local_loop.quit()

    @pyqtSlot(str, str, object, object)
    def _on_create_voice_action_window(self, title, status, result_holder, local_loop):
        from ui.windows.voice_action_windows import VoiceActionWindow
        window = VoiceActionWindow(self.window() or self, title, status)
        window.show()
        result_holder["window"] = window
        local_loop.quit()

    def _initialize_data(self):
        # Получаем данные через события
        models_data = self._get_models_data()
        installed_models = self._get_installed_models()
        
        self.create_model_panels(models_data, installed_models)
        
        dependencies_status = self._get_dependencies_status()
        self.display_installed_models_settings(models_data, installed_models, dependencies_status)

    def _get_models_data(self):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.GET_MODEL_DATA)
        return results[0] if results else []

    def _get_installed_models(self):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.GET_INSTALLED_MODELS)
        return results[0] if results else set()

    def _get_dependencies_status(self):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.GET_DEPENDENCIES_STATUS)
        return results[0] if results else {}

    def _get_default_description(self):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.GET_DEFAULT_DESCRIPTION)
        return results[0] if results else ""

    def _check_gpu_rtx30_40(self):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.CHECK_GPU_RTX30_40)
        return results[0] if results else False

    def _initialize_layout(self):
        # Главный layout устанавливаем сразу на self
        main_widget_layout = QVBoxLayout(self)
        main_widget_layout.setContentsMargins(0, 0, 0, 0)
        
        # Создаем контейнер для основного содержимого
        content_widget = QWidget()
        main_layout = QHBoxLayout(content_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Left panel
        left_panel = QWidget()
        left_panel.setFixedWidth(280)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)
        
        # Description frame
        description_frame = QFrame()
        description_frame.setObjectName("DescriptionFrame")
        description_frame.setFixedHeight(135)
        desc_layout = QVBoxLayout(description_frame)
        desc_layout.setContentsMargins(10, 5, 10, 10)
        
        desc_title = QLabel(_("Описание:", "Description"))
        desc_title.setStyleSheet("font-weight: bold; font-size: 9pt;")
        desc_layout.addWidget(desc_title)
        
        default_description = self._get_default_description()
        self.description_label_widget = QLabel(default_description)
        self.description_label_widget.setWordWrap(True)
        self.description_label_widget.setStyleSheet("color: #cccccc; font-size: 9pt;")
        self.description_label_widget.setAlignment(Qt.AlignmentFlag.AlignTop)
        desc_layout.addWidget(self.description_label_widget)
        desc_layout.addStretch()
        
        left_layout.addWidget(description_frame)
        
        # Models list
        models_title = QLabel(_("Доступные Модели:", "Available models"))
        models_title.setStyleSheet("font-weight: bold; font-size: 10pt;")
        left_layout.addWidget(models_title)
        
        # Models scroll area
        self.models_canvas = QScrollArea()
        self.models_canvas.setWidgetResizable(True)
        self.models_canvas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.models_scrollable_area = QWidget()
        self.models_layout = QVBoxLayout(self.models_scrollable_area)
        self.models_layout.setContentsMargins(0, 0, 0, 0)
        self.models_layout.setSpacing(4)
        
        self.models_canvas.setWidget(self.models_scrollable_area)
        left_layout.addWidget(self.models_canvas)
        
        main_layout.addWidget(left_panel)
        
        # Right panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Settings scroll area
        self.settings_canvas = QScrollArea()
        self.settings_canvas.setWidgetResizable(True)
        self.settings_canvas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.scrollable_frame_settings = QWidget()
        self.settings_layout = QVBoxLayout(self.scrollable_frame_settings)
        self.settings_layout.setContentsMargins(10, 10, 10, 10)
        
        # Top frame for dependencies status (будет заполнен Controller'ом)
        self.top_frame_settings = QFrame()
        top_layout = QVBoxLayout(self.top_frame_settings)
        top_layout.setContentsMargins(0, 0, 0, 5)
        self.settings_layout.addWidget(self.top_frame_settings)
        
        self.settings_canvas.setWidget(self.scrollable_frame_settings)
        right_layout.addWidget(self.settings_canvas)
        
        main_layout.addWidget(right_panel, 1)
        
        # Bottom buttons
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(10, 10, 10, 10)
        
        close_button = QPushButton(_("Закрыть", "Close"))
        close_button.clicked.connect(self._on_close_clicked)
        
        save_button = QPushButton(_("Сохранить", "Save"))
        save_button.clicked.connect(self._on_save_clicked)
        save_button.setObjectName("PrimaryButton")
        
        bottom_layout.addStretch()
        bottom_layout.addWidget(close_button)
        bottom_layout.addWidget(save_button)
        
        # Добавляем виджеты в главный layout
        main_widget_layout.addWidget(content_widget, 1)
        main_widget_layout.addWidget(bottom_widget)

    def _on_install_clicked(self, model_id):
        models_data = self._get_models_data()
        model_data = next((m for m in models_data if m["id"] == model_id), None)
        if not model_data:
            return
            
        model_name = model_data.get("name", model_id)
        
        window = VoiceInstallationWindow(
            self.window() if self.window() else self,
            _(f"Скачивание {model_name}", f"Downloading {model_name}"),
            _("Подготовка...", "Preparing...")
        )
        
        window.show()
        
        self.event_bus.emit(Events.VoiceModel.INSTALL_MODEL, {
            'model_id': model_id,
            'progress_callback': window.update_progress,
            'status_callback': window.update_status,
            'log_callback': window.update_log,
            'window': window
        })

    def _on_uninstall_clicked(self, model_id):
        self.event_bus.emit(Events.VoiceModel.UNINSTALL_MODEL, {'model_id': model_id})

    def _on_save_clicked(self):
        self.event_bus.emit(Events.VoiceModel.SAVE_SETTINGS)

    def _on_close_clicked(self):
        self.event_bus.emit(Events.VoiceModel.CLOSE_DIALOG)

    def _on_model_description_requested(self, model_id):
        self.event_bus.emit(Events.VoiceModel.UPDATE_DESCRIPTION, model_id)

    def _on_setting_description_requested(self, setting_key):
        self.event_bus.emit(Events.VoiceModel.UPDATE_DESCRIPTION, setting_key)

    def _on_clear_description_requested(self):
        self.event_bus.emit(Events.VoiceModel.CLEAR_DESCRIPTION)

    def _on_update_description(self, text):
        if self.description_label_widget:
            self.description_label_widget.setText(text)

    def _on_clear_description(self):
        if self.description_label_widget:
            default_description = self._get_default_description()
            self.description_label_widget.setText(default_description)

    def _on_install_started(self, model_id):
        button = self.model_action_buttons.get(model_id)
        if button:
            button.setText(_("Загрузка...", "Downloading..."))
            button.setEnabled(False)
        self.disable_all_action_buttons()

    def _on_install_finished(self, data):
        self.enable_all_action_buttons()
        self._initialize_data()

    def _on_uninstall_started(self, model_id):
        button = self.model_action_buttons.get(model_id)
        if button:
            button.setText(_("Удаление...", "Uninstalling..."))
            button.setEnabled(False)
        self.disable_all_action_buttons()

    def _on_uninstall_finished(self, data):
        self.enable_all_action_buttons()
        self._initialize_data()

    def _on_refresh_panels(self):
        models_data = self._get_models_data()
        installed_models = self._get_installed_models()
        self.create_model_panels(models_data, installed_models)

    def _on_refresh_settings(self):
        models_data = self._get_models_data()
        installed_models = self._get_installed_models()
        dependencies_status = self._get_dependencies_status()
        self.display_installed_models_settings(models_data, installed_models, dependencies_status)

    def create_model_panels(self, models_data, installed_models):
        """Создает панели моделей на основе данных от Controller"""
        if not self.models_scrollable_area:
            return
            
        # Clear existing panels
        while self.models_layout.count():
            item = self.models_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        self.model_action_buttons = {}
        
        for model_info in models_data:
            panel = self.create_model_panel(self.models_scrollable_area, model_info, installed_models)
            self.models_layout.addWidget(panel)
            
        self.models_layout.addStretch()
        QTimer.singleShot(50, self._update_models_scrollregion)

    def create_model_panel(self, parent, model_data, installed_models):
        model_id = model_data["id"]
        model_name = model_data["name"]
        supported_vendors = model_data.get('gpu_vendor', [])
        requires_rtx30plus = model_data.get("rtx30plus", False)
        
        panel = QFrame()
        panel.setObjectName("ModelPanel")
        panel.enterEvent = lambda e: self._on_model_description_requested(model_id)
        panel.leaveEvent = lambda e: self._on_clear_description_requested()
        
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 5, 10, 6)
        panel_layout.setSpacing(2)
        
        # Title row
        title_layout = QHBoxLayout()
        title_label = QLabel(model_name)
        title_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        title_label.enterEvent = lambda e: self._on_model_description_requested(model_id)
        title_label.leaveEvent = lambda e: self._on_clear_description_requested()
        title_layout.addWidget(title_label)
        
        # Warning icon for medium model
        if model_id == "medium":
            warning_icon = QLabel("⚠️")
            warning_icon.setStyleSheet("color: orange; font-size: 9pt;")
            warning_icon.setCursor(QCursor(Qt.CursorShape.WhatsThisCursor))
            medium_tooltip_text = _(
                "Модель 'Fish Speech' не рекомендуется для большинства пользователей.\n\n"
                "Для стабильной скорости генерации требуется мощная видеокарта, "
                "минимальные \"играбельные\" GPU: GeForce RTX 2080 Ti / RTX 2070 Super / GTX 1080 Ti и подобные, "
                "использование на более слабых GPU может привести к очень медленной работе.\n\n"
                "Владельцам RTX30+ рекомендуется использовать модели \"Fish Speech+\", "
                "остальным рекомендуется использовать модель \"Silero + RVC\"",
                "The 'Fish Speech' model is not recommended for most users.\n\n"
                "A powerful graphics card is required for stable generation speed, "
                "minimum \"playable\" GPUs: GeForce RTX 2080 Ti / RTX 2070 Super / GTX 1080 Ti and similar, "
                "using it on weaker GPUs can lead to very slow performance.\n\n"
                "RTX30+ owners are recommended to use \"Fish Speech+\" models, "
                "others are recommended to use the \"Silero + RVC\" model"
            )
            warning_icon.setToolTip(medium_tooltip_text)
            title_layout.addWidget(warning_icon)
        
        # RTX 30+ indicator
        if requires_rtx30plus:
            gpu_meets_requirement = self._check_gpu_rtx30_40()
            icon_color = "lightgreen" if gpu_meets_requirement else "orange"
            rtx_label = QLabel("RTX 30+")
            rtx_label.setStyleSheet(f"color: {icon_color}; font-size: 7pt; font-weight: bold;")
            rtx_tooltip_text = _("Требуется GPU NVIDIA RTX 30xx/40xx для оптимальной производительности.", 
                               "Requires NVIDIA RTX 30xx/40xx GPU for optimal performance.") if not gpu_meets_requirement else _("Ваша GPU подходит для этой модели.", "Your GPU is suitable for this model.")
            rtx_label.setToolTip(rtx_tooltip_text)
            title_layout.addWidget(rtx_label)
        
        title_layout.addStretch()
        panel_layout.addLayout(title_layout)
        
        # Info row
        vram_text = f"VRAM: {model_data.get('min_vram', '?')}GB - {model_data.get('rec_vram', '?')}GB"
        gpu_req_text = f"GPU: {', '.join(supported_vendors)}" if supported_vendors else "GPU: Any"
        info_label = QLabel(f"{vram_text} | {gpu_req_text}")
        info_label.setStyleSheet("color: #b0b0b0; font-size: 8pt;")
        info_label.enterEvent = lambda e: self._on_model_description_requested(model_id)
        info_label.leaveEvent = lambda e: self._on_clear_description_requested()
        panel_layout.addWidget(info_label)
        
        # AMD warning if needed
        allow_unsupported_gpu = os.environ.get("ALLOW_UNSUPPORTED_GPU", "0") == "1"
        
        # Получаем информацию о GPU через событие
        gpu_info = self.event_bus.emit_and_wait(Events.VoiceModel.GET_DEPENDENCIES_STATUS)[0]
        detected_gpu_vendor = gpu_info.get('detected_gpu_vendor') if gpu_info else None
        
        is_amd_user = detected_gpu_vendor == "AMD"
        is_amd_supported = "AMD" in supported_vendors
        is_gpu_unsupported_amd = is_amd_user and not is_amd_supported
        show_warning_amd = allow_unsupported_gpu and is_gpu_unsupported_amd
        
        if show_warning_amd:
            warning_label = QLabel(_("Может не работать на AMD!", "May not work on AMD!"))
            warning_label.setStyleSheet("color: #FF6A6A; font-size: 8pt; font-weight: bold;")
            panel_layout.addWidget(warning_label)
        
        # Action button
        is_installed = model_id in installed_models
        
        if is_installed:
            action_button = QPushButton(_("Удалить", "Uninstall"))
            action_button.setObjectName("DangerButton")
            action_button.clicked.connect(lambda: self._on_uninstall_clicked(model_id))
        else:
            install_text = _("Установить", "Install")
            can_install = True
            if is_gpu_unsupported_amd and not allow_unsupported_gpu:
                can_install = False
                install_text = _("Несовместимо с AMD", "Incompatible with AMD")
            
            action_button = QPushButton(install_text)
            action_button.setObjectName("SecondaryButton")
            action_button.setEnabled(can_install)
            if can_install:
                action_button.clicked.connect(lambda: self._on_install_clicked(model_id))
        
        self.model_action_buttons[model_id] = action_button
        panel_layout.addWidget(action_button)
        
        return panel

    def display_installed_models_settings(self, models_data, installed_models, dependencies_status):
        """Отображает настройки для установленных моделей на основе данных от Controller"""
        if not self.scrollable_frame_settings:
            return
            
        # Clear existing settings (except top frame)
        self._clear_settings_layout()
                
        self.settings_sections.clear()
        
        # Re-add top frame first
        self.top_frame_settings = QFrame()
        top_layout = QVBoxLayout(self.top_frame_settings)
        top_layout.setContentsMargins(0, 0, 0, 5)
        self._display_dependencies_status(top_layout, dependencies_status)
        self.settings_layout.addWidget(self.top_frame_settings)
        
        if not installed_models:
            self.placeholder_label_settings = QLabel(
                _("Модели не установлены.\n\nНажмите 'Установить' слева для установки модели,\nее настройки появятся здесь.", 
                  "Models not installed.\n\nClick 'Install' on the left to install a model,\nits settings will appear here.")
            )
            self.placeholder_label_settings.setStyleSheet("color: #aaa; font-size: 10pt;")
            self.placeholder_label_settings.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.placeholder_label_settings.setWordWrap(True)
            self.settings_layout.addWidget(self.placeholder_label_settings)
            self.settings_layout.addStretch()
        else:
            any_settings_shown = False
            
            for model_data in models_data:
                model_id = model_data.get("id")
                if not model_id or model_id not in installed_models:
                    continue
                    
                any_settings_shown = True
                model_name = model_data.get('name', model_id)
                
                section_title = f"{_('Настройки:', 'Settings:')} {model_name}"
                start_collapsed = len(installed_models) > 2
                section = VoiceCollapsibleSection(
                    self.scrollable_frame_settings,
                    section_title,
                    collapsed=start_collapsed,
                    update_scrollregion_func=self._update_settings_scrollregion,
                    clear_description_func=self._on_clear_description_requested
                )
                self.settings_sections[model_id] = section
                
                model_settings = model_data.get("settings", [])
                if model_settings:
                    for setting_info in model_settings:
                        key = setting_info.get("key")
                        label = setting_info.get("label", key)
                        widget_type = setting_info.get("type")
                        options = setting_info.get("options", {})
                        if key and widget_type:
                            section.add_row(
                                key, label, widget_type, options, setting_info,
                                show_setting_description=lambda k: self._on_setting_description_requested(k)
                            )
                else:
                    no_settings_label = QLabel(_("Специфические настройки отсутствуют.", "Specific settings are missing."))
                    no_settings_label.setStyleSheet("color: #ccc; font-size: 9pt;")
                    section.content_layout.addWidget(no_settings_label)
                    
                self.settings_layout.addWidget(section)
                
            if not any_settings_shown:
                self.placeholder_label_settings = QLabel(
                    _("Не удалось отобразить настройки для установленных моделей.", 
                      "Could not display settings for installed models.")
                )
                self.placeholder_label_settings.setStyleSheet("color: #aaa; font-size: 10pt;")
                self.placeholder_label_settings.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.settings_layout.addWidget(self.placeholder_label_settings)
                
            self.settings_layout.addStretch()
            
        QTimer.singleShot(50, self._update_settings_scrollregion)

    def _display_dependencies_status(self, layout, dependencies_status):
        """Отображает статус зависимостей на основе данных от Controller"""
        if dependencies_status.get('show_triton_checks', False):
            status_layout = QHBoxLayout()
            
            items = [
                ("CUDA Toolkit:", dependencies_status.get('cuda_found', False)),
                ("Windows SDK:", dependencies_status.get('winsdk_found', False)),
                ("MSVC:", dependencies_status.get('msvc_found', False))
            ]
            
            for text, found in items:
                item_layout = QHBoxLayout()
                item_layout.setSpacing(3)
                
                label = QLabel(text)
                label.setStyleSheet("font-size: 9pt;")
                item_layout.addWidget(label)
                
                status_text = _("Найден", "Found") if found else _("Не найден", "Not Found")
                status_color = "lightgreen" if found else "#FF6A6A"
                status_label = QLabel(status_text)
                status_label.setStyleSheet(f"font-size: 9pt; color: {status_color};")
                item_layout.addWidget(status_label)
                
                status_layout.addLayout(item_layout)
                status_layout.addSpacing(15)
            
            status_layout.addStretch()
            layout.addLayout(status_layout)
            
            if not (dependencies_status.get('cuda_found') and dependencies_status.get('winsdk_found') and dependencies_status.get('msvc_found')):
                warning_layout = QHBoxLayout()
                warning_text = _("⚠️ Для моделей Fish Speech+ / +RVC могут потребоваться все компоненты.", 
                               "⚠️ Fish Speech+ / +RVC models may require all components.")
                warning_label = QLabel(warning_text)
                warning_label.setStyleSheet("color: orange; font-weight: bold; font-size: 9pt;")
                warning_layout.addWidget(warning_label)
                
                doc_link = QLabel(_("[Документация]", "[Documentation]"))
                doc_link.setStyleSheet("color: #81d4fa; font-weight: bold; font-size: 9pt; text-decoration: underline;")
                doc_link.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                doc_link.mousePressEvent = lambda e: self.event_bus.emit(Events.VoiceModel.OPEN_DOC, "installation_guide.html")
                warning_layout.addWidget(doc_link)
                
                warning_layout.addStretch()
                layout.addLayout(warning_layout)
        
        elif not dependencies_status.get('triton_installed'):
            warning_label = QLabel(_("Triton не установлен (необходим для Fish Speech+ / +RVC).", 
                                   "Triton not installed (required for Fish Speech+ / +RVC)."))
            warning_label.setStyleSheet("color: orange; font-size: 9pt;")
            layout.addWidget(warning_label)
        else:
            info_label = QLabel(_("Проверка зависимостей Triton доступна только в Windows.", 
                                "Triton dependency check is only available on Windows."))
            info_label.setStyleSheet("color: #aaaaaa; font-size: 9pt;")
            layout.addWidget(info_label)

    def _clear_settings_layout(self):
        while self.settings_layout.count():
            item = self.settings_layout.takeAt(0) 
            w = item.widget()
            if w:
                w.deleteLater()

    def _update_scrollregion(self, canvas):
        """Update scroll region"""
        if canvas:
            canvas.updateGeometry()

    def _update_settings_scrollregion(self, event=None):
        self._update_scrollregion(self.settings_canvas)

    def _update_models_scrollregion(self, event=None):
        self._update_scrollregion(self.models_canvas)

    def get_section_values(self, model_id):
        section = self.settings_sections.get(model_id)
        if section:
            return section.get_values()
        return {}

    def get_all_section_values(self):
        """Получить значения всех секций настроек"""
        all_values = {}
        for model_id, section in self.settings_sections.items():
            all_values[model_id] = section.get_values()
        return all_values

    def set_button_text(self, model_id, text):
        button = self.model_action_buttons.get(model_id)
        if button:
            button.setText(text)

    def set_button_enabled(self, model_id, enabled):
        button = self.model_action_buttons.get(model_id)
        if button:
            button.setEnabled(enabled)

    def set_button_object_name(self, model_id, name):
        button = self.model_action_buttons.get(model_id)
        if button:
            button.setObjectName(name)
            button.setStyleSheet(button.styleSheet())  # Refresh style

    def disable_all_action_buttons(self):
        for button in self.model_action_buttons.values():
            button.setEnabled(False)
            if not hasattr(button, '_original_text'):
                button._original_text = button.text()

    def enable_all_action_buttons(self):
        models_data = self._get_models_data()
        installed_models = self._get_installed_models()
        
        for model_id, button in self.model_action_buttons.items():
            model_data = next((m for m in models_data if m["id"] == model_id), None)
            if not model_data:
                continue
                
            if model_id in installed_models:
                # Кнопка удаления
                button.setText(_("Удалить", "Uninstall"))
                button.setEnabled(True)
                button.setObjectName("DangerButton")
                button.setStyleSheet(button.styleSheet())  # Refresh style
            else:
                # Кнопка установки с проверкой совместимости
                install_text = _("Установить", "Install")
                can_install = True
                
                supported_vendors = model_data.get('gpu_vendor', [])
                allow_unsupported_gpu = os.environ.get("ALLOW_UNSUPPORTED_GPU", "0") == "1"
                
                gpu_info = self.event_bus.emit_and_wait(Events.VoiceModel.GET_DEPENDENCIES_STATUS)[0]
                detected_gpu_vendor = gpu_info.get('detected_gpu_vendor') if gpu_info else None
                
                is_amd_user = detected_gpu_vendor == "AMD"
                is_amd_supported = "AMD" in supported_vendors
                is_gpu_unsupported_amd = is_amd_user and not is_amd_supported
                
                if is_gpu_unsupported_amd and not allow_unsupported_gpu:
                    can_install = False
                    install_text = _("Несовместимо с AMD", "Incompatible with AMD")
                
                button.setText(install_text)
                button.setEnabled(can_install)
                button.setObjectName("SecondaryButton")
                button.setStyleSheet(button.styleSheet())  # Refresh style

    def show_warning(self, title, message):
        QMessageBox.warning(self, title, message)

    def show_critical(self, title, message):
        QMessageBox.critical(self, title, message)

    def show_question(self, title, message):
        reply = QMessageBox.question(self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        return reply == QMessageBox.StandardButton.Yes