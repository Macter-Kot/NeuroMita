from PyQt6.QtWidgets import QPushButton, QApplication
from PyQt6.QtCore import QSize
import qtawesome as qta

class SettingsIconButton(QPushButton):
    def __init__(self, icon_name, tooltip_text, parent=None):
        super().__init__(parent)
        self.setIcon(qta.icon(icon_name, color='#dcdcdc'))
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