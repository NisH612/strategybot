#!/usr/bin/env python3
import asyncio
import sys

from src.bot import TradingBot
from src.config import validate_or_exit
from src.utils.logger import logger


async def main() -> None:
    settings = validate_or_exit()
    bot = TradingBot(settings)
    try:
        await bot.start()
        while bot._running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except asyncio.CancelledError:
        logger.info("Bot cancelled")
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        raise
    finally:
        await bot.stop()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
