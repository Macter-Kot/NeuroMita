from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt
from pathlib import Path

def create_ffmpeg_install_popup(parent):
    dialog = QDialog(parent)
    dialog.setWindowTitle("FFmpeg")
    dialog.setFixedSize(300, 100)
    layout = QVBoxLayout(dialog)
    label = QLabel("Идет установка FFmpeg...\nПожалуйста, подождите.")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(label)
    return dialog

def show_ffmpeg_error_popup(parent):
    error_dialog = QDialog(parent)
    error_dialog.setWindowTitle("Ошибка установки FFmpeg")
    error_dialog.setModal(True)
    
    layout = QVBoxLayout(error_dialog)
    
    message = (
        "Не удалось автоматически установить FFmpeg.\n\n"
        "Он необходим для некоторых функций программы (например, обработки аудио).\n\n"
        "Пожалуйста, скачайте FFmpeg вручную с официального сайта:\n"
        "https://ffmpeg.org/download.html\n\n"
        "Распакуйте архив и поместите файл 'ffmpeg.exe' в папку программы:\n"
        f"{Path('.').resolve()}"
    )
    
    label = QLabel(message)
    layout.addWidget(label)
    
    ok_button = QPushButton("OK")
    ok_button.clicked.connect(error_dialog.accept)
    layout.addWidget(ok_button, alignment=Qt.AlignmentFlag.AlignCenter)
    
    error_dialog.exec()