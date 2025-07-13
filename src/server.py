import base64
import json
import socket
from datetime import datetime

from main_logger import logger
from core.events import get_event_bus, Events

class ChatServer:
    def __init__(self, controller, chat_model, host='127.0.0.1', port=12345):
        # Инициализация сервера с GUI, моделью чата и сетевыми параметрами
        self.host = host  # IP-адрес сервера
        self.port = port  # Порт сервера
        self.controller = controller  # Ссылка на графический интерфейс
        self.server_socket = None  # Основной серверный сокет
        self.client_socket = None  # Сокет для активного клиента
        self.passive_client_socket = None  # Резервный клиентский сокет (не используется)
        self.passive_server_socket = None  # Резервный серверный сокет (не используется)
        self.chat_model = chat_model  # Модель обработки сообщений
        self.messages_to_say = []  # Очередь сообщений для отправки
        self.text_wait_limit_enabled = False
        self.voice_wait_limit_enabled = False
        self.event_bus = get_event_bus()
        

    def start(self):
        """Инициализирует и запускает сервер, создавая TCP-сокет."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))  # Привязка к адресу
        self.server_socket.listen(5)  # Ожидание подключений (макс. 5 в очереди)
        logger.info(f"Сервер запущен на {self.host}:{self.port}")

    #TODO РЕФАКТОРЬ РЕФАКТОРЬ РЕФАКТОРЬ!
    def handle_connection(self):
        """Обрабатывает одно подключение."""
        # Проверка инициализации сервера
        if not self.server_socket:
            raise RuntimeError("Сервер не запущен. Вызовите start() перед handle_connection().")
        try:
            # Получаем настройки через события
            settings_result = self.event_bus.emit_and_wait(Events.GET_SETTINGS, timeout=1.0)
            settings = settings_result[0] if settings_result else {}
            
            self.text_wait_limit_enabled = settings.get("LIMIT_TEXT_WAIT", False)
            self.voice_wait_limit_enabled = settings.get("LIMIT_VOICE_WAIT", False)

            #logger.info("Жду получения от клиента игры")
            # Ожидание подключения
            self.client_socket, addr = self.server_socket.accept()
            #logger.info(f"Подключен {addr}")

            # Чтение данных по частям, чтобы обрабатывать большие сообщения (например, с изображениями)
            received_data = b""
            while True:
                chunk = self.client_socket.recv(65536)  # Увеличиваем буфер для чтения
                if not chunk:
                    break
                received_data += chunk
                # Простая эвристика для определения конца JSON.
                # В более надежной системе лучше передавать размер данных.
                if b"}" in chunk and received_data.count(b"{") == received_data.count(b"}"):
                    break
            
            received_text = received_data.decode("utf-8")

            # Логируем полученные данные
            #logger.info(f"Получено: {received_text}")

            # Валидация JSON структуры
            if not received_text.strip().endswith("}") or not received_text.strip().startswith("{"):
                logger.error("Ошибка: JSON оборван или некорректен")
                return False
            # Парсинг JSON данных
            try:
                message_data = json.loads(received_text)
                #logger.info("JSON успешно разобран!")
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                return False
            # Обработка распарсенных данных
            self.process_message_data(message_data)
            return True

        except socket.error as e:
            logger.error(f"Socket error: {e}")
        except Exception as e:
            logger.error(f"Connection handling error: {e}")
            self.event_bus.emit(Events.UPDATE_GAME_CONNECTION, {'is_connected': False})
        finally:
            if self.client_socket:
                self.client_socket.close()  # Важно закрывать соединение
            return False

    def process_message_data(self, message_data):
        """Обрабатывает распарсенные данные сообщения. Возвращает статус обработки."""
        transmitted_to_game = False
        try:
            # Извлечение базовых параметров сообщения
            #print(f"Json {message_data}")

            message_id = message_data["id"]  # Уникальный идентификатор сообщения
            # Уникальный идентификатор сообщения для вывода в окне

            message_type = message_data["type"]  # Тип сообщения (системное/пользовательское)
            character = str(message_data["character"])  # Персонаж-отправитель
            
            # Устанавливаем персонажа через событие
            self.event_bus.emit(Events.SET_CHARACTER_TO_CHANGE, {'character': character})

            message = message_data["input"]  # Текст сообщения
            system_message = message_data["dataToSentSystem"]
            system_info = message_data["systemInfo"]

            # Устанавливаем игровые данные через событие
            self.event_bus.emit(Events.SET_GAME_DATA, {
                'distance': float(message_data["distance"].replace(",", ".")),
                'roomPlayer': int(message_data["roomPlayer"]),
                'roomMita': int(message_data["roomMita"]),
                'nearObjects': message_data["hierarchy"],
                'actualInfo': message_data["currentInfo"]
            })

            # Устанавливаем dialog_active через событие
            self.event_bus.emit(Events.SET_DIALOG_ACTIVE, {
                'active': bool(message_data.get("dialog_active", False))
            })

            # Новое: извлечение данных изображения
            image_base64_list = message_data.get("image_base64_list", [])
            decoded_image_data = []
            if image_base64_list:
                for base64_str in image_base64_list:
                    try:
                        decoded_image_data.append(base64.b64decode(base64_str))
                    except Exception as e:
                        logger.error(f"Ошибка декодирования Base64 изображения: {e}")
                        # Можно пропустить некорректное изображение или вернуть ошибку

            if system_info != "-":
                logger.info("Добавил систем инфо " + system_info)
                self.event_bus.emit(Events.ADD_TEMPORARY_SYSTEM_INFO, {'content': system_info})

            response = ""

            # Обработка системных сообщений
            if message == "waiting":
                if system_message != "-":
                    logger.info(f"Получено system_message {system_message} id {message_id}")
                    self.event_bus.emit(Events.SET_ID_SOUND, {'id': message_id})
                    response = self.generate_response("", system_message, decoded_image_data)
                    self.event_bus.emit(Events.UPDATE_CHAT, {
                        'role': 'assistant',
                        'content': response,
                        'is_initial': False,
                        'emotion': ''
                    })
                elif self.messages_to_say:
                    response = self.messages_to_say.pop(0)
            elif message == "boring":
                logger.info(f"Получено boring message id {message_id}")
                date_now = datetime.now().replace(microsecond=0)
                self.event_bus.emit(Events.SET_ID_SOUND, {'id': message_id})
                response = self.generate_response("",
                                                  f"Время {date_now}, Игрок долго молчит( Ты можешь что-то сказать или предпринять",
                                                  decoded_image_data)
                self.event_bus.emit(Events.UPDATE_CHAT, {
                    'role': 'assistant',
                    'content': response,
                    'is_initial': False,
                    'emotion': ''
                })
                logger.info("Отправлено Мите на озвучку: " + response)
            else:
                logger.info(f"Получено message id {message_id}")
                # Если игрок отправил внутри игры, message его
                self.event_bus.emit(Events.SET_ID_SOUND, {'id': message_id})
                self.event_bus.emit(Events.UPDATE_CHAT, {
                    'role': 'user',
                    'content': message,
                    'is_initial': False,
                    'emotion': ''
                })
                response = self.generate_response(message, "", decoded_image_data)
                self.event_bus.emit(Events.UPDATE_CHAT, {
                    'role': 'assistant',
                    'content': response,
                    'is_initial': False,
                    'emotion': ''
                })
                logger.info("Отправлено Мите на озвучку: " + response)

                if not character:
                    character = "Mita"

            # Получаем данные через события
            user_input_result = self.event_bus.emit_and_wait(Events.GET_USER_INPUT, timeout=1.0)
            user_input = user_input_result[0] if user_input_result else ""
            
            transmitted_to_game = False
            if user_input:
                transmitted_to_game = True

            # Получаем остальные данные через события
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
                "id_sound": int(server_data.get('id_sound', 0)),
                "patch_to_sound_file": str(server_data.get('patch_to_sound_file', '')),
                "user_input": str(user_input),

                # Простите, но я хотел за вечер затестить
                "GM_ON": bool(settings.get("GM_ON")),
                "GM_READ": bool(settings.get("GM_READ")),
                "GM_VOICE": bool(settings.get("GM_VOICE")),
                "GM_REPEAT": int(settings.get("GM_REPEAT")),
                "CC_Limit_mod": int(settings.get("CC_Limit_mod")),

                "instant_send": bool(server_data.get('instant_send', False)),

                "LANGUAGE": str(settings.get("LANGUAGE")),

                "MITAS_MENU": bool(settings.get("MITAS_MENU")),
                "EMOTION_MENU": bool(settings.get("EMOTION_MENU")),
               # "TEST_MITAS": bool(self.gui.settings.get("TEST_MITAS")),

                "TEXT_WAIT_TIME": int(settings.get("TEXT_WAIT_TIME")),
                "VOICE_WAIT_TIME": int(settings.get("VOICE_WAIT_TIME")),

            })
            #logger.info(message_data)
            
            # Сбрасываем instant_send и patch_to_sound_file через событие
            self.event_bus.emit(Events.RESET_SERVER_DATA)

            if transmitted_to_game:
                self.event_bus.emit(Events.CLEAR_USER_INPUT)

            # Отправляем JSON через сокет
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
        """Генерирует текст с помощью модели."""
        if image_data is None:
            image_data = []
        try:
            self.event_bus.emit(Events.SET_WAITING_ANSWER, {'waiting': True})

            # Генерируем ответ через событие
            response_result = self.event_bus.emit_and_wait(Events.GENERATE_RESPONSE, {
                'user_input': input_text,
                'system_input': system_input_text,
                'image_data': image_data
            }, timeout=120.0)
            
            response = response_result[0] if response_result else "Произошла ошибка при обработке вашего сообщения."

        except Exception as e:
            logger.error(f"Ошибка генерации ответа: {e}")
            response = "Произошла ошибка при обработке вашего сообщения."

            self.event_bus.emit(Events.SET_WAITING_ANSWER, {'waiting': False})
        return response

    async def handle_message(self, message):
        """Обрабатывает сообщение. Будущая реализация: добавление ограничений по времени для текста и голоса."""
        if self.text_wait_limit_enabled:
            # TODO: Ждем ограничение по времени для текста
            pass

        if self.voice_wait_limit_enabled:
            # TODO: Ждем ограничение по времени для голоса
            pass

    def send_message_to_server(self, message):
        self.messages_to_say.append(message)

    def stop(self):
        """Закрывает сервер."""
        if self.server_socket:
            self.server_socket.close()
            logger.info("Сервер остановлен.")
            self.event_bus.emit(Events.SET_CONNECTED_TO_GAME, {'connected': False})