import base64
import json
import os

import qtawesome as qta
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


# ────────────────────────────────────────────────────
# универсальный маленький помощник-иконки
def _angle_icon(kind: str, size: int = 10):
    """kind: 'right' | 'down'"""
    name = 'fa6s.angle-right' if kind == 'right' else 'fa6s.angle-down'
    return qta.icon(name, color='#f0f0f0').pixmap(size, size)
# ────────────────────────────────────────────────────


class CollapsibleSection(QWidget):
    """Внешняя секция"""
    def __init__(self, title, parent=None, *, icon_name=None):
        super().__init__(parent)
        self.is_collapsed = False

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Header
        self.header = QWidget(self, objectName='CollapsibleHeader')

        h = QHBoxLayout(self.header)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(3)

        self.arrow_label = QLabel(self.header)
        self.arrow_pix_right = _angle_icon('right', 10)
        self.arrow_pix_down  = _angle_icon('down',  10)
        self.arrow_label.setPixmap(self.arrow_pix_right)
        self.arrow_label.setFixedWidth(11)

        self.title_label = QLabel(title, self.header, objectName='CollapsibleTitle')
        h.addWidget(self.arrow_label)
        h.addWidget(self.title_label)

        
        h.addStretch()

        if icon_name:
            h.addWidget(self._make_icon(icon_name))
            h.addSpacing(8)

        self.header.mousePressEvent = self.toggle

        # Content
        self.content_frame = QWidget(self, objectName='CollapsibleContent')
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(12, 5, 12, 5)
        self.content = self.content_frame

        v.addWidget(self.header)
        v.addWidget(self.content_frame)
        self.content_frame.hide()

    def _make_icon(self, name):
        # немного юзлесс функция, обрезается и тому подобное.
        lbl = QLabel(self.header)
        lbl.setPixmap(qta.icon(name, color='#f0f0f0').pixmap(15, 15))
        lbl.setFixedSize(18, 18)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl

    def toggle(self, _=None):
        self.is_collapsed = not self.is_collapsed
        self.content_frame.setVisible(not self.is_collapsed)
        self.arrow_label.setPixmap(self.arrow_pix_right if self.is_collapsed else self.arrow_pix_down)

    # --- API ---
    def collapse(self):
        if not self.is_collapsed:
            self.toggle()

    def expand(self):
        if self.is_collapsed:
            self.toggle()
    
    def add_widget(self, w):
        self.content_layout.addWidget(w)
        if self.is_collapsed:
            self.content_frame.hide()



class InnerCollapsibleSection(CollapsibleSection):
    """Под-секция: кликабельный текст без фона"""
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.is_collapsed = False
        self.header.setObjectName('InnerCollapsibleHeader')
        self.header.setStyleSheet('background: transparent;')
        self.arrow_pix_right = _angle_icon('right', 8)
        self.arrow_pix_down  = _angle_icon('down',  8)
        self.arrow_label.setPixmap(self.arrow_pix_right)
        self.header.layout().setSpacing(3)
        self.arrow_label.setFixedWidth(9) 
        self.title_label.setStyleSheet('font-size:9pt;')
        # больший отступ строк внутри подп-секции
        self.content_layout.setContentsMargins(24, 5, 12, 5)