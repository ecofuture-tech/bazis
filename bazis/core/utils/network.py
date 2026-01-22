import asyncio
import socket
import threading

import uvloop
from aiohttp import web


def check_port(port, host='localhost') -> bool:
    """
    Check if a given port on the specified host is free.

    Tags: RAG, EXPORT
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((host, port))
    is_free = result != 0
    sock.close()
    return is_free


def healthcheck_server(host, port, **endpoints):
    """
    Start a simple healthcheck server with custom endpoints in a separate thread.

    Tags: RAG, EXPORT
    """

    async def healthcheck(r):
        return web.Response()

    app = web.Application()
    app.router.add_get('/healthcheck', healthcheck)

    for ep_name, ep_func in endpoints.items():
        app.router.add_get(f'/{ep_name}', ep_func)

    async def thead_worker():
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

    if not check_port(port, host=host):
        raise Exception(f'Handler cannot run. Address [{host}, {port}] is busy.')

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.new_event_loop()
    loop.create_task(thead_worker())

    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
