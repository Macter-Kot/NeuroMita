from telethon import TelegramClient, events
import os
import sys
import time
import random
import asyncio
#import emoji

from telethon.tl.types import MessageMediaDocument, DocumentAttributeAudio
from telethon.errors import SessionPasswordNeededError

import tkinter as tk
import platform

from AudioConverter import AudioConverter
from AudioHandler import AudioHandler
from Logger import logger
from utils import SH


# Пример использования:
class TelegramBotHandler:

    def __init__(
            self, gui, api_id, api_hash, phone, tg_bot, message_limit_per_minute=20
    ):
        # Получение параметров из окружения
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.tg_bot = tg_bot  # Юзернейм Silero бота
        self.gui = gui
        self.patch_to_sound_file = ""
        self.last_speaker_command = ""

        self.last_send_time = -1

        #Считываем значение настройки SILERO_TIME_LIMIT
        self.silero_time_limit = int(gui.settings.get("SILERO_TIME", "10"))

        #Проверяем значение. Если пусто подставляем по умолчанию 10 секунд.
        if not hasattr(self, "silero_time_limit") or self.silero_time_limit is None:
            self.silero_time_limit = 10

        if getattr(sys, "frozen", False):
            # Если программа собрана в exe, получаем путь к исполняемому файлу
            base_dir = os.path.dirname(sys.executable)

            # Альтернативный вариант: если ffmpeg всё же упакован в _MEIPASS
            alt_base_dir = sys._MEIPASS
        else:
            # Если программа запускается как скрипт
            base_dir = os.path.dirname(__file__)
            alt_base_dir = base_dir  # Для единообразия

        # Проверяем, где лежит ffmpeg
        ffmpeg_rel_path = os.path.join(
            "ffmpeg-7.1-essentials_build", "bin", "ffmpeg.exe"
        )

        ffmpeg_path = os.path.join(base_dir, ffmpeg_rel_path)
        if not os.path.exists(ffmpeg_path):
            # Если не нашли в base_dir, пробуем _MEIPASS (актуально для PyInstaller)
            ffmpeg_path = os.path.join(alt_base_dir, ffmpeg_rel_path)

        self.ffmpeg_path = ffmpeg_path

        # Системные параметры
        device_model = platform.node()  # Имя устройства
        system_version = f"{platform.system()} {platform.release()}"  # ОС и версия
        app_version = "1.0.0"  # Версия приложения задается вручную

        # Параметры бота
        self.message_limit_per_minute = message_limit_per_minute
        self.message_count = 0
        self.start_time = time.time()

        self.client = None
        try:
            # Создание клиента Telegram с системными параметрами
            self.client = TelegramClient(
                "session_name",
                int(self.api_id),
                self.api_hash,
                device_model=device_model,
                system_version=system_version,
                app_version=app_version,
            )
        except:
            logger.info("Проблема в ините тг")
            logger.info(SH(self.api_id))
            logger.info(SH(self.api_hash))

    def reset_message_count(self):
        """Сбрасывает счетчик сообщений каждую минуту."""
        if time.time() - self.start_time > 60:
            self.message_count = 0
            self.start_time = time.time()

    async def send_and_receive(self, input_message, speaker_command, message_id):
        """Отправляет сообщение боту и обрабатывает ответ."""
        global message_count
        # start_time = time.time()

        if not input_message or not speaker_command:
            return

        # Защита от слишком быстрых сообщений
        time_between_messages = 1.5
        current_time = time.time()
        if self.last_send_time > 0:  # проверяем, что это не первый вызов
            time_since_last = current_time - self.last_send_time
            if time_since_last < time_between_messages:
                logger.info(f"Слишком быстро пришел некст войс, ждем{time_between_messages - time_since_last}")
                await asyncio.sleep(time_between_messages - time_since_last)

        self.last_send_time = time.time()  # обновляем время после возможной паузы

        #При компиляции нужно добавить в строку компилятора --add-data "%USERPROFILE%\AppData\Local\Programs\Python\Python313\Lib\site-packages\emoji\unicode_codes\emoji.json;emoji\unicode_codes"
        #Удаляем эмодзи из озвучки:

        #TODO ВЕРНУТь
        #input_message = emoji.replace_emoji(input_message)  # Заменяет все эмодзи на пустую строку

        if self.last_speaker_command != speaker_command:
            await self.client.send_message(self.tg_bot, speaker_command)
            self.last_speaker_command = speaker_command
            await asyncio.sleep(0.7)

            #await self.TurnOnHd()
            #await asyncio.sleep(0.75)

            #if self.gui.silero_turn_off_video:
             #   await self.TurnOffCircles()
              #  await asyncio.sleep(0.75)

        self.last_speaker_command = speaker_command

        self.reset_message_count()

        if self.message_count >= self.message_limit_per_minute:
            logger.warning("Превышен лимит сообщений. Ожидаем...")
            await asyncio.sleep(random.uniform(10, 15))
            return

        # Отправка сообщения боту
        if self.tg_bot == "@CrazyMitaAIbot":
            input_message = f"/voice {input_message}"
        await self.client.send_message(self.tg_bot, input_message)
        self.message_count += 1

        # Ожидание ответа от бота
        logger.info("Ожидание ответа от бота...")
        response = None
        attempts = 0
        attempts_per_second = 3

        attempts_max = self.silero_time_limit * attempts_per_second

        await asyncio.sleep(0.5)
        while attempts <= attempts_max:  # Попытки получения ответа

            async for message in self.client.iter_messages(self.tg_bot, limit=1):
                if message.media and isinstance(message.media, MessageMediaDocument):
                    doc = message.media.document

                    # Проверяем MP3-файл
                    if "audio/mpeg" in doc.mime_type:
                        response = message
                        break

                    # Проверяем голосовое сообщение (OGG, voice)
                    if "audio/ogg" in doc.mime_type:
                        for attr in doc.attributes:
                            if isinstance(attr, DocumentAttributeAudio) and attr.voice:
                                response = message
                                break
            if response:  # Если ответ найден, выходим из цикла
                break
            logger.info(f"Попытка {attempts + 1}/{attempts_max}. Ответ от бота не найден.")
            attempts += 1
            await asyncio.sleep(1 / attempts_per_second)  # Немного подождем

        if not response:
            logger.info(f"Ответ от бота не получен после {attempts_max} попыток.")
            return

        logger.info("Ответ получен")
        # Обработка полученного сообщения
        if response.media and isinstance(response.media, MessageMediaDocument):
            if response and response.media:
                file_path = await self.client.download_media(response.media)

                logger.info(f"Файл загружен: {file_path}")
                sound_absolute_path = os.path.abspath(file_path)

                # end_time = time.time()
                # logger.info(f"Время генерации озвучки {self.tg_bot}: {end_time - start_time}")

                if self.gui.ConnectedToGame:
                    logger.info("Подключен к игре, нужна конвертация")

                    # Генерируем путь для WAV-файла на основе имени исходного MP3
                    base_name = os.path.splitext(os.path.basename(file_path))[
                        0
                    ]  # Получаем имя файла без расширения
                    wav_path = os.path.join(
                        os.path.dirname(file_path), f"{base_name}.wav"
                    )  # Создаем новый путь

                    # Получаем абсолютный путь

                    absolute_wav_path = os.path.abspath(wav_path)
                    # Конвертируем MP3 в WAV
                    # await  AudioConverter.convert_mp3_to_wav(sound_absolute_path, absolute_wav_path)
                    await AudioConverter.convert_to_wav(
                        sound_absolute_path, absolute_wav_path
                    )

                    try:
                        logger.info(f"Удаляю файл: {sound_absolute_path}")
                        os.remove(sound_absolute_path)
                        logger.info(f"Файл {sound_absolute_path} удалён.")
                    except OSError as remove_error:
                        logger.info(
                            f"Ошибка при удалении файла {sound_absolute_path}: {remove_error}"
                        )

                    # .BnmRvcModel.process(absolute_wav_path, absolute_wav_path+"_RVC_.wav")

                    self.gui.patch_to_sound_file = absolute_wav_path
                    self.gui.id_sound = message_id
                    logger.info(f"Файл wav загружен: {absolute_wav_path}")
                else:
                    logger.info(f"Отправлен воспроизводится: {sound_absolute_path}")
                    await AudioHandler.handle_voice_file(file_path)
        elif response.text:  # Если сообщение текстовое
            logger.info(f"Ответ от бота: {response.text}")

    async def start(self):
        logger.info("Запуск коннектора ТГ!")
        try:
            await self.client.connect()

            # Проверяем, авторизован ли уже клиент
            if not await self.client.is_user_authorized():
                # Создаем окно для ввода кода подтверждения
                code_window = tk.Toplevel()
                code_window.title("Подтверждение Telegram")
                code_window.geometry("300x150")
                code_window.resizable(False, False)

                frame = tk.Frame(code_window)
                frame.place(relx=0.5, rely=0.5, anchor="center")

                code_var = tk.StringVar()

                code_entry = tk.Entry(
                    frame, textvariable=code_var, width=20, justify="center"
                )
                code_entry.pack(pady=10)
                code_entry.focus()  # Устанавливаем фокус на поле ввода

                code_future = asyncio.Future()

                def submit_code():
                    if code_var.get().strip():  # Проверяем, что код не пустой
                        code_future.set_result(code_var.get().strip())
                        code_window.destroy()
                    else:
                        tk.messagebox.showerror("Ошибка", "Введите код подтверждения")

                def on_enter(event):
                    submit_code()

                code_entry.bind("<Return>", on_enter)  # Добавляем обработку Enter

                submit_button = tk.Button(
                    frame,
                    text="Подтвердить",
                    command=submit_code,
                    width=15,
                    relief="flat",
                )
                submit_button.pack(pady=15)

                # Ждем код подтверждения
                try:
                    await self.client.sign_in(phone=self.phone)
                    verification_code = await code_future

                    try:
                        await self.client.sign_in(phone=self.phone, code=verification_code)
                    except SessionPasswordNeededError:
                        # Если требуется пароль двухфакторной аутентификации
                        password_window = tk.Toplevel()
                        password_window.title("Двухфакторная аутентификация")
                        password_window.geometry("300x150")
                        password_window.resizable(False, False)

                        frame = tk.Frame(password_window)
                        frame.place(relx=0.5, rely=0.5, anchor="center")

                        password_var = tk.StringVar()

                        password_entry = tk.Entry(
                            frame, textvariable=password_var, width=20, justify="center", show="*"
                        )
                        password_entry.pack(pady=10)
                        password_entry.focus()

                        password_future = asyncio.Future()

                        def submit_password():
                            if password_var.get().strip():
                                password_future.set_result(password_var.get().strip())
                                password_window.destroy()
                            else:
                                tk.messagebox.showerror("Ошибка", "Введите пароль")

                        def on_enter_password(event):
                            submit_password()

                        password_entry.bind("<Return>", on_enter_password)

                        submit_button = tk.Button(
                            frame,
                            text="Подтвердить",
                            command=submit_password,
                            width=15,
                            relief="flat",
                        )
                        submit_button.pack(pady=15)

                        # Получаем пароль от пользователя
                        password = await password_future
                        await self.client.sign_in(password=password)

                except Exception as e:
                    logger.info(f"Ошибка при авторизации: {e}")
                    raise

            await self.client.send_message(self.tg_bot, "/start")
            self.gui.silero_connected.set(True)

            if self.tg_bot == "@silero_voice_bot":
                await asyncio.sleep(0.35)
                await self.client.send_message(self.tg_bot, "/speaker mita")
                self.last_speaker_command = "/speaker mita"
                await asyncio.sleep(0.35)
                await self.client.send_message(self.tg_bot, "/mp3")
                await asyncio.sleep(0.35)
                await self.TurnOnHd()
                await asyncio.sleep(0.35)
                await self.TurnOffCircles()
            logger.info("Включено все в ТГ для сообщений миты")
        except Exception as e:
            self.gui.silero_connected.set(False)
            logger.error(f"Ошибка авторизации: {e}")

    async def getLastMessage(self):
        # Получаем последнее сообщение от бота
        messages = await self.client.get_messages(self.tg_bot, limit=1)
        last_message = messages[0] if messages else None
        return last_message

    async def TurnOnHd(self):
        return await self.execute_toggle_command(
            command="/hd",
            active_response="Режим HD включен!",
            inactive_response="Режим HD выключен!"
        )

    async def TurnOffCircles(self):
        return await self.execute_toggle_command(
            command="/videonotes",
            active_response="Кружки выключены!",
            inactive_response="Кружки включены!"
        )

    async def execute_toggle_command(self, command: str,
                                     active_response: str,
                                     inactive_response: str,
                                     max_attempts: int = 3,
                                     initial_delay: float = 0.5,
                                     retry_delay: float = 1):
        """
        Обобщенная функция для выполнения toggle-команд с проверкой состояния и повторными попытками

        :param command: Команда для отправки (например "/hd" или "/videonotes")
        :param active_response: Текст сообщения, когда функция активна (например "Кружки включены!")
        :param inactive_response: Текст сообщения, когда функция неактивна (например "Режим HD выключен!")
        :param max_attempts: Максимальное количество попыток
        :param initial_delay: Задержка перед проверкой ответа (в секундах)
        :param retry_delay: Задержка перед повторной попыткой (в секундах)
        """
        attempts = 0

        while attempts < max_attempts:
            attempts += 1

            try:
                await self.client.send_message(self.tg_bot, command)
                await asyncio.sleep(initial_delay)
                last_message = await self.getLastMessage()

                if not last_message:
                    continue

                # Если получили сообщение о слишком частых запросах
                if "Слишком много запросов" in last_message.text:
                    if attempts < max_attempts:
                        await asyncio.sleep(retry_delay)
                    continue

                # Если получили сообщение о неактивном состоянии - выполняем команду еще раз
                if last_message.text == inactive_response:
                    await asyncio.sleep(retry_delay)
                    await self.client.send_message(self.tg_bot, command)
                    return True

                # Если получили сообщение об активном состоянии - все ок
                if last_message.text == active_response:
                    return True

            except Exception as e:
                logger.info(f"Ошибка при выполнении команды {command}: {str(e)}")
                if attempts < max_attempts:
                    await asyncio.sleep(retry_delay)

        return False
