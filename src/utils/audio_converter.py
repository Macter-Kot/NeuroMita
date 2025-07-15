import subprocess
import os
import ffmpeg
import sys

from main_logger import logger


class AudioConverter:
    ffmpeg_path = os.path.join("ffmpeg.exe")

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
