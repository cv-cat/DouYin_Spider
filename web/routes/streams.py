import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/streams")


@router.get("/tasks")
def task_stream(request: Request):
    queue = request.app.state.broker.subscribe("tasks")

    def event_generator():
        try:
            while True:
                payload = queue.get()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            request.app.state.broker.unsubscribe("tasks", queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/events")
def event_stream(request: Request):
    queue = request.app.state.broker.subscribe("events")

    def event_generator():
        try:
            while True:
                payload = queue.get()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            request.app.state.broker.unsubscribe("events", queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
