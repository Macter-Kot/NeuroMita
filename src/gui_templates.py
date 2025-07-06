from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QComboBox, 
                             QCheckBox, QPushButton, QTextEdit, QSizePolicy)
from PyQt6.QtCore import Qt

from main_logger import logger
from settings_manager import CollapsibleSection, InnerCollapsibleSection
from utils import getTranslationVariant as _

def create_settings_section(gui, parent_layout, title, cfg_list, *, icon_name=None):
    root = CollapsibleSection(title, gui, icon_name=icon_name)
    parent_layout.addWidget(root)
    current_sub = None

    for cfg in cfg_list:
        t = cfg.get('type')

        if t == 'subsection':
            current_sub = InnerCollapsibleSection(cfg.get('label', ''), gui)
            root.add_widget(current_sub)
            continue

        if t == 'end':
            current_sub = None
            continue

        if t == 'text':
            lbl = QLabel(cfg['label'])
            lbl.setObjectName('SeparatorLabel')
            (current_sub or root).add_widget(lbl)
            continue

        parent = (current_sub or root).content

        if t == 'button_group':
            w = create_button_group(gui, parent, cfg.get('buttons', []))
        else:
            w = create_setting_widget(
                gui=gui, parent=parent, label=cfg.get('label'),
                setting_key=cfg.get('key', ''), widget_type=t,
                options=cfg.get('options'), default=cfg.get('default', ''),
                default_checkbutton=cfg.get('default_checkbutton', False),
                validation=cfg.get('validation'), tooltip=cfg.get('tooltip'),
                hide=cfg.get('hide', False), command=cfg.get('command'),
                widget_name=cfg.get('widget_name', cfg.get('key')),
            )
        if w:
            (current_sub or root).add_widget(w)

    return root

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

    
    if setting_key and gui.settings.get(setting_key) is None:
        initial_value = default_checkbutton if widget_type == 'checkbutton' else default
        gui.settings.set(setting_key, initial_value)

    if widget_type in ('textarea', 'textedit'):
        # --- контейнер для одной настройки ---
        frame = QWidget(parent)
        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(0, 2, 0, 2)
        vlay.setSpacing(4)

        lbl = QLabel(label)
        lbl.setWordWrap(True)  # длинные подписи переносятся
        vlay.addWidget(lbl)

        widget = QTextEdit()
        widget.setPlainText(str(gui.settings.get(setting_key, default)))

        widget.setMinimumHeight(50)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Expanding)

        vlay.addWidget(widget)

        # сигналы сохранения
        widget.textChanged.connect(
            lambda w=widget: gui._save_setting(setting_key, w.toPlainText())
        )

        if widget_name:
            setattr(gui, widget_name, widget)
            setattr(gui, f"{widget_name}_frame", frame)

        return frame

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