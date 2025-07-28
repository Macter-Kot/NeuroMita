from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit, QFrame, QButtonGroup, QRadioButton
from PyQt6.QtGui import QFont
from core.events import get_event_bus, Events
import sys

class EULAWidget(QWidget):
    accepted = pyqtSignal()
    rejected = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.event_bus = get_event_bus()
        self.setObjectName("EULAWidget")
        self.current_language = "ru"
        self.setup_ui()
        
    def setup_ui(self):
        self.setStyleSheet("""
            #EULAWidget {
                background-color: transparent;
            }
            #EULAContainer {
                background-color: #2a2a2a;
                border: 2px solid #5a5a5a;
                border-radius: 12px;
            }
            #EULATitle {
                font-size: 18px;
                font-weight: bold;
                color: #ffffff;
                padding: 10px;
            }
            #EULAText {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 12px;
                font-size: 12px;
                line-height: 1.4;
            }
            QPushButton {
                min-width: 120px;
                min-height: 35px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
                border: none;
            }
            #AcceptButton {
                background-color: #4a7c59;
                color: white;
            }
            #AcceptButton:hover {
                background-color: #5d8f6f;
            }
            #RejectButton {
                background-color: #d32f2f;
                color: white;
            }
            #RejectButton:hover {
                background-color: #e53935;
            }
            QRadioButton {
                color: #e0e0e0;
                font-size: 12px;
                padding: 5px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 2px solid #666666;
                background-color: #2a2a2a;
            }
            QRadioButton::indicator:checked {
                background-color: #6a4c93;
                border: 2px solid #6a4c93;
            }
            QFrame#Separator {
                background-color: #5a5a5a;
                max-height: 2px;
                border-radius: 1px;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("EULAContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container_layout.setSpacing(15)
        
        self.setMinimumSize(700, 600)
        self.setMaximumSize(900, 700)
        
        header_layout = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName("EULATitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.title_label)
        
        container_layout.addLayout(header_layout)
        
        separator = QFrame()
        separator.setObjectName("Separator")
        separator.setFrameShape(QFrame.Shape.HLine)
        container_layout.addWidget(separator)
        
        lang_layout = QHBoxLayout()
        lang_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lang_layout.setSpacing(15)
        
        self.lang_group = QButtonGroup()
        self.ru_radio = QRadioButton("Русский")
        self.ru_radio.setChecked(True)
        self.en_radio = QRadioButton("English")
        
        self.lang_group.addButton(self.ru_radio, 0)
        self.lang_group.addButton(self.en_radio, 1)
        self.lang_group.buttonClicked.connect(self._on_language_changed)
        
        lang_layout.addWidget(self.ru_radio)
        lang_layout.addWidget(self.en_radio)
        container_layout.addLayout(lang_layout)
        
        self.text_edit = QTextEdit()
        self.text_edit.setObjectName("EULAText")
        self.text_edit.setReadOnly(True)
        container_layout.addWidget(self.text_edit, 1)
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        
        self.reject_button = QPushButton()
        self.reject_button.setObjectName("RejectButton")
        self.reject_button.clicked.connect(self._on_reject)
        button_layout.addWidget(self.reject_button)
        
        button_layout.addStretch()
        
        self.accept_button = QPushButton()
        self.accept_button.setObjectName("AcceptButton")
        self.accept_button.clicked.connect(self._on_accept)
        button_layout.addWidget(self.accept_button)
        
        container_layout.addLayout(button_layout)
        
        main_layout.addWidget(container)
        
        self._update_texts()
        
    def _on_language_changed(self):
        self.current_language = "ru" if self.ru_radio.isChecked() else "en"
        self._update_texts()
        
    def _update_texts(self):
        if self.current_language == "ru":
            self.title_label.setText("Лицензионное соглашение пользователя")
            self.reject_button.setText("Отклонить")
            self.accept_button.setText("Принять")
            self.text_edit.setPlainText(self._get_russian_text())
        else:
            self.title_label.setText("End User License Agreement")
            self.reject_button.setText("Reject")
            self.accept_button.setText("Accept")
            self.text_edit.setPlainText(self._get_english_text())
            
    def _get_russian_text(self):
        return """ЛИЦЕНЗИОННОЕ СОГЛАШЕНИЕ КОНЕЧНОГО ПОЛЬЗОВАТЕЛЯ

Пожалуйста, внимательно прочитайте это соглашение перед использованием программы NeuroMita.

1. ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ
Разработчики NeuroMita НЕ НЕСУТ ОТВЕТСТВЕННОСТИ за контент, генерируемый искусственным интеллектом. Весь контент создается алгоритмами машинного обучения и может содержать неточности, ошибки или неприемлемый материал.

2. ОГРАНИЧЕНИЯ ИСПОЛЬЗОВАНИЯ
Вам ЗАПРЕЩАЕТСЯ использовать NeuroMita для:
• Создания незаконного, вредоносного или оскорбительного контента
• Нарушения авторских прав или интеллектуальной собственности
• Распространения дезинформации или вредоносной информации
• Любых действий, нарушающих законодательство вашей страны
• Создания контента, который может причинить вред людям

3. КОНФИДЕНЦИАЛЬНОСТЬ И ДАННЫЕ
• NeuroMita может сохранять историю чатов локально на вашем устройстве
• При использовании внешних API ваши данные могут передаваться третьим сторонам (OpenAI, Anthropic и др.)
• Мы не собираем персональные данные без вашего явного согласия
• Вы несете ответственность за безопасность своих API ключей

4. ОТКАЗ ОТ ГАРАНТИЙ
Программа предоставляется "КАК ЕСТЬ" без каких-либо гарантий, явных или подразумеваемых. Разработчики не гарантируют:
• Бесперебойную или безошибочную работу программы
• Точность или достоверность генерируемого контента
• Совместимость со всеми системами и конфигурациями

5. ОГРАНИЧЕНИЕ ОТВЕТСТВЕННОСТИ
Ни при каких обстоятельствах разработчики не несут ответственности за:
• Любые прямые, косвенные или случайные убытки
• Потерю данных или прибыли
• Ущерб, возникший в результате использования или невозможности использования программы

6. ИЗМЕНЕНИЯ И ОБНОВЛЕНИЯ
Разработчики оставляют за собой право изменять условия данного соглашения в будущих версиях программы.

7. ПРИМЕНИМОЕ ПРАВО
Данное соглашение регулируется международным правом в области программного обеспечения.

НАЖИМАЯ "ПРИНЯТЬ", ВЫ ПОДТВЕРЖДАЕТЕ, ЧТО:
• Прочитали и поняли все условия соглашения
• Принимаете на себя всю ответственность за использование программы
• Не будете использовать программу в незаконных целях"""
        
    def _get_english_text(self):
        return """END USER LICENSE AGREEMENT

Please read this agreement carefully before using NeuroMita.

1. DISCLAIMER
The developers of NeuroMita ARE NOT RESPONSIBLE for content generated by artificial intelligence. All content is created by machine learning algorithms and may contain inaccuracies, errors, or inappropriate material.

2. USAGE RESTRICTIONS
You are PROHIBITED from using NeuroMita to:
• Create illegal, harmful, or offensive content
• Violate copyrights or intellectual property
• Spread misinformation or harmful information
• Engage in any activities that violate the laws of your country
• Create content that may harm individuals

3. PRIVACY AND DATA
• NeuroMita may save chat history locally on your device
• When using external APIs, your data may be transmitted to third parties (OpenAI, Anthropic, etc.)
• We do not collect personal data without your explicit consent
• You are responsible for the security of your API keys

4. DISCLAIMER OF WARRANTIES
The software is provided "AS IS" without any warranties, express or implied. The developers do not guarantee:
• Uninterrupted or error-free operation of the software
• Accuracy or reliability of generated content
• Compatibility with all systems and configurations

5. LIMITATION OF LIABILITY
Under no circumstances shall the developers be liable for:
• Any direct, indirect, or incidental damages
• Loss of data or profits
• Damage arising from the use or inability to use the software

6. CHANGES AND UPDATES
The developers reserve the right to modify the terms of this agreement in future versions of the software.

7. GOVERNING LAW
This agreement is governed by international software law.

BY CLICKING "ACCEPT", YOU CONFIRM THAT:
• You have read and understood all terms of the agreement
• You accept full responsibility for using the software
• You will not use the software for illegal purposes"""
        
    def _on_accept(self):
        self.event_bus.emit(Events.Settings.SAVE_SETTING, {
            'key': 'EULA_ACCEPTED',
            'value': True
        })
        self.accepted.emit()
        
    def _on_reject(self):
        self.rejected.emit()
        sys.exit(0)