import asyncio
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional


def generate_id() -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def round_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    precision = Decimal(str(step))
    return float((Decimal(str(value)) / precision).to_integral_value() * precision)


async def retry_async(
    coro_factory,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exc_check=None,
):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if exc_check and not isinstance(exc, exc_check):
                raise
            if attempt == attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]
