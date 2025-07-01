from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QComboBox, 
                             QCheckBox, QPushButton, QTextEdit, QSizePolicy)
from PyQt6.QtCore import Qt

from Logger import logger
from SettingsManager import CollapsibleSection
from utils import getTranslationVariant as _

def create_settings_section(gui, parent_layout, title, settings_config):
    """Создает сворачиваемую секцию с набором настроек."""
    section = CollapsibleSection(title, gui)
    parent_layout.addWidget(section)
    
    for config in settings_config:
        widget = None
        widget_type = config.get('type')
        
        if widget_type == 'button_group':
            widget = create_button_group(gui, section.content_frame, config.get('buttons', []))
        else:
            widget = create_setting_widget(
                gui=gui,
                parent=section.content_frame,
                label=config.get('label'),
                setting_key=config.get('key', ''),
                widget_type=widget_type,
                options=config.get('options'),
                default=config.get('default', ''),
                default_checkbutton=config.get('default_checkbutton', False),
                validation=config.get('validation'),
                tooltip=config.get('tooltip'),
                hide=config.get('hide', False),
                command=config.get('command'),
                widget_name=config.get('widget_name', config.get('key'))
            )
        
        if widget:
            section.add_widget(widget)
    
    return section

def create_button_group(gui, parent, buttons_config):
    """Создает горизонтальную группу кнопок."""
    frame = QWidget(parent)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.setSpacing(10)
    
    for btn_config in buttons_config:
        button = QPushButton(btn_config['label'])
        if 'command' in btn_config:
            button.clicked.connect(btn_config['command'])
        layout.addWidget(button)
        
    return frame

def create_setting_widget(gui, parent, label, setting_key='', widget_type='entry',
                          options=None, default='', default_checkbutton=False, validation=None, tooltip=None,
                          hide=False, command=None, widget_name=None, **kwargs):
    """Создает один виджет настройки (строку) с меткой и элементом управления."""
    # ИЗМЕНЕНИЕ: Эта проверка удалена, так как виджет должен создаваться в любом случае.
    # if hide:
    #     return None
    
    if setting_key and gui.settings.get(setting_key) is None:
        initial_value = default_checkbutton if widget_type == 'checkbutton' else default
        gui.settings.set(setting_key, initial_value)

    frame = QWidget(parent)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.setSpacing(10)

    if widget_type in ['button', 'text']:
        if widget_type == 'button':
            widget = QPushButton(label)
            if command: widget.clicked.connect(command)
            button_layout = QHBoxLayout()
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_layout.addStretch()
            button_layout.addWidget(widget)
            button_layout.addStretch()
            layout.addLayout(button_layout)
        else:
            widget = QLabel(label)
            widget.setObjectName("SeparatorLabel")
            layout.addWidget(widget)
        if widget_name and widget is not None:
            setattr(gui, widget_name, widget)
        return frame

    lbl = QLabel(label)
    lbl.setMinimumWidth(140)
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    
    widget = None
    
    if widget_type == 'checkbutton':
        widget = QCheckBox()
        widget.setChecked(bool(gui.settings.get(setting_key, default_checkbutton)))
        
        def save_check_state(state):
            value = bool(state == Qt.CheckState.Checked.value)
            gui._save_setting(setting_key, value)
            if command: command(value)
            
        widget.stateChanged.connect(save_check_state)
        
        layout.addWidget(lbl)
        layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
    else:
        layout.addWidget(lbl)
        if widget_type == 'entry':
            widget = QLineEdit(str(gui.settings.get(setting_key, default)))
            
            # ИЗМЕНЕНИЕ: Устанавливаем режим пароля, если hide=True
            if hide:
                widget.setEchoMode(QLineEdit.EchoMode.Password)

            def save_entry_text():
                if validation and not validation(widget.text()):
                    widget.setText(str(gui.settings.get(setting_key, default)))
                    return
                if not (hide and widget.text() == ''):
                     gui._save_setting(setting_key, widget.text())
                if command: command(widget.text())

            widget.editingFinished.connect(save_entry_text)
            
        elif widget_type == 'combobox':
            widget = QComboBox()
            if options: widget.addItems([str(o) for o in options])
            widget.setCurrentText(str(gui.settings.get(setting_key, default)))
            
            def save_combo_text(text):
                gui._save_setting(setting_key, text)
                if command: command()
            
            widget.currentTextChanged.connect(save_combo_text)
        
        if widget:
            layout.addWidget(widget, 1)

    if tooltip and widget:
        widget.setToolTip(tooltip)
        
    if widget_name and widget is not None:
        setattr(gui, widget_name, widget)
        setattr(gui, f"{widget_name}_frame", frame)

    return frame