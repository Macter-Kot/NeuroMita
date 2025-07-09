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
        self.dot_size = 4
        self.dot_spacing = 6
        self.current_dot = 0
        self.animation_step = 0  # Для плавной анимации размера
        
        # Таймер для анимации
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._animate_dots)
        
        # Таймер для плавной анимации размера точек
        self.smooth_timer = QTimer()
        self.smooth_timer.timeout.connect(self._smooth_animation)
        
    def _animate_dots(self):
        """Анимация переключения активной точки"""
        self.current_dot = (self.current_dot + 1) % self.dot_count
        self.animation_step = 0
        self.update()
        
    def _smooth_animation(self):
        """Плавная анимация размера активной точки"""
        self.animation_step += 1
        self.update()
        if self.animation_step >= 10:  # Цикл анимации
            self.animation_step = 0
            
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Начальная позиция для центрирования точек
        total_width = self.dot_count * self.dot_size + (self.dot_count - 1) * self.dot_spacing
        start_x = (self.width() - total_width) // 2
        y = self.height() // 2
        
        for i in range(self.dot_count):
            x = start_x + i * (self.dot_size + self.dot_spacing)
            
            # Вычисляем размер и прозрачность для плавной анимации
            if i == self.current_dot:
                # Активная точка пульсирует
                scale_factor = 1.0 + 0.5 * abs(5 - self.animation_step) / 5.0
                size = int(self.dot_size * scale_factor)
                color = QColor("#7a7a7a")  # Более приглушенный цвет
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(x - size//2 + self.dot_size//2, 
                                   y - size//2, size, size)
            else:
                # Неактивные точки
                painter.setBrush(QBrush(QColor("#4a4a4a")))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(x, y - self.dot_size//2, 
                                   self.dot_size, self.dot_size)
    
    def stop_animation(self):
        """Остановить анимацию"""
        self.animation_timer.stop()
        self.smooth_timer.stop()
        
    def start_animation(self):
        """Запустить анимацию"""
        self.animation_timer.start(600)  # Переключение точек каждые 600мс
        self.smooth_timer.start(60)      # Плавная анимация 60мс (16 FPS)


class MitaStatusWidget(QWidget):
    """Виджет статуса Миты - overlay поверх чата"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_state = "idle"
        self.is_animating = False
        self.setup_ui()
        self.hide()  # Скрыт по умолчанию
        
    def setup_ui(self):
        self.setObjectName("MitaStatusWidget")
        self.setFixedHeight(40)  # Фиксированная высота
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        # Основной layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # Анимированные точки
        self.dots_widget = AnimatedDots()
        layout.addWidget(self.dots_widget)
        
        # Текст статуса
        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # Эффект прозрачности для анимации
        self.opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)
        
        # Анимация появления/исчезновения
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(500)  # Увеличили длительность
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Применяем стили
        self._apply_normal_style()
        
    def _apply_normal_style(self):
        """Применить обычный стиль"""
        self.setStyleSheet("""
            #MitaStatusWidget {
                background-color: rgba(45, 45, 45, 200);
                border: 1px solid rgba(74, 74, 74, 150);
                border-radius: 8px;
                margin: 0px;
            }
        """)
        self.status_label.setStyleSheet("""
            QLabel {
                color: rgba(160, 160, 160, 180);
                font-size: 10pt;
                background: transparent;
                font-weight: 400;
            }
        """)
        
    def _apply_error_style(self):
        """Применить стиль ошибки"""
        self.setStyleSheet("""
            #MitaStatusWidget {
                background-color: rgba(74, 40, 40, 220);
                border: 1px solid rgba(138, 48, 48, 180);
                border-radius: 8px;
                margin: 0px;
            }
        """)
        self.status_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 107, 107, 200);
                font-size: 10pt;
                font-weight: 500;
                background: transparent;
            }
        """)
        
    def _apply_success_style(self):
        """Применить стиль успеха"""
        self.setStyleSheet("""
            #MitaStatusWidget {
                background-color: rgba(42, 56, 42, 220);
                border: 1px solid rgba(74, 106, 74, 180);
                border-radius: 8px;
                margin: 0px;
            }
        """)
        self.status_label.setStyleSheet("""
            QLabel {
                color: rgba(76, 175, 80, 200);
                font-size: 10pt;
                font-weight: 500;
                background: transparent;
            }
        """)
        
    def _disconnect_fade_signal(self):
        """Безопасно отключить сигнал finished от анимации"""
        try:
            self.fade_animation.finished.disconnect()
        except TypeError:
            # Сигнал уже отключен или не был подключен
            pass
        
    def show_thinking(self, character_name="Мита"):
        """Показать статус 'думает'"""
        if self.current_state == "thinking" and self.isVisible() and self.opacity_effect.opacity() > 0.5:
            return  # Уже показываем
            
        print(f"[DEBUG] show_thinking вызван для {character_name}")
        
        self.current_state = "thinking"
        self.is_animating = False
        
        # Останавливаем все анимации и таймеры
        self.fade_animation.stop()
        self._disconnect_fade_signal()
        
        self._apply_normal_style()
        self.status_label.setText(f"{character_name} думает...")
        self.dots_widget.show()
        self.dots_widget.start_animation()
        
        # Показываем сразу и устанавливаем opacity = 0
        self.show()
        self.raise_()
        self.opacity_effect.setOpacity(0.0)
        
        # Запускаем анимацию появления
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()
        
    def show_error(self, error_message="Произошла ошибка"):
        """Показать статус ошибки"""
        print(f"[DEBUG] show_error вызван: {error_message}")
        
        self.current_state = "error"
        self.is_animating = False
        
        # Останавливаем все анимации
        self.fade_animation.stop()
        self._disconnect_fade_signal()
        
        self._apply_error_style()
        self.status_label.setText(f"⚠ {error_message}")
        self.dots_widget.hide()
        self.dots_widget.stop_animation()
        
        # Показываем сразу и устанавливаем opacity = 0
        self.show()
        self.raise_()
        self.opacity_effect.setOpacity(0.0)
        
        # Запускаем анимацию появления
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()
        
        # Автоматически скрыть через 5 секунд
        QTimer.singleShot(5000, self.hide_animated)
        
    def show_success(self, message="Готово"):
        """Показать статус успеха"""
        print(f"[DEBUG] show_success вызван: {message}")
        
        self.current_state = "success"
        self.is_animating = False
        
        # Останавливаем все анимации
        self.fade_animation.stop()
        self._disconnect_fade_signal()
        
        self._apply_success_style()
        self.status_label.setText(f"✓ {message}")
        self.dots_widget.hide()
        self.dots_widget.stop_animation()
        
        # Показываем сразу и устанавливаем opacity = 0
        self.show()
        self.raise_()
        self.opacity_effect.setOpacity(0.0)
        
        # Запускаем анимацию появления
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()
        
        # Автоматически скрыть через 2 секунды
        QTimer.singleShot(2000, self.hide_animated)
        
    def hide_animated(self):
        """Скрыть с анимацией"""
        if self.current_state == "idle" or self.is_animating:
            print(f"[DEBUG] hide_animated игнорирован - состояние: {self.current_state}, анимация: {self.is_animating}")
            return
            
        print(f"[DEBUG] hide_animated начат - состояние: {self.current_state}, opacity: {self.opacity_effect.opacity()}")
        
        self.current_state = "idle"
        self.is_animating = True
        self.dots_widget.stop_animation()
        
        # Останавливаем текущую анимацию
        self.fade_animation.stop()
        self._disconnect_fade_signal()
        
        # Запускаем анимацию скрытия
        current_opacity = self.opacity_effect.opacity()
        self.fade_animation.setStartValue(current_opacity)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.finished.connect(self._on_hide_finished)
        
        print(f"[DEBUG] Запускаем анимацию скрытия с {current_opacity} до 0.0")
        self.fade_animation.start()
        
    def _on_hide_finished(self):
        """Вызывается после завершения анимации скрытия"""
        print("[DEBUG] _on_hide_finished - скрываем виджет")
        self.hide()
        self.is_animating = False
        self._disconnect_fade_signal()