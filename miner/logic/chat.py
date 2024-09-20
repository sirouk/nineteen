import json
import httpx
from fiber.logging_utils import get_logger

from core.models import payload_models
from core import tasks_config as tcfg
from core.tasks import Task
from miner.config import WorkerConfig

logger = get_logger(__name__)


async def chat_stream(
    httpx_client: httpx.AsyncClient, decrypted_payload: payload_models.ChatPayload, worker_config: WorkerConfig
):
    task_config = tcfg.get_enabled_task_config(decrypted_payload.model)
    if task_config is None:
        raise ValueError(f"Task config not found for model: {decrypted_payload.model}")
    assert task_config.orchestrator_server_config.load_model_config is not None

    model_name = task_config.orchestrator_server_config.load_model_config["model"]
    

    if task_config.task == Task.chat_llama_3_1_8b:
        address = worker_config.LLAMA_3_1_8B_TEXT_WORKER_URL
    elif task_config.task == Task.chat_llama_3_1_70b:
        address = worker_config.LLAMA_3_1_70B_TEXT_WORKER_URL
    else:
        raise ValueError(f"Invalid model: {decrypted_payload.model}")
    
    decrypted_payload.model = model_name

    assert address is not None, f"Address for model: {decrypted_payload.model} is not set in env vars!"

    if True:
        # NOTE: review timeout?
        async with httpx_client.stream("POST", address, json=decrypted_payload.model_dump(), timeout=5) as resp:
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                await resp.aread()
                logger.error(f"HTTP Error {e.response.status_code}: {e.response.text}")
                raise
            async for chunk in resp.aiter_lines():
                try:
                    received_event_chunks = chunk.split("\n\n")
                    for event in received_event_chunks:
                        if event == "":
                            continue
                        prefix, _, data = event.partition(":")
                        if data.strip() == "[DONE]":
                            break
                        yield f"data: {data}\n\n"
                except Exception as e:
                    logger.error(f"Error in streaming text from the server: {e}. Original chunk: {chunk}")
    else:
        for i in range(100):
            data = {"choices": [{"delta": {"content": f"{i}"}}]}
            yield f"data: {json.dumps(data)}\n\n"
        yield "data: [DONE]\n\n"