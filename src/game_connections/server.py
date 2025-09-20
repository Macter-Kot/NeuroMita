# src/game_connections/server.py
import json
import socket
import asyncio
import threading
from typing import Optional, Dict, Any, Set
from main_logger import logger
from core.events import get_event_bus, Events, Event
from managers.task_manager import TaskStatus
import uuid


class ChatServerNew:
    def __init__(self, host='127.0.0.1', port=12345):
        self.host = host
        self.port = port
        self.server_socket = None
        self.active_connections: Dict[str, asyncio.StreamWriter] = {}
        self.event_bus = get_event_bus()
        self.running = False
        self._loop = None
        self._server_task = None
        self.client_tasks: Dict[str, Set[str]] = {}
        self.last_idle_tasks: Dict[str, str] = {}
        self.pending_sysinfo: Dict[str, list[str]] = {}
        self.stub_tasks: Dict[str, Dict[str, Any]] = {}
        
        self._subscribe_to_events()

    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.Task.TASK_STATUS_CHANGED, self._on_task_status_changed, weak=False)
        self.event_bus.subscribe(Events.Server.SEND_TASK_UPDATE, self._on_send_task_update, weak=False)
        
    async def start_async(self):
        self.running = True
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        addrs = ', '.join(str(sock.getsockname()) for sock in self.server.sockets)
        logger.info(f'Новый сервер запущен на {addrs}')
        try:
            async with self.server:
                await self.server.serve_forever()
        except asyncio.CancelledError:
            logger.debug("serve_forever cancelled on shutdown (normal)")
        finally:
            self.running = False
    
    def start(self):
        self._loop = asyncio.new_event_loop()
        self._server_thread = threading.Thread(target=self._run_server_loop, daemon=True)
        self._server_thread.start()
        
    def _run_server_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self.start_async())
        
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info('peername')
        client_id = f"{addr[0]}:{addr[1]}"
        logger.info(f"Новое подключение от {client_id}")
        
        self.active_connections[client_id] = writer
        self.client_tasks[client_id] = set()
        self.event_bus.emit(Events.Server.SET_GAME_CONNECTION, {'is_connected': True})
        
        buffer = bytearray()
        decoder = json.JSONDecoder()

        try:
            while self.running:
                chunk = await reader.read(4096)
                if not chunk:
                    break

                buffer.extend(chunk)

                while buffer:
                    try:
                        buf_str = buffer.decode('utf-8')
                        obj, idx = decoder.raw_decode(buf_str)

                        await self.process_request(obj, client_id)

                        del buffer[:len(buf_str[:idx].encode('utf-8'))]
                        while buffer and chr(buffer[0]).isspace():
                            buffer.pop(0)

                    except json.JSONDecodeError:
                        break
                    except UnicodeDecodeError:
                        break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Ошибка в handle_client: {e}", exc_info=True)
        finally:
            self.active_connections.pop(client_id, None)
            if client_id in self.client_tasks:
                del self.client_tasks[client_id]
            writer.close()
            await writer.wait_closed()
            logger.info(f"Клиент {client_id} отключился")
            if not self.active_connections:
                self.event_bus.emit(Events.Server.SET_GAME_CONNECTION, {'is_connected': False})
    
    async def process_request(self, request: Dict[str, Any], client_id: str):
        action = request.get('action')
        
        if action == 'create_task':
            await self.handle_create_task(request, client_id)
        elif action == 'get_task_status':
            await self.handle_get_task_status(request, client_id)
        else:
            await self.send_error(self.active_connections[client_id], f"Unknown action: {action}")
    
    def _get_settings(self) -> Dict[str, Any]:
        try:
            res = self.event_bus.emit_and_wait(Events.Settings.GET_SETTINGS, timeout=1.0)
            return res[0] if res else {}
        except Exception:
            return {}

    def _should_block_event(self, event_type: str) -> bool:
        settings = self._get_settings()
        if not settings.get('IGNORE_GAME_REQUESTS', False):
            return False
        block_level = settings.get('GAME_BLOCK_LEVEL', 'Idle events')
        if event_type == 'idle_timeout' and block_level in ('Idle events', 'All events'):
            return True
        return False

    async def _send_blocked_stub(self, client_id: str, event_type: str, character: str, reason: str = 'Blocked by settings'):
        if client_id not in self.active_connections:
            return

        writer = self.active_connections[client_id]
        stub_uid = f"blk_{uuid.uuid4().hex}"

        self.stub_tasks[stub_uid] = {
            "uid": stub_uid,
            "status": TaskStatus.SUCCESS.value,
            "type": "idle",
            "result": {
                "text": "",
                "voiceover_path": "",
                "instant_send": False
            },
            "meta": {
                "blocked": True,
                "reason": reason,
                "event_type": event_type,
                "character": character
            }
        }

        await self.send_json(writer, {"task_uid": stub_uid, "blocked": True})

        await self.send_json(writer, {
            "type": "task_update",
            "uid": stub_uid,
            "status": TaskStatus.SUCCESS.value,
            "body": self.stub_tasks[stub_uid]
        })

        logger.info(f"Заблокировано событие '{event_type}' для персонажа '{character}', uid={stub_uid}")
    
    async def handle_create_task(self, request: Dict[str, Any], client_id: str):
        event_type = request.get('type', 'answer')
        character = request.get('character', 'Mita')
        data = request.get('data', {})
        context = request.get('context', {})
        
        self.event_bus.emit(Events.Model.SET_CHARACTER_TO_CHANGE, {'character': character})
        
        self.event_bus.emit(Events.Server.SET_GAME_DATA, {
            'distance': float(context.get('distance', '0').replace(',', '.')),
            'roomPlayer': int(context.get('roomPlayer', 0)),
            'roomMita': int(context.get('roomMita', 0)),
            'nearObjects': context.get('hierarchy', ''),
            'actualInfo': context.get('currentInfo', '')
        })
        
        if event_type == 'answer':
            user_input = data.get('message', '')

            if user_input:
                self.event_bus.emit(Events.GUI.UPDATE_CHAT_UI, {
                    'role': 'user',
                    'response': user_input,
                    'is_initial': False,
                    'emotion': ''
                })
            
            collected_sys = "\n".join(self.pending_sysinfo.pop(character, []))
            
            task_result = self.event_bus.emit_and_wait(Events.Task.CREATE_TASK, {
                'type': 'chat',
                'data': {
                    'character': character,
                    'user_input': user_input,
                    'system_input': collected_sys,
                    'system_info': context.get('currentInfo', ''),
                    'client_id': client_id,
                    'event_type': event_type
                }
            }, timeout=5.0)
            
            task = task_result[0] if task_result else None
            
            if task:
                self.client_tasks[client_id].add(task.uid)
                
                response = {
                    "task_uid": task.uid
                }
                await self.send_json(self.active_connections[client_id], response)
                
                self.event_bus.emit(Events.Chat.SEND_MESSAGE, {
                    'user_input': user_input,
                    'system_input': collected_sys,
                    'image_data': context.get('image_base64_list', []),
                    'task_uid': task.uid
                })
            else:
                await self.send_error(self.active_connections[client_id], "Failed to create task")
                
        elif event_type == 'idle_timeout':
            if self._should_block_event(event_type):
                await self._send_blocked_stub(client_id, event_type, character)
                return

            last_idle_uid = self.last_idle_tasks.get(character)
            if last_idle_uid:
                last_task_result = self.event_bus.emit_and_wait(Events.Task.GET_TASK, {
                    'uid': last_idle_uid
                }, timeout=1.0)
                last_task = last_task_result[0] if last_task_result else None
                
                if last_task and last_task.status == TaskStatus.PENDING:
                    logger.info(f"Игнорируем дубликат idle события для {character}, предыдущая задача еще не завершена")
                    response = {
                        "task_uid": last_idle_uid
                    }
                    await self.send_json(self.active_connections[client_id], response)
                    return
            
            collected_sys = "\n".join(self.pending_sysinfo.pop(character, []))
            
            task_result = self.event_bus.emit_and_wait(Events.Task.CREATE_TASK, {
                'type': 'idle',
                'data': {
                    'character': character,
                    'message': data.get('message', 'Player idle for 90 seconds'),
                    'system_input': collected_sys,
                    'client_id': client_id,
                    'event_type': event_type
                }
            }, timeout=5.0)
            
            task = task_result[0] if task_result else None
            
            if task:
                self.client_tasks[client_id].add(task.uid)
                
                self.last_idle_tasks[character] = task.uid
                
                response = {
                    "task_uid": task.uid
                }
                await self.send_json(self.active_connections[client_id], response)
                
                idle_prompt = "The player has been silent for 90 seconds. React naturally to this silence."
                if collected_sys:
                    idle_prompt += f"\n\nAdditional context:\n{collected_sys}"
                
                self.event_bus.emit(Events.Chat.SEND_MESSAGE, {
                    'user_input': '',
                    'system_input': idle_prompt,
                    'image_data': [],
                    'task_uid': task.uid
                })
            else:
                await self.send_error(self.active_connections[client_id], "Failed to create idle task")
                
        elif event_type == 'position_move':
            logger.info(f"Position move event from {character}: {data}")
            
            response = {
                "task_uid": f"pos_{uuid.uuid4()}"
            }
            await self.send_json(self.active_connections[client_id], response)
            
        elif event_type == 'system_info':
            msg = data.get('message', '')
            if msg:
                self.pending_sysinfo.setdefault(character, []).append(msg)
                logger.info(f"Buffered system_info for {character}: {msg[:60]}...")
            
            await self.send_json(self.active_connections[client_id], {
                "task_uid": f"sys_{uuid.uuid4()}",
                "stored": len(self.pending_sysinfo.get(character, []))
            })
            
        elif event_type == 'system_info_flush':
            collected_sys = "\n".join(self.pending_sysinfo.pop(character, []))
            
            if not collected_sys:
                await self.send_error(
                    self.active_connections[client_id],
                    "No pending system_info to flush"
                )
                return
            
            task_result = self.event_bus.emit_and_wait(Events.Task.CREATE_TASK, {
                'type': 'chat',
                'data': {
                    'character': character,
                    'user_input': '',
                    'system_input': collected_sys,
                    'system_info': context.get('currentInfo', ''),
                    'client_id': client_id,
                    'event_type': event_type
                }
            }, timeout=5.0)
            
            task = task_result[0] if task_result else None
            if task:
                self.client_tasks[client_id].add(task.uid)
                await self.send_json(self.active_connections[client_id], {
                    "task_uid": task.uid
                })
                
                self.event_bus.emit(Events.Chat.SEND_MESSAGE, {
                    'user_input': '',
                    'system_input': collected_sys,
                    'image_data': [],
                    'task_uid': task.uid
                })
            else:
                await self.send_error(self.active_connections[client_id], "Failed to flush system info")
            
        else:
            await self.send_error(self.active_connections[client_id], f"Unknown event type: {event_type}")
    
    async def handle_get_task_status(self, request: Dict[str, Any], client_id: str):
        task_uid = request.get('task_uid')
        
        if not task_uid:
            await self.send_error(self.active_connections[client_id], "Missing task_uid")
            return

        if task_uid in self.stub_tasks:
            response = self.stub_tasks.pop(task_uid)
            await self.send_json(self.active_connections[client_id], response)
            return
            
        task_result = self.event_bus.emit_and_wait(Events.Task.GET_TASK, {
            'uid': task_uid
        }, timeout=1.0)
        
        task = task_result[0] if task_result else None
        
        if task:
            response = task.to_dict()
            
            if task.status == TaskStatus.SUCCESS and task.result:
                audio_path = task.result.get('voiceover_path', '')
                if audio_path:
                    response['result']['audio_path'] = audio_path
                    
                silero_result = self.event_bus.emit_and_wait(Events.Telegram.GET_SILERO_STATUS, timeout=1.0)
                response['silero_connected'] = silero_result[0] if silero_result else False
                
                gm_character = self.event_bus.emit_and_wait(Events.Model.GET_CURRENT_CHARACTER, timeout=1.0)
                current_char = gm_character[0] if gm_character else {}
                is_gm = current_char.get('name') == 'GameMaster'
                
                response['GM_ON'] = is_gm
                response['GM_READ'] = is_gm
                response['GM_VOICE'] = is_gm and self.event_bus.emit_and_wait(Events.Settings.GET_SETTING, {'key': 'GM_VOICE'}, timeout=1.0)[0]
                
            await self.send_json(self.active_connections[client_id], response)
        else:
            await self.send_error(self.active_connections[client_id], f"Task {task_uid} not found")
    
    def _on_task_status_changed(self, event: Event):
        task = event.data.get('task')
        if not task or not getattr(task, 'data', None):
            return

        client_id  = task.data.get('client_id')
        character  = task.data.get('character')
        event_type = task.data.get('event_type')

        if client_id and client_id in self.active_connections:
            asyncio.run_coroutine_threadsafe(
                self.send_task_update(client_id, task),
                self._loop
            )

        if event_type in ('idle', 'idle_timeout') and character:
            if task.status in (TaskStatus.SUCCESS,
                            TaskStatus.FAILED,
                            TaskStatus.CANCELLED):
                if self.last_idle_tasks.get(character) == task.uid:
                    del self.last_idle_tasks[character]
    
    def _on_send_task_update(self, event: Event):
        task = event.data.get('task')
        if task and hasattr(task, 'data') and task.data:
            client_id = task.data.get('client_id')
            if client_id and client_id in self.active_connections:
                asyncio.run_coroutine_threadsafe(
                    self.send_task_update(client_id, task),
                    self._loop
                )
    
    async def send_task_update(self, client_id: str, task):
        if client_id not in self.active_connections:
            return
            
        writer = self.active_connections[client_id]
        
        message = {
            "type": "task_update",
            "uid": task.uid,
            "status": task.status.value,
            "body": task.to_dict()
        }
        logger.success(message)
        
        await self.send_json(writer, message)
    
    async def send_json(self, writer: asyncio.StreamWriter, data: Dict[str, Any]):
        try:
            json_str = json.dumps(data)
            writer.write(json_str.encode('utf-8'))
            writer.write(b'\n')
            await writer.drain()
        except Exception as e:
            logger.error(f"Ошибка отправки JSON: {e}")
    
    async def send_error(self, writer: asyncio.StreamWriter, error: str):
        await self.send_json(writer, {"type": "error", "error": error})
    
    def stop(self):
        self.running = False
        
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)
            try:
                future.result(timeout=5)
            except Exception as e:
                logger.warning(f"Ошибка при остановке сервера: {e}")
        
        if hasattr(self, '_server_thread') and self._server_thread:
            self._server_thread.join(timeout=5)
            if self._server_thread.is_alive():
                logger.warning("Server thread did not stop in time")

    async def _async_stop(self):
        if hasattr(self, 'server'):
            self.server.close()
            await self.server.wait_closed()

        for writer in list(self.active_connections.values()):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        self.active_connections.clear()