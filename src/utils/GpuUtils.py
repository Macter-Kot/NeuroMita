# GpuUtils.py
import subprocess
import platform
import os
import re # Импортируем модуль для регулярных выражений
from Logger import logger

def check_gpu_provider():
    """
    Проверяет вендора GPU (NVIDIA или AMD) в системе Windows.
    
    Пытается сначала использовать `wmic`, затем fallback на PowerShell.
    
    Возвращает:
        str: "NVIDIA", "AMD" или None, если не удалось определить.
    """
    if platform.system() != "Windows":
        logger.info("Предупреждение: Определение вендора GPU реализовано только для Windows.")
        return None

    amd_test = os.environ.get('TEST_AS_AMD', '').upper() == 'TRUE'

    def parse_output(output):
        """Вспомогательная функция для анализа вывода"""
        if "NVIDIA" in output:
            return "NVIDIA" if not amd_test else "AMD"
        elif "AMD" in output or "Radeon" in output:
            return "AMD"
        return None

    try:
        # Первая попытка — через wmic
        output = subprocess.check_output(
            "wmic path win32_VideoController get name",
            shell=True, text=True, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE
        ).strip()

        gpu_vendor = parse_output(output)
        if gpu_vendor:
            return gpu_vendor

        logger.info(f"Не удалось определить вендора GPU из вывода WMIC:\n{output}")

    except FileNotFoundError:
        logger.info("Команда 'wmic' не найдена. Пробуем альтернативу через PowerShell...")
    except subprocess.CalledProcessError as e:
        logger.info(f"Ошибка при выполнении команды wmic: {e}")
        logger.info(f"Stderr: {e.stderr}")
    except Exception as e:
        logger.info(f"Неожиданная ошибка при выполнении wmic: {e}")

    # Альтернатива через PowerShell
    try:
        command = [
            "powershell",
            "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"
        ]
        output = subprocess.check_output(
            command, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
        ).strip()

        gpu_vendor = parse_output(output)
        if gpu_vendor:
            return gpu_vendor

        logger.info(f"Не удалось определить вендора GPU из вывода PowerShell:\n{output}")

    except Exception as e:
        logger.info(f"Ошибка при выполнении PowerShell-команды: {e}")

    return None

def get_cuda_devices():
    cuda_devices = []
    try:
        # logger.info("Попытка импорта PyTorch для определения CUDA устройств...") # Убрал вывод
        import torch
        # logger.info(f"PyTorch импортирован. Версия: {torch.__version__}") # Убрал вывод

        if torch.cuda.is_available():
            # logger.info("CUDA доступен в PyTorch.") # Убрал вывод
            device_count = torch.cuda.device_count()
            # logger.info(f"Найдено CUDA устройств: {device_count}") # Убрал вывод
            if device_count > 0:
                for i in range(device_count):
                    # device_name = torch.cuda.get_device_name(i) # Получение имени здесь не нужно для списка ID
                    cuda_devices.append(f"cuda:{i}")
                    # logger.info(f"  - Обнаружено: cuda:{i} ({device_name})") # Убрал вывод
            # else: # Убрал вывод
                # logger.info("torch.cuda.is_available() вернул True, но device_count <= 0. Странная ситуация.")
        # else: # Убрал вывод
            # logger.info("CUDA недоступен в установленной версии PyTorch.")
            # try:
            #     smi_output = subprocess.check_output(["nvidia-smi", "-L"], text=True, stderr=subprocess.STDOUT)
            #     logger.info("Вывод 'nvidia-smi -L':")
            #     logger.info(smi_output)
            #     logger.info("NVIDIA драйверы установлены, но PyTorch не видит CUDA. Возможные причины:")
            #     logger.info("- PyTorch установлен для CPU (pip install torch), а не для CUDA.")
            #     logger.info("- Несовместимость версии CUDA драйвера и CUDA Toolkit, с которым собран PyTorch.")
            #     logger.info("- Проблемы с окружением (переменные PATH, CUDA_VISIBLE_DEVICES).")
            # except (FileNotFoundError, subprocess.CalledProcessError, Exception) as smi_e:
            #     logger.info(f"Не удалось выполнить 'nvidia-smi -L' для диагностики: {smi_e}")
            #     logger.info("Возможно, NVIDIA драйверы не установлены или nvidia-smi не в PATH.")

    except ImportError:
        logger.info("PyTorch не найден. Невозможно определить CUDA устройства через PyTorch.")
        # logger.info("Для автоматического определения всех GPU NVIDIA рекомендуется установить PyTorch с поддержкой CUDA.") # Убрал вывод
    except Exception as e:
        logger.info(f"Неожиданная ошибка при проверке CUDA устройств через PyTorch: {e}")

    # if not cuda_devices: # Убрал вывод
        # logger.info("Не удалось определить CUDA устройства через PyTorch.")

    return cuda_devices

def get_gpu_name_by_id(device_id):
    """
    Получает имя GPU по его ID (например, 'cuda:0').
    Требует установленный PyTorch с поддержкой CUDA.

    Args:
        device_id (str): Идентификатор устройства, например 'cuda:0'.

    Returns:
        str: Имя GPU или None, если не удалось определить.
    """
    if not isinstance(device_id, str) or not device_id.startswith("cuda:"):
        # logger.info(f"Неверный формат device_id: {device_id}. Ожидается 'cuda:X'.") # Убрал вывод
        return None

    try:
        # Извлекаем индекс из строки 'cuda:X'
        match = re.match(r"cuda:(\d+)", device_id)
        if not match:
            # logger.info(f"Не удалось извлечь индекс из device_id: {device_id}") # Убрал вывод
            return None
        index = int(match.group(1))

        import torch
        if torch.cuda.is_available() and index < torch.cuda.device_count():
            return torch.cuda.get_device_name(index)
        else:
            # logger.info(f"CUDA недоступен или индекс {index} вне диапазона доступных устройств.") # Убрал вывод
            return None
    except ImportError:
        logger.info("PyTorch не найден. Невозможно получить имя GPU.")
        return None
    except Exception as e:
        logger.info(f"Ошибка при получении имени GPU для {device_id}: {e}")
        return None