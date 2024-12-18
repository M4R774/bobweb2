import asyncio
import subprocess

from concurrent.futures import ThreadPoolExecutor


class VideoConvertService:
    """
    Service for queueing ffmpeg commands and running them synchronously in sequence. This was created as having multiple
    ffmpeg subprocesses called from multiple threads had problems. Now each call is queued and executed in sequence.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
            cls._instance._queue = asyncio.Queue()
            cls._instance._executor = ThreadPoolExecutor(max_workers=1)
            cls._instance._loop = asyncio.get_event_loop()
            cls._instance._loop.create_task(cls._instance._worker())
        return cls._instance

    async def _worker(self):
        while True:
            func, video_bytes, future = await self._queue.get()
            try:
                result = await self._loop.run_in_executor(self._instance._executor, func, video_bytes)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
            finally:
                self._queue.task_done()

    async def convert_image_from_video(self, video_bytes: bytes) -> bytes:
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        await self._queue.put((_convert_image_from_video_synchronous, video_bytes, future))
        return await future


def _convert_image_from_video_synchronous(video_bytes: bytes) -> bytes:
    """
    Synchronous implementation of converting single video bytes to single image bytes. Calls ffmpeg as subprocess. This
    way no extra wrapped library is required.
    :param video_bytes:
    :return:
    """
    command = [
        'ffmpeg',
        '-hide_banner',  # No banner on every call
        '-loglevel', 'quiet',  # Quiet logging level as decoding errors are frequent and have no harmful effect
        '-i', 'pipe:0',  # Use stdin for input
        '-frames:v', '1',  # Get only one frame
        '-f', 'image2pipe',  # Output to a pipe
        '-vcodec', 'mjpeg',  # Convert video stream to motion jpeg
        'pipe:1'
    ]

    # Fmpeg can now take input directly from the memory buffer and output to a pipe
    process = subprocess.run(
        command,
        input=video_bytes,  # Use the buffer content as input
        stdout=subprocess.PIPE
    )
    # Check return code, raise error if it's not 0
    process.check_returncode()
    # Return bytes from the standard output
    return process.stdout
