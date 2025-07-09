from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QSize
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QGraphicsOpacityEffect
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

class AnimatedDots(QWidget):
    """Виджет с анимированными точками (как в мессенджерах)"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 20)
        
        # Параметры точек
        self.dot_count = 3
        self.dot_size = 6
        self.dot_spacing = 8
        self.current_dot = 0
        
        # Таймер для анимации
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._animate_dots)
        self.animation_timer.start(400)  # Меняем активную точку каждые 400мс
        
    def _animate_dots(self):
        """Анимация переключения активной точки"""
        self.current_dot = (self.current_dot + 1) % self.dot_count
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Начальная позиция для центрирования точек
        total_width = self.dot_count * self.dot_size + (self.dot_count - 1) * self.dot_spacing
        start_x = (self.width() - total_width) // 2
        y = self.height() // 2
        
        for i in range(self.dot_count):
            x = start_x + i * (self.dot_size + self.dot_spacing)
            
            # Активная точка больше и ярче
            if i == self.current_dot:
                painter.setBrush(QBrush(QColor("#8a2be2")))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(x - 1, y - self.dot_size // 2 - 1, 
                                   self.dot_size + 2, self.dot_size + 2)
            else:
                painter.setBrush(QBrush(QColor("#5a5a5a")))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(x, y - self.dot_size // 2, 
                                   self.dot_size, self.dot_size)
    
    def stop_animation(self):
        """Остановить анимацию"""
        self.animation_timer.stop()
        
    def start_animation(self):
        """Запустить анимацию"""
        self.animation_timer.start(400)


class MitaStatusWidget(QWidget):
    """Виджет статуса Миты"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_state = "idle"
        self.setup_ui()
        self.hide()  # Скрыт по умолчанию
        
    def setup_ui(self):
        self.setObjectName("MitaStatusWidget")
        self.setMaximumHeight(35)
        self.setStyleSheet("""
            #MitaStatusWidget {
                background-color: #383838;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                margin: 4px 0px;
            }
        """)
        
        # Основной layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)
        
        # Анимированные точки
        self.dots_widget = AnimatedDots()
        self.dots_widget.hide()
        layout.addWidget(self.dots_widget)
        
        # Текст статуса
        self.status_label = QLabel()
        self.status_label.setStyleSheet("""
            QLabel {
                color: #dcdcdc;
                font-size: 11pt;
                background: transparent;
            }
        """)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # Эффект прозрачности для анимации
        self.opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0)
        
        # Анимация появления/исчезновения
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(250)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
    def show_thinking(self, character_name="Мита"):
        """Показать статус 'думает'"""
        self.current_state = "thinking"
        self.dots_widget.show()
        self.dots_widget.start_animation()
        self.status_label.setText(f"{character_name} думает...")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #dcdcdc;
                font-size: 11pt;
                background: transparent;
            }
        """)
        self.setStyleSheet("""
            #MitaStatusWidget {
                background-color: #383838;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                margin: 4px 0px;
            }
        """)
        self._show_animated()
        
    def show_error(self, error_message="Произошла ошибка"):
        """Показать статус ошибки"""
        self.current_state = "error"
        self.dots_widget.hide()
        self.dots_widget.stop_animation()
        self.status_label.setText(f"⚠ {error_message}")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #ff6b6b;
                font-size: 11pt;
                font-weight: bold;
                background: transparent;
            }
        """)
        self.setStyleSheet("""
            #MitaStatusWidget {
                background-color: #4a2828;
                border: 1px solid #8a3030;
                border-radius: 6px;
                margin: 4px 0px;
            }
        """)
        self._show_animated()
        
        # Автоматически скрыть через 5 секунд
        QTimer.singleShot(5000, self.hide_animated)
        
    def show_success(self, message="Готово"):
        """Показать статус успеха"""
        self.current_state = "success"
        self.dots_widget.hide()
        self.dots_widget.stop_animation()
        self.status_label.setText(f"✓ {message}")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #4caf50;
                font-size: 11pt;
                font-weight: bold;
                background: transparent;
            }
        """)
        self.setStyleSheet("""
            #MitaStatusWidget {
                background-color: #2a382a;
                border: 1px solid #4a6a4a;
                border-radius: 6px;
                margin: 4px 0px;
            }
        """)
        self._show_animated()
        
        # Автоматически скрыть через 2 секунды
        QTimer.singleShot(2000, self.hide_animated)
        
    def hide_animated(self):
        """Скрыть с анимацией"""
        if self.current_state == "idle":
            return
            
        self.current_state = "idle"
        self.fade_animation.setStartValue(1)
        self.fade_animation.setEndValue(0)
        self.fade_animation.finished.connect(self._on_hide_finished)
        self.fade_animation.start()
        
    def _show_animated(self):
        """Показать с анимацией"""
        if not self.isVisible():
            self.show()
            
        self.fade_animation.setStartValue(self.opacity_effect.opacity())
        self.fade_animation.setEndValue(1)
        self.fade_animation.start()
        
    def _on_hide_finished(self):
        """Вызывается после завершения анимации скрытия"""
        self.hide()
        self.dots_widget.stop_animation()
        self.fade_animation.finished.disconnect()