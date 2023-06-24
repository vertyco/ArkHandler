import asyncio
import logging
import os
import sys

from common.scheduler import scheduler
from common.tasks import ArkHandler
from common.utils import set_resolution

log = logging.getLogger("ArkHandler.main")


class Manager:
    """Compile with 'pyinstaller.exe --clean main.spec'"""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop: asyncio.AbstractEventLoop = loop
        self.handler = ArkHandler()

    async def start(self) -> None:
        scheduler.start()
        scheduler.remove_all_jobs()
        logging.getLogger("apscheduler").setLevel(logging.WARNING)
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
    Manager.run()
