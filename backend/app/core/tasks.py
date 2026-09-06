from typing import Callable, Any
from fastapi import BackgroundTasks

class TaskQueue:
    """
    Abstraction for background/long-running tasks.
    
    NOTE: The current implementation relies on FastAPI BackgroundTasks, 
    which DOES NOT provide durable job execution. 
    If the application restarts, pending tasks are lost.
    This abstraction allows for easy replacement with Celery, Redis Queue, 
    or another worker system in future tracks without changing service code.
    """
    def __init__(self, background_tasks: BackgroundTasks):
        self._bg = background_tasks
    
    def enqueue(self, func: Callable, *args: Any, **kwargs: Any):
        self._bg.add_task(func, *args, **kwargs)
