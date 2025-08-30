from PyQt6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget, QScrollArea
from PyQt6.QtCore import Qt

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