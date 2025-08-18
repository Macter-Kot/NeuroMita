from telethon import TelegramClient, events
import os
import sys
import time
import random
import asyncio

from telethon.tl.types import MessageMediaDocument, DocumentAttributeAudio
from telethon.errors import SessionPasswordNeededError

from utils.audio_converter import AudioConverter
from handlers.audio_handler import AudioHandler
from main_logger import logger
from utils import SH
import platform
from core.events import get_event_bus, Events

class TelegramBotHandler:

    def __init__(
            self, api_id, api_hash, phone, tg_bot, message_limit_per_minute=20
    ):
        # Получение параметров
        self.event_bus = get_event_bus()
        
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.tg_bot = tg_bot
        
        self.last_speaker_command = ""
        self.last_send_time = -1

        # Получаем настройки через событие
        settings_result = self.event_bus.emit_and_wait(Events.Settings.GET_SETTINGS, timeout=1.0)
        settings = settings_result[0] if settings_result else {}
        
        self.silero_time_limit = int(settings.get("SILERO_TIME", "10"))
        if not hasattr(self, "silero_time_limit") or self.silero_time_limit is None:
            self.silero_time_limit = 10

        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
            alt_base_dir = getattr(sys, '_MEIPASS', base_dir)
        else:
            base_dir = os.path.dirname(__file__)
            alt_base_dir = base_dir

        ffmpeg_rel_path = os.path.join(
            "ffmpeg-7.1-essentials_build", "bin", "ffmpeg.exe"
        )
        ffmpeg_path = os.path.join(base_dir, ffmpeg_rel_path)
        if not os.path.exists(ffmpeg_path):
            ffmpeg_path = os.path.join(alt_base_dir, ffmpeg_rel_path)
        self.ffmpeg_path = ffmpeg_path

        device_model = platform.node()
        system_version = f"{platform.system()} {platform.release()}"
        app_version = "1.0.0"

        self.message_limit_per_minute = message_limit_per_minute
        self.message_count = 0
        self.start_time = time.time()

        self.client = None
        try:
            self.client = TelegramClient(
                "session_name",
                int(self.api_id),
                self.api_hash,
                device_model=device_model,
                system_version=system_version,
                app_version=app_version,
            )
        except Exception as e:
            logger.info(f"Проблема в ините тг: {e}")
            logger.info(SH(self.api_id))
            logger.info(SH(self.api_hash))

    def reset_message_count(self):
        if time.time() - self.start_time > 60:
            self.message_count = 0
            self.start_time = time.time()

    async def send_and_receive(self, input_message, speaker_command, message_id, voice_future : asyncio.Future | None = None,):
        logger.info(f"Отправка сообщения на озвучку Telegram: {speaker_command} {input_message}")
        if not input_message or not speaker_command:
            return

        time_between_messages = 1.5
        current_time = time.time()
        if self.last_send_time > 0:
            time_since_last = current_time - self.last_send_time
            if time_since_last < time_between_messages:
                logger.info(f"Слишком быстро пришел некст войс, ждем {time_between_messages - time_since_last:.2f} сек")
                await asyncio.sleep(time_between_messages - time_since_last)
        self.last_send_time = time.time()

        if self.last_speaker_command != speaker_command:
            await self.client.send_message(self.tg_bot, speaker_command)
            self.last_speaker_command = speaker_command
            await asyncio.sleep(0.7)

        self.last_speaker_command = speaker_command
        self.reset_message_count()

        if self.message_count >= self.message_limit_per_minute:
            logger.warning("Превышен лимит сообщений. Ожидаем...")
            await asyncio.sleep(random.uniform(10, 15))
            return

        if self.tg_bot == "@CrazyMitaAIbot":
            input_message = f"/voice {input_message}"
        await self.client.send_message(self.tg_bot, input_message)
        self.message_count += 1

        logger.info("Ожидание ответа от бота...")
        response = None
        attempts = 0
        attempts_per_second = 3
        attempts_max = self.silero_time_limit * attempts_per_second

        await asyncio.sleep(0.5)
        while attempts <= attempts_max:
            async for message in self.client.iter_messages(self.tg_bot, limit=1):
                if message.media and isinstance(message.media, MessageMediaDocument):
                    doc = message.media.document
                    if "audio/mpeg" in doc.mime_type or ("audio/ogg" in doc.mime_type and any(isinstance(attr, DocumentAttributeAudio) and attr.voice for attr in doc.attributes)):
                        response = message
                        break
            if response:
                break
            logger.info(f"Попытка {attempts + 1}/{attempts_max}. Ответ от бота не найден.")
            attempts += 1
            await asyncio.sleep(1 / attempts_per_second)

        if not response:
            logger.info(f"Ответ от бота не получен после {attempts_max} попыток.")
            return
        
        logger.info("Ответ получен")

        path_to_file: str | None = None

        if response.media and isinstance(response.media, MessageMediaDocument):
            # Качаем в ./temp (создаём при необходимости)
            temp_dir = os.path.join(os.getcwd(), "temp")
            os.makedirs(temp_dir, exist_ok=True)
            file_path = await self.client.download_media(response.media, file=temp_dir)
            logger.info(f"Файл загружен: {file_path}")

            # Ждём, пока файл появится и стабилизируется по размеру
            start_time = time.time()
            last_size = -1
            while True:
                try:
                    if os.path.exists(file_path):
                        size = os.path.getsize(file_path)
                        if size > 0 and size == last_size:
                            break
                        last_size = size
                except OSError:
                    pass
                if time.time() - start_time > 10.0:
                    break
                await asyncio.sleep(0.1)

            sound_absolute_path = os.path.abspath(file_path)

            # Получаем статус подключения к игре через событие
            connection_result = await asyncio.get_event_loop().run_in_executor(
                None, 
                self.event_bus.emit_and_wait,
                Events.Server.GET_GAME_CONNECTION,
                {},
                1.0
            )
            connected_to_game = connection_result[0] if connection_result else False

            if connected_to_game:
                logger.info("Подключен к игре, нужна конвертация")
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                wav_path = os.path.join(os.path.dirname(file_path), f"{base_name}.wav")
                absolute_wav_path = os.path.abspath(wav_path)
                
                await AudioConverter.convert_to_wav(sound_absolute_path, absolute_wav_path)

                try:
                    os.remove(sound_absolute_path)
                except OSError as remove_error:
                    logger.info(f"Ошибка при удалении файла {sound_absolute_path}: {remove_error}")

                # Устанавливаем данные через события
                self.event_bus.emit(Events.Server.SET_PATCH_TO_SOUND_FILE, absolute_wav_path)
                logger.info(f"Файл установлен серверу: {absolute_wav_path}")
                self.event_bus.emit_and_wait(Events.Server.SET_ID_SOUND, {'id': message_id})
                logger.info(f"Установленный файлу message_Id: {message_id}")
                
                path_to_file = absolute_wav_path
            else:
                logger.info(f"Отправлен воспроизводится: {sound_absolute_path}")
                path_to_file = sound_absolute_path
                await AudioHandler.handle_voice_file(file_path)
        elif response.text:
            logger.info(f"Ответ от бота: {response.text}")
        return path_to_file
        

    async def start(self):
        logger.info("Запуск коннектора ТГ!")
        try:
            await self.client.connect()

            # Получаем event loop и auth_signals через событие
            loop_results = await asyncio.get_event_loop().run_in_executor(
                None,
                self.event_bus.emit_and_wait,
                Events.Core.GET_EVENT_LOOP,
                {},
                1.0
            )
            loop = loop_results[0] if loop_results else asyncio.get_event_loop()

            if not await self.client.is_user_authorized():
                try:
                    await self.client.send_code_request(self.phone)
                    
                    code_future = loop.create_future()
                    self.event_bus.emit(Events.Telegram.PROMPT_FOR_TG_CODE, {'future': code_future})
                    verification_code = await code_future
                    
                    try:
                        await self.client.sign_in(phone=self.phone, code=verification_code)
                    except SessionPasswordNeededError:
                        password_future = loop.create_future()
                        self.event_bus.emit(Events.Telegram.PROMPT_FOR_TG_PASSWORD, {'future': password_future})
                        password = await password_future
                        await self.client.sign_in(password=password)

                except asyncio.CancelledError:
                    logger.info("Авторизация отменена пользователем.")
                    raise
                except Exception as e:
                    logger.error(f"Ошибка при авторизации: {e}")
                    raise

            await self.client.send_message(self.tg_bot, "/start")
            
            # Устанавливаем статус подключения через событие
            self.event_bus.emit(Events.Telegram.SET_SILERO_CONNECTED, {'connected': True})

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
            self.event_bus.emit(Events.Telegram.SET_SILERO_CONNECTED, {'connected': False})
            logger.error(f"Ошибка авторизации: {e}")

    async def getLastMessage(self):
        messages = await self.client.get_messages(self.tg_bot, limit=1)
        return messages[0] if messages else None

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

    async def execute_toggle_command(self, command: str, active_response: str, inactive_response: str, max_attempts: int = 3, initial_delay: float = 0.5, retry_delay: float = 1):
        attempts = 0
        while attempts < max_attempts:
            attempts += 1
            try:
                await self.client.send_message(self.tg_bot, command)
                await asyncio.sleep(initial_delay)
                last_message = await self.getLastMessage()
                if not last_message or not hasattr(last_message, 'text'):
                    continue
                if "Слишком много запросов" in last_message.text:
                    if attempts < max_attempts:
                        await asyncio.sleep(retry_delay)
                    continue
                if last_message.text == inactive_response:
                    await asyncio.sleep(retry_delay)
                    await self.client.send_message(self.tg_bot, command)
                    return True
                if last_message.text == active_response:
                    return True
            except Exception as e:
                logger.info(f"Ошибка при выполнении команды {command}: {str(e)}")
                if attempts < max_attempts:
                    await asyncio.sleep(retry_delay)
        return False