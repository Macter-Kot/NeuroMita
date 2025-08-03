from typing import Optional, Dict, Any
from main_logger import logger
from core.events import get_event_bus, Events, Event
from managers.task_manager import get_task_manager, TaskStatus, Task


class TaskController:
    def __init__(self):
        self.event_bus = get_event_bus()
        self.task_manager = get_task_manager()
        self._subscribe_to_events()
        
    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.Task.CREATE_TASK, self._on_create_task, weak=False)
        self.event_bus.subscribe(Events.Task.UPDATE_TASK_STATUS, self._on_update_task_status, weak=False)
        self.event_bus.subscribe(Events.Task.GET_TASK, self._on_get_task, weak=False)
        self.event_bus.subscribe(Events.Task.NOTIFY_TASK_UPDATE, self._on_notify_task_update, weak=False)
        
    def _on_create_task(self, event: Event) -> Task:
        task_type = event.data.get('type', 'chat')
        data = event.data.get('data', {})
        
        task = self.task_manager.create_task(task_type, data)
        
        # Уведомляем сервер о создании задачи
        self.event_bus.emit(Events.Task.TASK_CREATED, {'task': task})
        
        return task
        
    def _on_update_task_status(self, event: Event) -> Optional[Task]:
        uid = event.data.get('uid')
        status = event.data.get('status')
        result = event.data.get('result')
        error = event.data.get('error')
        
        if not uid or not status:
            logger.error("Missing uid or status in update_task_status event")
            return None
            
        task = self.task_manager.update_task_status(uid, status, result, error)
        
        if task:
            # Уведомляем о изменении статуса
            self.event_bus.emit(Events.Task.TASK_STATUS_CHANGED, {'task': task})
            
        return task
        
    def _on_get_task(self, event: Event) -> Optional[Task]:
        uid = event.data.get('uid')
        return self.task_manager.get_task(uid) if uid else None
        
    def _on_notify_task_update(self, event: Event):
        task = event.data.get('task')
        if task:
            # Уведомляем сервер об обновлении задачи для отправки клиенту
            self.event_bus.emit(Events.Server.SEND_TASK_UPDATE, {'task': task})