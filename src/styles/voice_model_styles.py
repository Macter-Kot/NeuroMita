# styles/voice_model_styles.py

def get_stylesheet():
    return """
        /* ----- General ----- */
        QWidget {
            background-color: #1e1e1e;
            color: #dcdcdc;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 9pt;
        }
        
        QMainWindow, QDialog {
            background-color: #1e1e1e;
        }
        
        QFrame {
            border: none;
            background-color: #1e1e1e;
        }

        /* ----- Description Frame ----- */
        QFrame#DescriptionFrame {
            background-color: #252525;
            border: none;
        }

        /* ----- Model Panel ----- */
        QFrame#ModelPanel {
            background-color: #2a2a2e;
            border: none;
        }

        /* ----- Voice Settings Sections ----- */
        VoiceCollapsibleSection {
            background-color: #1e1e1e;
            border: none;
        }
        
        QFrame#VoiceCollapsibleHeader {
            background-color: #252525;
        }
        
        QFrame#VoiceCollapsibleContent {
            background-color: #1e1e1e;
        }
        
        QFrame#VoiceSettingLabel {
            background-color: #252525;
        }
        
        QFrame#VoiceSettingWidget {
            background-color: #1e1e1e;
        }

        /* ----- QTextEdit & QLineEdit ----- */
        QTextEdit, QLineEdit {
            background-color: #3c3c3c;
            color: white;
            border: 1px solid #333333;
            /* ↓ было 5px 8px;  стало 3px 8px ↓ */
            padding: 3px 8px;
            font-family: "Segoe UI";
            font-size: 9pt;
            border-radius: 0px;
        }
        
        QTextEdit:focus, QLineEdit:focus {
            border: 1px solid #007acc;
            background-color: #3c3c3c;
            outline: none;
        }
        
        QTextEdit:disabled, QLineEdit:disabled {
            background-color: #303030;
            color: #888888;
        }

        /* ----- QComboBox ----- */
        QComboBox {
            background-color: #3c3c3c;
            color: white;
            border: 1px solid #333333;
            /* ↓ было 6px 8px;  стало 3px 8px ↓ */
            padding: 3px 8px;
            font-family: "Segoe UI";
            font-size: 9pt;
            border-radius: 0px;
        }
        
        QComboBox:focus, QComboBox:hover {
            border: 1px solid #007acc;
        }
        
        QComboBox:disabled {
            background-color: #303030;
            color: #888888;
        }
        
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        
        QComboBox::down-arrow {
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid white;
            width: 0px;
            height: 0px;
            margin-right: 4px;
        }
        
        QComboBox::down-arrow:disabled {
            border-top: 6px solid #888888;
        }
        
        QComboBox QAbstractItemView {
            background-color: #3c3c3c;
            color: white;
            selection-background-color: #007acc;
            selection-color: white;
            border: 1px solid #333333;
        }

        /* ----- QPushButton ----- */
        QPushButton {
            font-family: "Segoe UI";
            font-size: 9pt;
            font-weight: bold;
            padding: 8px 20px;
            border: none;
            border-radius: 0px;
        }
        
        /* Primary button (Save) */
        QPushButton#PrimaryButton {
            background-color: #3c3cac;
            color: white;
        }
        QPushButton#PrimaryButton:hover {
            background-color: #4a4acb;
        }
        QPushButton#PrimaryButton:pressed {
            background-color: #5a5adb;
        }
        
        /* Secondary button (Install) */
        QPushButton#SecondaryButton {
            background-color: #555555;
            color: white;
        }
        QPushButton#SecondaryButton:hover {
            background-color: #666666;
        }
        QPushButton#SecondaryButton:pressed {
            background-color: #777777;
        }
        QPushButton#SecondaryButton:disabled {
            background-color: #555555;
            color: #999999;
        }
        
        /* Danger button (Uninstall) */
        QPushButton#DangerButton {
            background-color: #ac3939;
            color: white;
        }
        QPushButton#DangerButton:hover {
            background-color: #bf4a4a;
        }
        QPushButton#DangerButton:pressed {
            background-color: #d05a5a;
        }
        
        /* Default button (Close) */
        QPushButton {
            background-color: #3c3c3c;
            color: white;
        }
        QPushButton:hover {
            background-color: #555555;
        }
        QPushButton:pressed {
            background-color: #666666;
        }

        /* ----- QLabel ----- */
        QLabel {
            background-color: transparent;
            color: white;
            font-family: "Segoe UI";
            font-size: 9pt;
        }
        
        /* Specific label styles */
        QLabel#CollapsibleArrow {
            color: white;
            font-size: 8pt;
        }
        
        QLabel#CollapsibleTitle {
            color: white;
            font-weight: bold;
            font-size: 9pt;
        }

        /* ----- QCheckBox ----- */
        QCheckBox {
            spacing: 5px;
            font-family: "Segoe UI";
            font-size: 9pt;
        }
        
        QCheckBox::indicator {
            width: 12px;
            height: 12px;
            background-color: #3c3c3c;
            border: 1px solid #444444;
            border-radius: 0px;
        }
        
        QCheckBox::indicator:checked {
            background-color: #007acc;
            border: 1px solid #007acc;
            border-radius: 0px;
        }
        
        QCheckBox::indicator:disabled {
            background-color: #303030;
            border: 1px solid #444444;
        }
        
        QCheckBox::indicator:checked:disabled {
            background-color: #303030;
            border: 1px solid #444444;
        }

        /* ----- QScrollArea & ScrollBar ----- */
        QScrollArea {
            background-color: #1e1e1e;
            border: none;
        }
        
        QScrollBar:vertical {
            background-color: #1e1e1e;
            width: 12px;
            border: none;
        }
        
        QScrollBar::handle:vertical {
            background-color: #555555;
            min-height: 20px;
            border-radius: 0px;
        }
        
        QScrollBar::handle:vertical:hover {
            background-color: #6a6a6a;
        }
        
        QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
            height: 0px;
        }
        
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
        
        QScrollBar:horizontal {
            background-color: #1e1e1e;
            height: 12px;
            border: none;
        }
        
        QScrollBar::handle:horizontal {
            background-color: #555555;
            min-width: 20px;
            border-radius: 0px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background-color: #6a6a6a;
        }
        
        QScrollBar::sub-line:horizontal, QScrollBar::add-line:horizontal {
            width: 0px;
        }
        
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
            background: none;
        }

        /* ----- Status Labels ----- */
        QLabel[status="found"] {
            color: lightgreen;
        }
        
        QLabel[status="notfound"] {
            color: #FF6A6A;
        }
        
        QLabel[status="warning"] {
            color: orange;
            font-weight: bold;
        }
        
        QLabel[status="info"] {
            color: #aaaaaa;
        }
        
        QLabel[status="link"] {
            color: #81d4fa;
            font-weight: bold;
            text-decoration: underline;
        }

        /* ----- QToolTip ----- */
        QToolTip {
            background-color: #ffffe0;
            color: black;
            border: 1px solid black;
            padding: 4px;
            font-family: "Segoe UI";
            font-size: 8pt;
        }

        /* ----- Model Panel Specific ----- */
        QLabel#ModelTitle {
            color: white;
            font-weight: bold;
            font-size: 10pt;
        }
        
        QLabel#ModelInfo {
            color: #b0b0b0;
            font-size: 8pt;
        }
        
        QLabel#ModelWarning {
            color: #FF6A6A;
            font-size: 8pt;
            font-weight: bold;
        }
        
        QLabel#RTXIndicator {
            font-size: 7pt;
            font-weight: bold;
        }
        
        QLabel#WarningIcon {
            color: orange;
            font-size: 9pt;
        }

        /* ----- Placeholder Labels ----- */
        QLabel#PlaceholderLabel {
            color: #aaaaaa;
            font-size: 10pt;
        }
    """