import logging

from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import bleach
import httpx
import socketio
import validators

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    JSONRPCErrorResponse,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Role,
    SendMessageRequest,
    SendMessageResponse,
    SendStreamingMessageRequest,
    SendStreamingMessageResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskIdParams,
    TaskStatusUpdateEvent,
    TextPart,
)
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from task_tracker import TaskTracker


STANDARD_HEADERS = {
    'host',
    'user-agent',
    'accept',
    'content-type',
    'content-length',
    'connection',
    'accept-encoding',
}

# ==============================================================================
# Setup
# ==============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

app = FastAPI()
# NOTE: In a production environment, cors_allowed_origins should be restricted
# to the specific frontend domain, not a wildcard '*'.
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_app = socketio.ASGIApp(sio)
app.mount('/socket.io', socket_app)

app.mount('/static', StaticFiles(directory='../frontend/public'), name='static')
templates = Jinja2Templates(directory='../frontend/public')

# ==============================================================================
# State Management
# ==============================================================================

# NOTE: This global dictionary stores state. For a simple inspector tool with
# transient connections, this is acceptable. For a scalable production service,
# a more robust state management solution (e.g., Redis) would be required.
clients: dict[str, tuple[httpx.AsyncClient, A2AClient, AgentCard]] = {}

# Task tracker for dashboard
task_tracker = TaskTracker(max_tasks=1000)


# ==============================================================================
# Socket.IO Event Helpers
# ==============================================================================


async def _emit_debug_log(
    sid: str, event_id: str, log_type: str, data: Any
) -> None:
    """Helper to emit a structured debug log event to the client."""
    await sio.emit(
        'debug_log', {'type': log_type, 'data': data, 'id': event_id}, to=sid
    )


async def _process_a2a_response(
    result: SendMessageResponse | SendStreamingMessageResponse,
    sid: str,
    request_id: str,
    agent_url: str | None = None,
) -> None:
    """Processes a response from the A2A client, validates it, and emits events.

    Handles both success and error responses. Also tracks tasks for the dashboard.

    Args:
        result: The response from the A2A client
        sid: The socket ID of the client
        request_id: The request ID
        agent_url: Optional agent URL for task tracking
    """
    if isinstance(result.root, JSONRPCErrorResponse):
        error_data = result.root.error.model_dump(exclude_none=True)
        await _emit_debug_log(sid, request_id, 'error', error_data)
        await sio.emit(
            'agent_response',
            {
                'error': error_data.get('message', 'Unknown error'),
                'id': request_id,
            },
            to=sid,
        )
        return

    # Success case
    event = result.root.result
    # The response payload 'event' (Task, Message, etc.) may have its own 'id',
    # which can differ from the JSON-RPC request/response 'id'. We prioritize
    # the payload's ID for client-side correlation if it exists.
    response_id = getattr(event, 'id', request_id)

    response_data = event.model_dump(exclude_none=True)
    response_data['id'] = response_id

    validation_errors = validators.validate_message(response_data)
    response_data['validation_errors'] = validation_errors

    # Track task if this is a Task object
    if isinstance(event, Task) and agent_url:
        logger.info(f'Tracking task {event.id} with context_id={event.context_id}')
        task_tracker.add_task(event, agent_url)
        # Broadcast task update to subscribers
        room_name = f'tasks_{agent_url}'
        task_data = event.model_dump(exclude_none=True)  # Don't exclude None to keep consistent structure
        await sio.emit(
            'task_update',
            {'task': task_data},
            room=room_name,
        )
        logger.debug(f'Tracked task {event.id} for agent {agent_url}, context_id: {event.context_id}')

    # Handle streaming status updates
    elif isinstance(event, TaskStatusUpdateEvent) and agent_url:
        # Get the existing task and update its status
        task = task_tracker.get_task(event.task_id)
        if task:
            task.status = event.status
            task_tracker.add_task(task, agent_url)
            # Broadcast updated task to dashboard subscribers
            room_name = f'tasks_{agent_url}'
            await sio.emit(
                'task_update',
                {'task': task.model_dump(exclude_none=True)},
                room=room_name,
            )
            logger.debug(f'Updated status for task {event.task_id}')

    # Handle streaming artifact updates
    elif isinstance(event, TaskArtifactUpdateEvent) and agent_url:
        # Get the existing task and add/update artifact
        task = task_tracker.get_task(event.task_id)
        if task:
            # Initialize artifacts list if None
            if task.artifacts is None:
                task.artifacts = []

            # Add or append artifact
            if event.append and task.artifacts:
                # Find existing artifact and append
                for i, existing_artifact in enumerate(task.artifacts):
                    if existing_artifact.name == event.artifact.name:
                        # Append parts to existing artifact
                        task.artifacts[i].parts.extend(event.artifact.parts)
                        break
                else:
                    # Artifact not found, add new one
                    task.artifacts.append(event.artifact)
            else:
                # Add new artifact
                task.artifacts.append(event.artifact)

            task_tracker.add_task(task, agent_url)
            # Broadcast updated task to dashboard subscribers
            room_name = f'tasks_{agent_url}'
            await sio.emit(
                'task_update',
                {'task': task.model_dump(exclude_none=True)},
                room=room_name,
            )
            logger.debug(f'Updated artifact for task {event.task_id}')

    await _emit_debug_log(sid, response_id, 'response', response_data)
    await sio.emit('agent_response', response_data, to=sid)


