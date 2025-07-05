import subprocess
import os
import ffmpeg
import sys

from main_logger import logger


class AudioConverter:
    # Проверяем, где лежит ffmpeg\
    #ffmpeg_rel_path = os.path.join("ffmpeg-7.1-essentials_build", "bin", "ffmpeg.exe")
    ffmpeg_rel_path = os.path.join("ffmpeg.exe")
    if getattr(sys, 'frozen', False):
        # Если программа собрана в exe, получаем путь к исполняемому файлу
        base_dir = os.path.dirname(sys.executable)

        # Альтернативный вариант: если ffmpeg всё же упакован в _MEIPASS
        alt_base_dir = sys._MEIPASS
    else:
        # Если программа запускается как скрипт
        base_dir = os.path.dirname(__file__)
        alt_base_dir = base_dir  # Для единообразия
    ffmpeg_path = os.path.join(base_dir, ffmpeg_rel_path)

    @staticmethod
    async def convert_to_wav(input_file, output_file):
        logger.info(f"Начинаю конвертацию {input_file} в {output_file} с помощью {AudioConverter.ffmpeg_path}")

        try:
            command = [
                AudioConverter.ffmpeg_path,
                '-i', input_file,
                '-f', 'wav',
                '-acodec', 'pcm_s16le',
                '-ar', '44100', # Стандартная частота дискретизации
                '-ac', '2', # Стерео
                '-q:a', '0', # Высокое качество
                '-threads', '4', # Используем многопоточность
                '-preset', 'ultrafast', # Самый быстрый пресет
                output_file,
                '-y'
            ]
            subprocess.run(command, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.info(f"Ошибка при конвертации аудио: {e}")
            return False
