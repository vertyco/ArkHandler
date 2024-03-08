import asyncio
import logging
import os
import sys

from common.config import Conf
from common.const import CONF_PATH, DEFAULT_CONF_TEXT
from common.helpers import set_resolution
from common.scheduler import scheduler
from common.tasks import ArkHandler

log = logging.getLogger("arkhandler.main")


class Manager:
    """Compile with 'pyinstaller.exe --clean main.spec'"""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop: asyncio.AbstractEventLoop = loop
        self.handler = ArkHandler()

    async def start(self) -> None:
        scheduler.start()
        scheduler.remove_all_jobs()
        await self.handler.initialize()

    async def stop(self) -> None:
        scheduler.remove_all_jobs()
        scheduler.shutdown(wait=False)

    @classmethod
    def run(cls) -> None:
        log.info(f"Starting ArkHandler with PID {os.getpid()}")

        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        arkhandler = cls(loop)

        try:
            loop.create_task(arkhandler.start())
            loop.run_forever()
        except KeyboardInterrupt:
            print("CTRL+C received, shutting down...")
        except Exception as e:
            log.critical("Fatal error!", exc_info=e)
        finally:
            log.info("Shutting down...")
            set_resolution(default=True)
            loop.run_until_complete(arkhandler.stop())
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(asyncio.sleep(1))
            asyncio.set_event_loop(None)
            loop.stop()
            loop.close()

            log.info("Goodbye.")
            sys.exit()


if __name__ == "__main__":
    if not CONF_PATH.exists():
        log.error("Config file not found, created a new one.")
        CONF_PATH.write_text(DEFAULT_CONF_TEXT)
        input("Please configure and restart.. ")
        exit()

    try:
        Conf.load(str(CONF_PATH))
    except Exception as e:
        log.error("Failed to load config file", exc_info=e)
        input("Failed to load config file, check the logs for details. Press Enter to exit.")
        exit()

    Manager.run()