def get_card_resolver(
    client: httpx.AsyncClient, agent_card_url: str
) -> A2ACardResolver:
    """Returns an A2ACardResolver for the given agent card URL."""
    parsed_url = urlparse(agent_card_url)
    base_url = f'{parsed_url.scheme}://{parsed_url.netloc}'
    path_with_query = urlunparse(
        ('', '', parsed_url.path, '', parsed_url.query, '')
    )
    card_path = path_with_query.lstrip('/')
    if card_path:
        card_resolver = A2ACardResolver(
            client, base_url, agent_card_path=card_path
        )
    else:
        card_resolver = A2ACardResolver(client, base_url)

    return card_resolver


# ==============================================================================
# FastAPI Routes
# ==============================================================================


@app.get('/', response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serve the main index.html page."""
    return templates.TemplateResponse('index.html', {'request': request})


@app.get('/api/tasks/stats')
async def get_task_stats(
    agent_url: str | None = Query(None, description='Filter by agent URL'),
) -> JSONResponse:
    """Get task statistics.

    Args:
        agent_url: Optional agent URL to filter stats

    Returns:
        JSON response with task statistics
    """
    try:
        stats = task_tracker.get_stats(agent_url=agent_url)
        return JSONResponse(content=stats, status_code=200)
    except Exception as e:
        logger.error(f'Failed to get task stats: {e}', exc_info=True)
        return JSONResponse(
            content={'error': f'Failed to get task stats: {str(e)}'}, status_code=500
        )


@app.get('/api/tasks')
async def list_tasks(
    agent_url: str | None = Query(None, description='Filter by agent URL'),
    context_id: str | None = Query(None, description='Filter by context ID'),
    state: str | None = Query(None, description='Filter by task state'),
    limit: int = Query(50, ge=1, le=100, description='Maximum results to return'),
    offset: int = Query(0, ge=0, description='Pagination offset'),
) -> JSONResponse:
    """List tasks with optional filtering and pagination.

    Args:
        agent_url: Optional agent URL to filter tasks
        context_id: Optional context ID to filter tasks
        state: Optional task state to filter (submitted, working, completed, failed, cancelled)
        limit: Maximum number of tasks to return (1-100)
        offset: Number of tasks to skip for pagination

    Returns:
        JSON response with tasks array and pagination info
    """
    try:
        tasks, total = task_tracker.get_tasks(
            agent_url=agent_url,
            context_id=context_id,
            state=state,
            limit=limit,
            offset=offset,
        )

        # Convert tasks to dict format
        tasks_data = [task.model_dump(exclude_none=True) for task in tasks]

        return JSONResponse(
            content={
                'tasks': tasks_data,
                'total': total,
                'limit': limit,
                'offset': offset,
            },
            status_code=200,
        )
    except Exception as e:
        logger.error(f'Failed to list tasks: {e}', exc_info=True)
        return JSONResponse(
            content={'error': f'Failed to list tasks: {str(e)}'}, status_code=500
        )


@app.get('/api/tasks/{task_id}')
async def get_task_detail(task_id: str) -> JSONResponse:
    """Get detailed information for a specific task.

    Args:
        task_id: The task ID to retrieve

    Returns:
        JSON response with task details
    """
    try:
        task = task_tracker.get_task(task_id)

        if task is None:
            return JSONResponse(
                content={'error': f'Task not found: {task_id}'}, status_code=404
            )

        return JSONResponse(
            content=task.model_dump(exclude_none=True), status_code=200
        )
    except Exception as e:
        logger.error(f'Failed to get task {task_id}: {e}', exc_info=True)
        return JSONResponse(
            content={'error': f'Failed to get task: {str(e)}'}, status_code=500
        )


@app.post('/agent-card')
async def get_agent_card(request: Request) -> JSONResponse:
    """Fetch and validate the agent card from a given URL."""
    # 1. Parse request and get sid. If this fails, we can't do much.
    try:
        request_data = await request.json()
        agent_url = request_data.get('url')
        sid = request_data.get('sid')

        if not agent_url or not sid:
            return JSONResponse(
                content={'error': 'Agent URL and SID are required.'},
                status_code=400,
            )
    except Exception:
        logger.warning('Failed to parse JSON from /agent-card request.')
        return JSONResponse(
            content={'error': 'Invalid request body.'}, status_code=400
        )

    # Extract custom headers from the request
    custom_headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in STANDARD_HEADERS
    }

    # 2. Log the request.
    await _emit_debug_log(
        sid,
        'http-agent-card',
        'request',
        {
            'endpoint': '/agent-card',
            'payload': request_data,
            'custom_headers': custom_headers,
        },
    )

    # 3. Perform the main action and prepare response.
    try:
        async with httpx.AsyncClient(
            timeout=30.0, headers=custom_headers
        ) as client:
            card_resolver = get_card_resolver(client, agent_url)
            card = await card_resolver.get_agent_card()

        card_data = card.model_dump(exclude_none=True)
        validation_errors = validators.validate_agent_card(card_data)
        response_data = {
            'card': card_data,
            'validation_errors': validation_errors,
        }
        response_status = 200

    except httpx.RequestError as e:
        logger.error(
            f'Failed to connect to agent at {agent_url}', exc_info=True
        )
        response_data = {'error': f'Failed to connect to agent: {e}'}
        response_status = 502  # Bad Gateway
    except Exception as e:
        logger.error('An internal server error occurred', exc_info=True)
        response_data = {'error': f'An internal server error occurred: {e}'}
        response_status = 500

    # 4. Log the response and return it.
    await _emit_debug_log(
        sid,
        'http-agent-card',
        'response',
        {'status': response_status, 'payload': response_data},
    )
    return JSONResponse(content=response_data, status_code=response_status)


# ==============================================================================
# Socket.IO Event Handlers
# ==============================================================================


@sio.on('connect')
async def handle_connect(sid: str, environ: dict[str, Any]) -> None:
    """Handle the 'connect' socket.io event."""
    logger.info(f'Client connected: {sid}, environment: {environ}')


@sio.on('disconnect')
async def handle_disconnect(sid: str) -> None:
    """Handle the 'disconnect' socket.io event."""
    logger.info(f'Client disconnected: {sid}')
    if sid in clients:
        httpx_client, _, _ = clients.pop(sid)
        await httpx_client.aclose()
        logger.info(f'Cleaned up client for {sid}')


@sio.on('initialize_client')
async def handle_initialize_client(sid: str, data: dict[str, Any]) -> None:
    """Handle the 'initialize_client' socket.io event."""
    agent_card_url = data.get('url')

    custom_headers = data.get('customHeaders', {})

    if not agent_card_url:
        await sio.emit(
            'client_initialized',
            {'status': 'error', 'message': 'Agent URL is required.'},
            to=sid,
        )
        return
    try:
        httpx_client = httpx.AsyncClient(timeout=600.0, headers=custom_headers)
        card_resolver = get_card_resolver(httpx_client, agent_card_url)
        card = await card_resolver.get_agent_card()
        a2a_client = A2AClient(httpx_client, agent_card=card)
        clients[sid] = (httpx_client, a2a_client, card)
        await sio.emit('client_initialized', {'status': 'success'}, to=sid)
    except Exception as e:
        logger.error(
            f'Failed to initialize client for {sid}: {e}', exc_info=True
        )
        await sio.emit(
            'client_initialized', {'status': 'error', 'message': str(e)}, to=sid
        )


@sio.on('send_message')
async def handle_send_message(sid: str, json_data: dict[str, Any]) -> None:
    """Handle the 'send_message' socket.io event."""
    message_text = bleach.clean(json_data.get('message', ''))

    message_id = json_data.get('id', str(uuid4()))
    context_id = json_data.get('contextId')
    metadata = json_data.get('metadata', {})

    if sid not in clients:
        await sio.emit(
            'agent_response',
            {'error': 'Client not initialized.', 'id': message_id},
            to=sid,
        )
        return

    _, a2a_client, card = clients[sid]

    # Get agent URL for task tracking
    agent_url = card.url if card else None

    message = Message(
        role=Role.user,
        parts=[TextPart(text=str(message_text))],  # type: ignore[list-item]
        message_id=message_id,
        context_id=context_id,
        metadata=metadata,
    )
    payload = MessageSendParams(
        message=message,
        configuration=MessageSendConfiguration(
            accepted_output_modes=['text/plain', 'video/mp4']
        ),
    )

    supports_streaming = (
        hasattr(card.capabilities, 'streaming')
        and card.capabilities.streaming is True
    )

    try:
        if supports_streaming:
            stream_request = SendStreamingMessageRequest(
                id=message_id,
                method='message/stream',
                jsonrpc='2.0',
                params=payload,
            )
            await _emit_debug_log(
                sid,
                message_id,
                'request',
                stream_request.model_dump(exclude_none=True),
            )
            response_stream = a2a_client.send_message_streaming(stream_request)
            async for stream_result in response_stream:
                await _process_a2a_response(stream_result, sid, message_id, agent_url)
        else:
            send_message_request = SendMessageRequest(
                id=message_id,
                method='message/send',
                jsonrpc='2.0',
                params=payload,
            )
            await _emit_debug_log(
                sid,
                message_id,
                'request',
                send_message_request.model_dump(exclude_none=True),
            )
            send_result = await a2a_client.send_message(send_message_request)
            await _process_a2a_response(send_result, sid, message_id, agent_url)

    except Exception as e:
        logger.error(f'Failed to send message for sid {sid}', exc_info=True)
        await sio.emit(
            'agent_response',
            {'error': f'Failed to send message: {e}', 'id': message_id},
            to=sid,
        )


@sio.on('subscribe_to_tasks')
async def handle_subscribe_to_tasks(sid: str, data: dict[str, Any]) -> None:
    """Handle the 'subscribe_to_tasks' socket.io event.

    Subscribes a client to receive real-time task updates for a specific agent.
    """
    agent_url = data.get('agent_url')

    if not agent_url:
        await sio.emit(
            'task_subscription_response',
            {'status': 'error', 'message': 'Agent URL is required'},
            to=sid,
        )
        return

    # Add client to a room for this agent's task updates
    room_name = f'tasks_{agent_url}'
    await sio.enter_room(sid, room_name)

    logger.info(f'Client {sid} subscribed to tasks for agent: {agent_url}')

    # Send initial task list
    try:
        tasks, total = task_tracker.get_tasks(agent_url=agent_url, limit=50)
        tasks_data = [task.model_dump(exclude_none=True) for task in tasks]

        await sio.emit(
            'task_subscription_response',
            {'status': 'success', 'tasks': tasks_data, 'total': total},
            to=sid,
        )
    except Exception as e:
        logger.error(
            f'Failed to send initial tasks to {sid}: {e}', exc_info=True
        )
        await sio.emit(
            'task_subscription_response',
            {'status': 'error', 'message': str(e)},
            to=sid,
        )


@sio.on('unsubscribe_from_tasks')
async def handle_unsubscribe_from_tasks(sid: str, data: dict[str, Any]) -> None:
    """Handle the 'unsubscribe_from_tasks' socket.io event."""
    agent_url = data.get('agent_url')

    if not agent_url:
        return

    room_name = f'tasks_{agent_url}'
    await sio.leave_room(sid, room_name)

    logger.info(f'Client {sid} unsubscribed from tasks for agent: {agent_url}')


@sio.on('get_task_details')
async def handle_get_task_details(sid: str, data: dict[str, Any]) -> None:
    """Handle the 'get_task_details' socket.io event."""
    task_id = data.get('task_id')

    if not task_id:
        await sio.emit(
            'task_details_response',
            {'status': 'error', 'message': 'Task ID is required'},
            to=sid,
        )
        return

    try:
        task = task_tracker.get_task(task_id)

        if task is None:
            await sio.emit(
                'task_details_response',
                {'status': 'error', 'message': f'Task not found: {task_id}'},
                to=sid,
            )
            return

        await sio.emit(
            'task_details_response',
            {'status': 'success', 'task': task.model_dump(exclude_none=True)},
            to=sid,
        )
    except Exception as e:
        logger.error(f'Failed to get task details for {task_id}: {e}', exc_info=True)
        await sio.emit(
            'task_details_response',
            {'status': 'error', 'message': str(e)},
            to=sid,
        )


@sio.on('cancel_task')
async def handle_cancel_task(sid: str, data: dict[str, Any]) -> None:
    """Handle the 'cancel_task' socket.io event."""
    task_id = data.get('task_id')

    if not task_id:
        await sio.emit(
            'cancel_task_response',
            {'status': 'error', 'message': 'Task ID is required'},
            to=sid,
        )
        return

    if sid not in clients:
        await sio.emit(
            'cancel_task_response',
            {'status': 'error', 'message': 'Client not initialized'},
            to=sid,
        )
        return

    try:
        _, a2a_client, _ = clients[sid]

        # Call the agent's cancel task endpoint
        cancel_response = await a2a_client.cancel_task(TaskIdParams(id=task_id))

        if cancel_response and cancel_response.root.result:
            task = cancel_response.root.result
            # Update our tracker
            agent_url = data.get('agent_url', 'unknown')
            task_tracker.add_task(task, agent_url)

            # Broadcast update to subscribers
            room_name = f'tasks_{agent_url}'
            await sio.emit(
                'task_update',
                {'task': task.model_dump(exclude_none=True)},
                room=room_name,
            )

            await sio.emit(
                'cancel_task_response',
                {'status': 'success', 'task': task.model_dump(exclude_none=True)},
                to=sid,
            )
        else:
            await sio.emit(
                'cancel_task_response',
                {'status': 'error', 'message': 'Failed to cancel task'},
                to=sid,
            )

    except Exception as e:
        logger.error(f'Failed to cancel task {task_id}: {e}', exc_info=True)
        await sio.emit(
            'cancel_task_response',
            {'status': 'error', 'message': str(e)},
            to=sid,
        )


# ==============================================================================
# Main Execution
# ==============================================================================


if __name__ == '__main__':
    import uvicorn

    # NOTE: The 'reload=True' flag is for development purposes only.
    # In a production environment, use a proper process manager like Gunicorn.
    uvicorn.run('app:app', host='127.0.0.1', port=5001, reload=True)
