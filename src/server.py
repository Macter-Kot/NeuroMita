import base64
import json
import socket
from datetime import datetime
import asyncio

from main_logger import logger
from core.events import get_event_bus, Events

class ChatServer:
    def __init__(self, controller, chat_model, host='127.0.0.1', port=12345):
        self.host = host
        self.port = port
        self.controller = controller
        self.server_socket = None
        self.client_socket = None
        self.passive_client_socket = None
        self.passive_server_socket = None
        self.chat_model = chat_model
        self.messages_to_say = []
        self.text_wait_limit_enabled = False
        self.voice_wait_limit_enabled = False
        self.event_bus = get_event_bus()
        

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        logger.info(f"Сервер запущен на {self.host}:{self.port}")

    def handle_connection(self):
        if not self.server_socket:
            raise RuntimeError("Сервер не запущен. Вызовите start() перед handle_connection().")
        try:
            settings_result = self.event_bus.emit_and_wait(Events.GET_SETTINGS, timeout=1.0)
            settings = settings_result[0] if settings_result else {}
            
            self.text_wait_limit_enabled = settings.get("LIMIT_TEXT_WAIT", False)
            self.voice_wait_limit_enabled = settings.get("LIMIT_VOICE_WAIT", False)

            self.client_socket, addr = self.server_socket.accept()

            received_data = b""
            while True:
                chunk = self.client_socket.recv(65536)
                if not chunk:
                    break
                received_data += chunk
                if b"}" in chunk and received_data.count(b"{") == received_data.count(b"}"):
                    break
            
            received_text = received_data.decode("utf-8")

            if not received_text.strip().endswith("}") or not received_text.strip().startswith("{"):
                logger.error("Ошибка: JSON оборван или некорректен")
                return False
            try:
                message_data = json.loads(received_text)
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                return False
            self.process_message_data(message_data)
            return True

        except socket.error as e:
            logger.error(f"Socket error: {e}")
        except Exception as e:
            logger.error(f"Connection handling error: {e}")
            self.event_bus.emit(Events.UPDATE_GAME_CONNECTION, {'is_connected': False})
        finally:
            if self.client_socket:
                self.client_socket.close()
            return False

    def process_message_data(self, message_data):
        transmitted_to_game = False
        try:
            message_id = message_data["id"]
            
            self.current_message_id = message_id

            message_type = message_data["type"]
            character = str(message_data["character"])
            
            self.event_bus.emit(Events.SET_CHARACTER_TO_CHANGE, {'character': character})

            message = message_data["input"]
            system_message = message_data["dataToSentSystem"]
            system_info = message_data["systemInfo"]

            self.event_bus.emit(Events.SET_GAME_DATA, {
                'distance': float(message_data["distance"].replace(",", ".")),
                'roomPlayer': int(message_data["roomPlayer"]),
                'roomMita': int(message_data["roomMita"]),
                'nearObjects': message_data["hierarchy"],
                'actualInfo': message_data["currentInfo"]
            })

            self.event_bus.emit(Events.SET_DIALOG_ACTIVE, {
                'active': bool(message_data.get("dialog_active", False))
            })

            image_base64_list = message_data.get("image_base64_list", [])
            decoded_image_data = []
            if image_base64_list:
                for base64_str in image_base64_list:
                    try:
                        decoded_image_data.append(base64.b64decode(base64_str))
                    except Exception as e:
                        logger.error(f"Ошибка декодирования Base64 изображения: {e}")

            if system_info != "-":
                logger.info("Добавил систем инфо " + system_info)
                self.event_bus.emit(Events.ADD_TEMPORARY_SYSTEM_INFO, {'content': system_info})

            response = ""

            

            if message == "waiting":
                if system_message != "-":
                    logger.info(f"Получено system_message {system_message} id {message_id}")
                    self.event_bus.emit_and_wait(Events.SET_ID_SOUND, {'id': message_id})
                    response = self.generate_response("", system_message, decoded_image_data)
                elif self.messages_to_say:
                    response = self.messages_to_say.pop(0)
            elif message == "boring":
                logger.info(f"Получено boring message id {message_id}")
                self.event_bus.emit_and_wait(Events.SET_ID_SOUND, {'id': message_id})
                date_now = datetime.now().replace(microsecond=0)
                response = self.generate_response("",
                                              f"Время {date_now}, Игрок долго молчит( Ты можешь что-то сказать или предпринять",
                                              decoded_image_data)
                logger.info("Отправлено Мите на озвучку: " + response)
            else:
                logger.info(f"Получено message id {message_id}")
                
                self.event_bus.emit_and_wait(Events.SET_ID_SOUND, {'id': message_id})
                self.event_bus.emit(Events.UPDATE_CHAT_UI, {
                    'role': 'user',
                    'response': message,
                    'is_initial': False,
                    'emotion': ''
                })
                response = self.generate_response(message, "", decoded_image_data)
                logger.info("Отправлено Мите на озвучку: " + response)

                if not character:
                    character = "Mita"

            user_input_result = self.event_bus.emit_and_wait(Events.GET_USER_INPUT, timeout=1.0)
            user_input = user_input_result[0] if user_input_result else ""
            
            transmitted_to_game = False
            if user_input:
                transmitted_to_game = True

            server_data_result = self.event_bus.emit_and_wait(Events.GET_SERVER_DATA, timeout=1.0)
            server_data = server_data_result[0] if server_data_result else {}
            
            settings_result = self.event_bus.emit_and_wait(Events.GET_SETTINGS, timeout=1.0)
            settings = settings_result[0] if settings_result else {}

            if server_data.get('patch_to_sound_file', '') != "":
                logger.info(f"id {message_id} Скоро передам {server_data.get('patch_to_sound_file')} id {server_data.get('id_sound')}")

            message_data = {
                "id": int(message_id),
                "type": str(message_type),
                "character": str(character),
            }
            message_data.update({
                "response": str(response),
                "silero": bool(server_data.get('silero_connected', False) and bool(settings.get("SILERO_USE"))),
                "id_sound": message_id,
                "patch_to_sound_file": str(server_data.get('patch_to_sound_file', '')),
                "user_input": str(user_input),

                "GM_ON": bool(settings.get("GM_ON")),
                "GM_READ": bool(settings.get("GM_READ")),
                "GM_VOICE": bool(settings.get("GM_VOICE")),
                "GM_REPEAT": int(settings.get("GM_REPEAT")),
                "CC_Limit_mod": int(settings.get("CC_Limit_mod")),

                "instant_send": bool(server_data.get('instant_send', False)),

                "LANGUAGE": str(settings.get("LANGUAGE")),

                "MITAS_MENU": bool(settings.get("MITAS_MENU")),
                "EMOTION_MENU": bool(settings.get("EMOTION_MENU")),

                "TEXT_WAIT_TIME": int(settings.get("TEXT_WAIT_TIME")),
                "VOICE_WAIT_TIME": int(settings.get("VOICE_WAIT_TIME")),

            })
            
            self.event_bus.emit(Events.RESET_SERVER_DATA)

            if transmitted_to_game:
                self.event_bus.emit(Events.CLEAR_USER_INPUT)

            json_message = json.dumps(message_data)
            self.client_socket.send(json_message.encode("utf-8"))

            self.event_bus.emit(Events.UPDATE_GAME_CONNECTION, {'is_connected': True})

            return True
        except Exception as e:
            logger.error(f"Ошибка обработки подключения: {e}")
            self.event_bus.emit(Events.UPDATE_GAME_CONNECTION, {'is_connected': False})
            return False
        finally:
            if self.client_socket:
                self.client_socket.close()

    def generate_response(self, input_text, system_input_text, image_data: list[bytes] = None):
        if image_data is None:
            image_data = []
        try:
            self.event_bus.emit(Events.SET_WAITING_ANSWER, {'waiting': True})
            
            message_id = getattr(self, 'current_message_id', None)

            # Используем событие вместо прямого вызова
            response_result = self.event_bus.emit_and_wait(Events.SEND_MESSAGE, {
                'user_input': input_text,
                'system_input': system_input_text,
                'image_data': image_data,
                'message_id': message_id  # Передаем message_id через событие
            }, timeout=300.0)
            
            response = response_result[0] if response_result else None
            
            return response if response else "Произошла ошибка при обработке вашего сообщения."

        except Exception as e:
            logger.error(f"Ошибка генерации ответа: {e}")
            return "Произошла ошибка при обработке вашего сообщения."
        finally:
            self.event_bus.emit(Events.SET_WAITING_ANSWER, {'waiting': False})

    async def handle_message(self, message):
        if self.text_wait_limit_enabled:
            pass

        if self.voice_wait_limit_enabled:
            pass

    def send_message_to_server(self, message):
        self.messages_to_say.append(message)

    def stop(self):
        if self.server_socket:
            self.server_socket.close()
            logger.info("Сервер остановлен.")
            self.event_bus.emit(Events.SET_CONNECTED_TO_GAME, {'connected': False})