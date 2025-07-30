import logging
import colorlog
import os
import sys

# -----------------------------------------------------------------------------
# Добавляем кастомные уровни логирования
# -----------------------------------------------------------------------------
NOTIFY_LEVEL = 25  # между INFO (20) и WARNING (30)
SUCCESS_LEVEL = 35  # между WARNING (30) и ERROR (40)

logging.addLevelName(NOTIFY_LEVEL, "NOTIFY")
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

# Добавляем метод notify к классу Logger
def notify(self, message, *args, **kwargs):
    if self.isEnabledFor(NOTIFY_LEVEL):
        self._log(NOTIFY_LEVEL, message, args, **kwargs)

# Добавляем метод success к классу Logger
def success(self, message, *args, **kwargs):
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kwargs)

# Привязываем методы к классу Logger
logging.Logger.notify = notify
logging.Logger.success = success

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
            'NOTIFY':   'light_purple',    # Розовый
            'WARNING':  'yellow',
            'SUCCESS':  'light_green',     # Лаймовый
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

# -----------------------------------------------------------------------------
# Пример использования (можно удалить)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Запуск программы")
    logger.notify("Важное уведомление для пользователя")
    logger.warning("Предупреждение о потенциальной проблеме")
    logger.success("Операция завершена успешно!")
    logger.error("Произошла ошибка")