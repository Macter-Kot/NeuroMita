# pyqt_styles/styles.py

def get_stylesheet():
    return """
        /* ----- General ----- */
        QWidget {
            background-color: #2c2c2c;
            color: #dcdcdc;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 9pt;
            border-radius: 0px;
        }
        QMainWindow {
            background-color: #1e1e1e;
        }
        QDialog {
            background-color: #2c2c2c;
        }
        QFrame {
            border: none;
        }

        /* ----- QTextEdit & QLineEdit (Compact) ----- */
        QTextEdit, QLineEdit {
            background-color: #252525;
            color: #dcdcdc;
            border: 1px solid #4a4a4a;
            padding: 3px 5px;
            border-radius: 3px;
            min-height: 18px; /* Compact height */
        }
        QTextEdit:focus, QLineEdit:focus {
            border: 1px solid #8a2be2;
            background-color: #2a2a2a;
        }
        QTextEdit#DebugWindow {
            font-family: "Consolas", "Courier New", monospace;
            font-size: 8pt;
        }

        /* ----- QComboBox (Compact) ----- */
        QComboBox {
            background-color: #252525;
            color: #dcdcdc;
            border: 1px solid #4a4a4a;
            padding: 2px 5px; /* Reduced vertical padding */
            min-height: 18px; /* Compact height */
            border-radius: 3px;
        }
        QComboBox:focus, QComboBox:on {
            border: 1px solid #8a2be2;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 18px;
            border-left-width: 1px;
            border-left-color: #4a4a4a;
            border-left-style: solid;
        }
        QComboBox::down-arrow {
            image: url(./pyqt_styles/down_arrow.png);
            width: 8px;
            height: 8px;
        }
        QComboBox QAbstractItemView {
            background-color: #252525;
            border: 1px solid #8a2be2;
            selection-background-color: #8a2be2;
            selection-color: #ffffff;
            color: #dcdcdc;
            padding: 4px;
        }

        /* ----- QPushButton ----- */
        QPushButton {
            background-color: #8a2be2;
            color: #ffffff;
            border: none;
            padding: 5px 14px;
            font-weight: bold;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #9932CC;
        }
        QPushButton:pressed {
            background-color: #9400D3;
        }
        QPushButton#CancelButton {
            background-color: #e57373; /* Coral Red */
        }
        QPushButton#CancelButton:hover {
            background-color: #ef5350;
        }
        QPushButton#CancelButton:pressed {
            background-color: #f44336;
        }

        /* ----- QLabel ----- */
        QLabel {
            background-color: transparent;
            padding-top: 2px; /* Align text vertically with inputs */
            padding-bottom: 2px;
        }
        QLabel#TokenCountLabel {
            font-size: 8pt;
            color: #aaaaaa;
            padding: 2px 5px;
        }
        QLabel#SeparatorLabel {
            margin-top: 6px;
            padding-bottom: 3px;
            border-bottom: 1px solid #3a3a3a;
            font-weight: bold;
            color: #e0e0e0;
        }
        #TritonWarningLabel {
            background-color: #400000;
            color: #ffffff;
            font-weight: bold;
            padding: 4px;
            border: 1px solid #800000;
            border-radius: 3px;
        }

        /* ----- QCheckBox ----- */
        QCheckBox {
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 13px;
            height: 13px;
            border: 1px solid #5c5c5c;
            background-color: #252525;
            border-radius: 2px;
        }
        QCheckBox::indicator:checked {
            background-color: #dcdcdc; /* White-ish checkmark */
            image: url(./pyqt_styles/check.png); /* Optional: use an image for the check */
        }
        QCheckBox::indicator:hover {
            border-color: #8a2be2;
        }

        /* ----- QScrollArea & ScrollBar ----- */
        QScrollArea {
            background-color: #2c2c2c;
            border: none;
        }
        QScrollBar:vertical {
            border: none;
            background: #2c2c2c;
            width: 10px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #4a4a4a;
            min-height: 25px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical:hover {
            background: #5a5a5a;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }

        /* ----- Collapsible Section ----- */
        QWidget#CollapsibleHeader {
            background-color: #383838;
            border-radius: 3px;
        }
        QWidget#CollapsibleHeader:hover {
            background-color: #404040;
        }
        QLabel#CollapsibleArrow, QLabel#CollapsibleTitle {
            font-weight: bold;
            color: #f0f0f0;
            padding: 3px;
        }
        QLabel#WarningIcon {
            color: #ffcc00; /* Yellow warning color */
        }
        QWidget#CollapsibleContent {
            background-color: #2c2c2c;
            padding-top: 3px;
        }
        
        /* ----- Loading Dialog ----- */
        QDialog#LoadingDialog {
             border: 1px solid #505050;
             border-radius: 4px;
        }
        QProgressBar {
            border: 1px solid #4a4a4a;
            border-radius: 3px;
            text-align: center;
            background-color: #3a3a3a;
            color: #dcdcdc;
            height: 20px;
        }
        QProgressBar::chunk {
            background-color: #5698d4; /* Blue color from screenshot */
            border-radius: 2px;
        }
    """