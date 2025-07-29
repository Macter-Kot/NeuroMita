import logging
import colorlog
import os
import sys

# -----------------------------------------------------------------------------
# Фильтр: пропускаем только логи из проекта; в PyInstaller ничего не режем
# -----------------------------------------------------------------------------
class ProjectFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.project_path = os.path.dirname(os.path.abspath(__file__))

    def filter(self, record):
        if hasattr(sys, '_MEIPASS'):        # запущено из exe
            return True
        return record.pathname.startswith(self.project_path)
    
class LocationFilter(logging.Filter):
    def filter(self, record):
        record.location = f"[{record.filename}:{record.lineno}]"
        return True

# -----------------------------------------------------------------------------
# Логгер
# -----------------------------------------------------------------------------
logger = colorlog.getLogger(__name__)
logger.setLevel(logging.INFO)

# -----------------------------------------------------------------------------
# Консоль — без даты, без относительного пути
# -----------------------------------------------------------------------------
console_handler = colorlog.StreamHandler()
console_handler.setFormatter(
    colorlog.ColoredFormatter(
        '%(log_color)s%(levelname)-8s %(location)-30s | %(message)s',
        log_colors={
            'INFO':     'white',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        },
    )
)
console_handler.addFilter(ProjectFilter())
console_handler.addFilter(LocationFilter())

# -----------------------------------------------------------------------------
# Файл — с датой
# -----------------------------------------------------------------------------
file_handler = logging.FileHandler('NeuroMitaLogs.log', encoding='utf-8')
file_handler.setFormatter(
    logging.Formatter(
        '%(asctime)s - %(levelname)-8s '
        '[%(filename)s:%(lineno)d - %(funcName)s] '
        '%(message)s'
    )
)
file_handler.addFilter(ProjectFilter())

# -----------------------------------------------------------------------------
# Регистрируем обработчики
# -----------------------------------------------------------------------------
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.propagate = False