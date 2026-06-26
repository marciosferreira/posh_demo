"""
Canal SSE para comandos de UI enviados pelo agente ao browser.

O agente chama push_ui_event() de dentro de uma thread; o endpoint /ui/stream
em main.py registra uma asyncio.Queue por sessão e faz o despacho para o browser.
"""

import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

_ui_queues: dict[str, tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = {}
_lock = threading.Lock()


def register_ui_queue(session_id: str, q: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
    with _lock:
        _ui_queues[session_id] = (q, loop)
    logger.info("[ui_events] fila registrada para session_id=%s (total=%d)", session_id, len(_ui_queues))


def unregister_ui_queue(session_id: str) -> None:
    with _lock:
        _ui_queues.pop(session_id, None)
    logger.info("[ui_events] fila removida para session_id=%s", session_id)


def push_ui_event(session_id: str, event: dict) -> bool:
    """Chamado de threads do agente para enviar um evento ao browser via SSE.

    Tenta primeiro a sessão exata. Se não encontrar (session_id mismatch entre
    o ContextVar do agente e a sessão SSE), faz broadcast para todas as sessões
    ativas — comportamento seguro para dashboard single-user.
    """
    with _lock:
        entry = _ui_queues.get(session_id)
        all_entries = list(_ui_queues.items())

    if entry is not None:
        q, loop = entry
        asyncio.run_coroutine_threadsafe(q.put(event), loop)
        logger.info("[ui_events] evento enviado para session_id=%s: %s", session_id, event)
        return True

    if all_entries:
        logger.warning(
            "[ui_events] session_id=%s não encontrado, broadcast para %d sessão(ões) ativa(s): %s",
            session_id, len(all_entries), [s for s, _ in all_entries],
        )
        for _, (q, loop) in all_entries:
            asyncio.run_coroutine_threadsafe(q.put(event), loop)
        return True

    logger.warning("[ui_events] push ignorado — nenhuma sessão SSE ativa (procurado: %s)", session_id)
    return False
