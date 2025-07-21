import os
import asyncio
import tempfile
from main_logger import logger
from core.events import get_event_bus, Events, Event

# Контроллер для работы с отправкой сообщений.
class ChatController:
    def __init__(self, settings):
        self.settings = settings
        self.event_bus = get_event_bus()
        self.llm_processing = False
        
        self.staged_images = []
        self._subscribe_to_events()
        
    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.Chat.SEND_MESSAGE, self._on_send_message, weak=False)
        self.event_bus.subscribe(Events.Model.GET_LLM_PROCESSING_STATUS, self._on_get_llm_processing_status, weak=False)
        self.event_bus.subscribe("send_periodic_image_request", self._on_send_periodic_image_request, weak=False)
        self.event_bus.subscribe(Events.Chat.CLEAR_CHAT, self._on_clear_chat, weak=False)
        
        self.event_bus.subscribe(Events.Chat.STAGE_IMAGE, self._on_stage_image, weak=False)
        self.event_bus.subscribe(Events.Chat.CLEAR_STAGED_IMAGES, self._on_clear_staged_images, weak=False)
        
    async def async_send_message(
        self,
        user_input: str,
        system_input: str = "",
        image_data: list[bytes] | None = None,
        message_id: int | None = None  # ДОБАВИТЬ ПАРАМЕТР
    ):
        try:
            print("[DEBUG] Начинаем async_send_message, показываем статус")
            self.llm_processing = True
            
            is_streaming = bool(self.settings.get("ENABLE_STREAMING", False))

            def stream_callback_handler(chunk: str):
                self.event_bus.emit(Events.GUI.APPEND_STREAM_CHUNK_UI, {'chunk': chunk})

            if is_streaming:
                self.event_bus.emit(Events.GUI.PREPARE_STREAM_UI)

            response_result = self.event_bus.emit_and_wait(Events.Model.GENERATE_RESPONSE, {
                'user_input': user_input,
                'system_input': system_input,
                'image_data': image_data,
                'stream_callback': stream_callback_handler if is_streaming else None,
                'message_id': message_id  # Передаем message_id дальше
            }, timeout=600.0)
            
            response = response_result[0] if response_result else None

            if response and self.settings.get("USE_VOICEOVER"):
                character_result = self.event_bus.emit_and_wait(Events.Model.GET_CURRENT_CHARACTER, timeout=3.0)
                current_character = character_result[0] if character_result else None
                
                logger.info(current_character)
                if current_character:
                    is_game_master = current_character.get('name') == 'GameMaster'
                    if not is_game_master or self.settings.get("GM_VOICE"):
                        from utils import process_text_to_voice
                        processed_response = process_text_to_voice(response)
                        
                        speaker = current_character.get("silero_command")
                        if self.settings.get("AUDIO_BOT") == "@CrazyMitaAIbot":
                            speaker = current_character.get("miku_tts_name")
                        
                        self.event_bus.emit(Events.Audio.VOICEOVER_REQUESTED, {
                            'text': processed_response,
                            'speaker': speaker,
                            'message_id': message_id
                        })
                        logger.info(f"Озвучка запрошена: {processed_response[:50]}... с message_id: {message_id}")

            if is_streaming:
                self.event_bus.emit(Events.GUI.FINISH_STREAM_UI)
            else:
                self.event_bus.emit(Events.GUI.UPDATE_CHAT_UI, {
                    'role': 'assistant',
                    'response': response if response is not None else "...",
                    'is_initial': False,
                    'emotion': ''
                })

            self.event_bus.emit(Events.GUI.UPDATE_STATUS)
            self.event_bus.emit(Events.GUI.UPDATE_DEBUG_INFO)
            self.event_bus.emit(Events.GUI.UPDATE_TOKEN_COUNT)

            # Получаем сервер через событие
            server_result = self.event_bus.emit_and_wait(Events.Server.GET_CHAT_SERVER, timeout=1.0)
            server = server_result[0] if server_result else None
            
            if server and server.client_socket:
                final_response_text = response if response else "..."
                try:
                    server.send_message_to_server(final_response_text)
                    logger.info("Ответ отправлен в игру.")
                except Exception as e:
                    logger.error(f"Не удалось отправить ответ в игру: {e}")
            
            self.llm_processing = False
            return response
                    
        except asyncio.TimeoutError:
            logger.warning("Тайм-аут: генерация ответа заняла слишком много времени.")
            self.llm_processing = False
            self.event_bus.emit(Events.Model.ON_FAILED_RESPONSE, {'error': "Превышено время ожидания ответа"})
            return "Произошла ошибка при обработке вашего сообщения."
        except Exception as e:
            logger.error(f"Ошибка в async_send_message: {e}", exc_info=True)
            self.llm_processing = False
            self.event_bus.emit(Events.Model.ON_FAILED_RESPONSE, {'error': f"Ошибка: {str(e)[:50]}..."})
            return "Произошла ошибка при обработке вашего сообщения."
    
    def _on_send_message(self, event: Event):
        data = event.data
        user_input = data.get('user_input', '')
        system_input = data.get('system_input', '')
        image_data = data.get('image_data', [])
        message_id = data.get('message_id')
        
        if image_data:
            self.event_bus.emit(Events.Capture.UPDATE_LAST_IMAGE_REQUEST_TIME)
        
        # Получаем главный asyncio-loop
        loop_res = self.event_bus.emit_and_wait(Events.Core.GET_EVENT_LOOP, timeout=1.0)
        loop = loop_res[0] if loop_res else None
        
        if loop and loop.is_running():
            # Запускаем корутину в этом loop'е и синхронно ждём результата
            import asyncio
            fut = asyncio.run_coroutine_threadsafe(
                self.async_send_message(user_input, system_input, image_data, message_id),
                loop
            )
            try:
                response = fut.result(timeout=600)
                return response  # ответ попадёт вызвавшему emit_and_wait
            except Exception as e:
                logger.error(f"async_send_message failed: {e}", exc_info=True)
                return None
        else:
            # fallback: нет цикла ⇒ запускаем напрямую
            import asyncio
            response = asyncio.run(
                self.async_send_message(user_input, system_input, image_data, message_id)
            )
            return response
    
    def _on_get_llm_processing_status(self, event: Event):
        return self.llm_processing
    
    def _on_send_periodic_image_request(self, event: Event):
        data = event.data
        
        if data.get('image_data'):
            self.event_bus.emit(Events.Capture.UPDATE_LAST_IMAGE_REQUEST_TIME)
        
        coro = self.async_send_message(
            user_input=data.get('user_input', ''),
            system_input=data.get('system_input', ''), 
            image_data=data.get('image_data', []),
            message_id=data.get('message_id')  # ДОБАВИТЬ
        )
        
        self.event_bus.emit(Events.Core.RUN_IN_LOOP, {
            'coroutine': coro,
            'callback': None
        })

    
    def _on_clear_chat(self, event: Event):
        pass

    
    def stage_image_bytes(self, img_bytes: bytes) -> int:
        fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="nm_clip_")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(img_bytes)

        self.staged_images.append(tmp_path)
        logger.info(f"Clipboard image staged: {tmp_path}")
        return len(self.staged_images)

    def clear_staged_images(self):
        self.staged_images.clear()
    
    
    def _on_stage_image(self, event: Event):
        image_data = event.data.get('image_data')
        if image_data:
            if isinstance(image_data, bytes):
                self.stage_image_bytes(image_data)
            elif isinstance(image_data, str):
                self.staged_images.append(image_data)
    
    def _on_clear_staged_images(self, event: Event):
        self.clear_staged_images()
