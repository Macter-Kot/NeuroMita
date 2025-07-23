from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QTextEdit, QProgressBar, QApplication, QWidget)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor

from utils import getTranslationVariant as _

class VoiceInstallationWindow(QDialog):
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    log_updated = pyqtSignal(str)
    window_closed = pyqtSignal()
    
    def __init__(self, parent, title, initial_status=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(700, 400)
        self.setModal(True)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #ffffff;
            }
            QTextEdit {
                background-color: #101010;
                color: #cccccc;
                border: 1px solid #333;
            }
            QProgressBar {
                border: 1px solid #555;
                border-radius: 5px;
                background-color: #555555;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 5px;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        info_layout = QHBoxLayout()
        self.status_label = QLabel(initial_status or _("Подготовка...", "Preparing..."))
        self.status_label.setFont(QFont("Segoe UI", 9))
        info_layout.addWidget(self.status_label, 1)
        
        self.progress_value_label = QLabel("0%")
        self.progress_value_label.setFont(QFont("Segoe UI", 9))
        info_layout.addWidget(self.progress_value_label)
        
        layout.addLayout(info_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text, 1)
        
        self.progress_updated.connect(self._on_progress_update)
        self.status_updated.connect(self._on_status_update)
        self.log_updated.connect(self._on_log_update)
        
        if parent and hasattr(parent, 'geometry'):
            parent_rect = parent.geometry()
            self.move(
                parent_rect.center().x() - self.width() // 2,
                parent_rect.center().y() - self.height() // 2
            )
    
    def _on_progress_update(self, value):
        self.progress_bar.setValue(int(value))
        self.progress_value_label.setText(f"{int(value)}%")
    
    def _on_status_update(self, message):
        self.status_label.setText(message)
    
    def _on_log_update(self, text):
        self.log_text.append(text)
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
    
    def closeEvent(self, event):
        self.window_closed.emit()
        super().closeEvent(event)
    
    def update_progress(self, value):
        self.progress_updated.emit(value)
    
    def update_status(self, message):
        self.status_updated.emit(message)
    
    def update_log(self, text):
        self.log_updated.emit(text)


class VoiceActionWindow(QDialog):
    

    
    status_updated = pyqtSignal(str)
    log_updated = pyqtSignal(str)
    window_closed = pyqtSignal()
    
    def get_threadsafe_callbacks(self):
            return (
                None,
                self.status_updated.emit,
                self.log_updated.emit
            )

    def __init__(self, parent, title, initial_status=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(700, 400)
        self.setModal(True)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #ffffff;
            }
            QTextEdit {
                background-color: #101010;
                color: #cccccc;
                border: 1px solid #333;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        self.status_label = QLabel(initial_status or _("Подготовка...", "Preparing..."))
        self.status_label.setFont(QFont("Segoe UI", 9))
        layout.addWidget(self.status_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text, 1)
        
        self.status_updated.connect(self._on_status_update)
        self.log_updated.connect(self._on_log_update)
        
        if parent and hasattr(parent, 'geometry'):
            parent_rect = parent.geometry()
            self.move(
                parent_rect.center().x() - self.width() // 2,
                parent_rect.center().y() - self.height() // 2
            )
    
    def _on_status_update(self, message):
        self.status_label.setText(message)
    
    def _on_log_update(self, text):
        self.log_text.append(text)
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
    
    def closeEvent(self, event):
        self.window_closed.emit()
        super().closeEvent(event)
    
    def update_status(self, message):
        self.status_updated.emit(message)
    
    def update_log(self, text):
        self.log_updated.emit(text)

class VCRedistWarningDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("⚠️ Ошибка загрузки Triton", "⚠️ Triton Load Error"))
        self.setModal(True)
        self.setFixedSize(500, 250)
        
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: #ffffff; }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: none;
                padding: 5px 10px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #555555; }
            #RetryButton { background-color: #4CAF50; }
            #RetryButton:hover { background-color: #45a049; }
        """)
        
        self.choice = 'close'
        
        layout = QVBoxLayout(self)
        
        title_label = QLabel(_("Ошибка импорта Triton (DLL Load Failed)", "Triton Import Error (DLL Load Failed)"))
        title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_label.setStyleSheet("color: orange;")
        layout.addWidget(title_label)
        
        info_text = _(
            "Не удалось загрузить библиотеку для Triton (возможно, отсутствует VC++ Redistributable).\n"
            "Установите последнюю версию VC++ Redistributable (x64) с сайта Microsoft\n"
            "или попробуйте импортировать снова, если вы только что его установили.",
            "Failed to load the library for Triton (VC++ Redistributable might be missing).\n"
            "Install the latest VC++ Redistributable (x64) from the Microsoft website\n"
            "or try importing again if you just installed it."
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        button_layout = QHBoxLayout()
        
        docs_button = QPushButton(_("Документация", "Documentation"))
        docs_button.clicked.connect(self._on_docs_clicked)
        button_layout.addWidget(docs_button)
        
        button_layout.addStretch()
        
        close_button = QPushButton(_("Закрыть", "Close"))
        close_button.clicked.connect(lambda: self._set_choice_and_accept('close'))
        button_layout.addWidget(close_button)
        
        retry_button = QPushButton(_("Попробовать снова", "Retry"))
        retry_button.setObjectName("RetryButton")
        retry_button.clicked.connect(lambda: self._set_choice_and_accept('retry'))
        button_layout.addWidget(retry_button)
        
        layout.addLayout(button_layout)
    
    def _on_docs_clicked(self):
        from core.events import get_event_bus, Events
        get_event_bus().emit(Events.VoiceModel.OPEN_DOC, "installation_guide.html#vc_redist")
    
    def _set_choice_and_accept(self, choice):
        self.choice = choice
        self.accept()
    
    def get_choice(self):
        return self.choice


class TritonDependenciesDialog(QDialog):
    def __init__(self, parent=None, dependencies_status=None):
        super().__init__(parent)
        self.setWindowTitle(_("⚠️ Зависимости Triton", "⚠️ Triton Dependencies"))
        self.setModal(True)
        self.setFixedSize(700, 350)
        
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: #ffffff; }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: none;
                padding: 5px 10px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #555555; }
            #ContinueButton { background-color: #4CAF50; }
            #ContinueButton:hover { background-color: #45a049; }
        """)
        
        self.choice = 'skip'
        self.dependencies_status = dependencies_status or {}
        
        layout = QVBoxLayout(self)
        
        title_label = QLabel(_("Статус зависимостей Triton:", "Triton Dependency Status:"))
        title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(title_label)
        
        self.status_layout = QHBoxLayout()
        self._update_status_display()
        layout.addLayout(self.status_layout)
        
        self.warning_label = QLabel(_("⚠️ Модели Fish Speech+ / + RVC требуют всех компонентов!", 
                                     "⚠️ Models Fish Speech+ / + RVC require all components!"))
        self.warning_label.setStyleSheet("color: orange; font-weight: bold;")
        cuda_found = self.dependencies_status.get('cuda_found', False)
        winsdk_found = self.dependencies_status.get('winsdk_found', False)
        msvc_found = self.dependencies_status.get('msvc_found', False)
        self.warning_label.setVisible(not (cuda_found and winsdk_found and msvc_found))
        layout.addWidget(self.warning_label)
        
        info_text = _(
            "Если компоненты не найдены, установите их согласно документации.\n"
            "Вы также можете попробовать инициализировать модель вручную,\n"
            "запустив `init_triton.bat` в корневой папке программы.",
            "If components are not found, install them according to the documentation.\n"
            "You can also try initializing the model manually\n"
            "by running `init_triton.bat` in the program's root folder."
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        button_layout = QHBoxLayout()
        
        docs_button = QPushButton(_("Открыть документацию", "Open Documentation"))
        docs_button.clicked.connect(self._on_docs_clicked)
        button_layout.addWidget(docs_button)
        
        refresh_button = QPushButton(_("Обновить статус", "Refresh Status"))
        refresh_button.clicked.connect(self._on_refresh_status)
        button_layout.addWidget(refresh_button)
        
        button_layout.addStretch()
        
        skip_button = QPushButton(_("Пропустить инициализацию", "Skip Initialization"))
        skip_button.clicked.connect(lambda: self._set_choice_and_accept('skip'))
        button_layout.addWidget(skip_button)
        
        continue_button = QPushButton(_("Продолжить инициализацию", "Continue Initialization"))
        continue_button.setObjectName("ContinueButton")
        continue_button.clicked.connect(lambda: self._set_choice_and_accept('continue'))
        button_layout.addWidget(continue_button)
        
        layout.addLayout(button_layout)
    
    def _update_status_display(self):
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        items = [
            ("CUDA Toolkit:", self.dependencies_status.get('cuda_found', False)),
            ("Windows SDK:", self.dependencies_status.get('winsdk_found', False)),
            ("MSVC:", self.dependencies_status.get('msvc_found', False))
        ]
        
        for text, found in items:
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 15, 0)
            
            label = QLabel(text)
            label.setFont(QFont("Segoe UI", 9))
            item_layout.addWidget(label)
            
            status_text = _("Найден", "Found") if found else _("Не найден", "Not Found")
            status_color = "#4CAF50" if found else "#F44336"
            status_label = QLabel(status_text)
            status_label.setFont(QFont("Segoe UI", 9))
            status_label.setStyleSheet(f"color: {status_color};")
            item_layout.addWidget(status_label)
            
            self.status_layout.addWidget(item_widget)
        
        self.status_layout.addStretch()
        
        if hasattr(self, 'warning_label'):
            cuda_found = self.dependencies_status.get('cuda_found', False)
            winsdk_found = self.dependencies_status.get('winsdk_found', False)
            msvc_found = self.dependencies_status.get('msvc_found', False)
            self.warning_label.setVisible(not (cuda_found and winsdk_found and msvc_found))
    
    def _on_refresh_status(self):
        from core.events import get_event_bus, Events
        event_bus = get_event_bus()
        
        results = event_bus.emit_and_wait(Events.Audio.REFRESH_TRITON_STATUS, timeout=5.0)
        if results and results[0]:
            self.dependencies_status = results[0]
            self._update_status_display()
    
    def _on_docs_clicked(self):
        from core.events import get_event_bus, Events
        get_event_bus().emit(Events.VoiceModel.OPEN_DOC, "installation_guide.html")
    
    def _set_choice_and_accept(self, choice):
        self.choice = choice
        self.accept()
    
    def get_choice(self):
        return self.choice