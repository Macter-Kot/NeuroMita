import base64
import json
import os

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt

from main_logger import logger

class SettingsManager:
    instance = None

    def __init__(self, config_path):
        self.config_path = config_path
        self.settings = {}
        self.load_settings()
        # Set the singleton instance. This should only happen once.
        if SettingsManager.instance is None:
            SettingsManager.instance = self

    def load_settings(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "rb") as f:
                    encoded = f.read()
                decoded = base64.b64decode(encoded)
                self.settings = json.loads(decoded.decode("utf-8"))
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            self.settings = {}

    def save_settings(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            json_data = json.dumps(self.settings, ensure_ascii=False, indent=4)
            encoded = base64.b64encode(json_data.encode("utf-8"))
            with open(self.config_path, "wb") as f:
                f.write(encoded)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")

    # The static methods provide the global access point for the entire application.
    # They operate on the singleton `instance`.

    @staticmethod
    def get(key, default=None):
        if SettingsManager.instance:
            # Directly access the 'settings' dictionary of the instance
            return SettingsManager.instance.settings.get(key, default)
        
        logger.warning("SettingsManager.get() called before instance was created.")
        return default

    @staticmethod
    def set(key, value):
        if SettingsManager.instance:
            # Directly access the 'settings' dictionary of the instance
            SettingsManager.instance.settings[key] = value
        else:
            logger.error("SettingsManager.set() called before instance was created. Cannot set value.")


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
        # The translation function might not be available here, so using a plain string.
        self.warning_label.setToolTip("Model not initialized or not installed.")

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
