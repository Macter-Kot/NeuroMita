import io
import uuid
import os
import glob
import asyncio
from handlers.audio_handler import AudioHandler
from main_logger import logger
from utils import process_text_to_voice
from handlers.local_voice_handler import LocalVoice
from ui.settings.voiceover_settings import LOCAL_VOICE_MODELS

class AudioController:
    def __init__(self, main_controller):
        self.main = main_controller
        self.local_voice = LocalVoice(self.main)
        self.voiceover_method = self.main.settings.get("VOICEOVER_METHOD", "TG")
        self.current_local_voice_id = self.main.settings.get("NM_CURRENT_VOICEOVER", None)
        self.last_voice_model_selected = None
        if self.current_local_voice_id:
            for model_info in LOCAL_VOICE_MODELS:
                if model_info["id"] == self.current_local_voice_id:
                    self.last_voice_model_selected = model_info
                    break
        self.model_loading_cancelled = False
        
        self.textToTalk = ""
        self.textSpeaker = "/Speaker Mita"
        self.textSpeakerMiku = "/set_person CrazyMita"
        self.silero_turn_off_video = False
        self.patch_to_sound_file = ""
        self.id_sound = -1
        self.waiting_answer = False
        
    def get_speaker_text(self):
        if self.main.settings.get("AUDIO_BOT") == "@CrazyMitaAIbot":
            return self.textSpeakerMiku
        else:
            return self.textSpeaker
            
    async def run_send_and_receive(self, response, speaker_command, id=0):
        logger.info("Попытка получить фразу")
        self.waiting_answer = True
        await self.main.telegram_controller.bot_handler.send_and_receive(response, speaker_command, id)
        self.waiting_answer = False
        logger.info("Завершение получения фразы")
        
    def voice_text(self):
        logger.info(f"Есть текст для отправки: {self.textToTalk} id {self.id_sound}")
        if self.main.loop and self.main.loop.is_running():
            try:
                self.voiceover_method = self.main.settings.get("VOICEOVER_METHOD", "TG")

                if self.voiceover_method == "TG":
                    logger.info("Используем Telegram (Silero/Miku) для озвучки")
                    asyncio.run_coroutine_threadsafe(
                        self.run_send_and_receive(self.textToTalk, self.get_speaker_text(), self.id_sound),
                        self.main.loop
                    )
                    self.textToTalk = ""

                elif self.voiceover_method == "Local":
                    selected_local_model_id = self.main.settings.get("NM_CURRENT_VOICEOVER", None)
                    if selected_local_model_id:
                        logger.info(f"Используем {selected_local_model_id} для локальной озвучки")
                        if self.local_voice.is_model_initialized(selected_local_model_id):
                            asyncio.run_coroutine_threadsafe(
                                self.run_local_voiceover(self.textToTalk),
                                self.main.loop
                            )
                            self.textToTalk = ""
                        else:
                            logger.warning(f"Модель {selected_local_model_id} выбрана, но не инициализирована. Озвучка не будет выполнена.")
                            self.textToTalk = ""
                    else:
                        logger.warning("Локальная озвучка выбрана, но конкретная модель не установлена/не выбрана.")
                        self.textToTalk = ""
                else:
                    logger.warning(f"Неизвестный метод озвучки: {self.voiceover_method}")
                    self.textToTalk = ""

                logger.info("Выполнено")
            except Exception as e:
                logger.error(f"Ошибка при отправке текста на озвучку: {e}")
                self.textToTalk = ""
        else:
            logger.error("Ошибка: Цикл событий не готов.")
            
    async def run_local_voiceover(self, text):
        result_path = None
        try:
            character = self.main.model_controller.model.current_character if hasattr(self.main.model_controller.model, "current_character") else None
            output_file = f"MitaVoices/output_{uuid.uuid4()}.wav"
            absolute_audio_path = os.path.abspath(output_file)
            os.makedirs(os.path.dirname(absolute_audio_path), exist_ok=True)

            result_path = await self.local_voice.voiceover(
                text=text,
                output_file=absolute_audio_path,
                character=character
            )

            if result_path:
                logger.info(f"Локальная озвучка сохранена в: {result_path}")
                if not self.main.ConnectedToGame and self.main.settings.get("VOICEOVER_LOCAL_CHAT"):
                    await AudioHandler.handle_voice_file(result_path, self.main.settings.get("LOCAL_VOICE_DELETE_AUDIO",
                                                                                        True) if os.environ.get(
                        "ENABLE_VOICE_DELETE_CHECKBOX", "0") == "1" else True)
                elif self.main.ConnectedToGame:
                    self.patch_to_sound_file = result_path
                    logger.info(f"Путь к файлу для игры: {self.patch_to_sound_file}")
                else:
                    logger.info("Озвучка в локальном чате отключена.")
            else:
                logger.error("Локальная озвучка не удалась, файл не создан.")

        except Exception as e:
            logger.error(f"Ошибка при выполнении локальной озвучки: {e}")
            
    @staticmethod
    def delete_all_sound_files():
        for pattern in ["*.wav", "*.mp3"]:
            files = glob.glob(pattern)
            for file in files:
                try:
                    os.remove(file)
                    logger.info(f"Удален файл: {file}")
                except Exception as e:
                    logger.info(f"Ошибка при удалении файла {file}: {e}")