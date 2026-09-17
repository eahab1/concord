"""Elapsed-time heartbeat for opaque, blocking solver calls."""
from contextlib import contextmanager
from threading import Event, Thread
from time import monotonic


def duration(seconds):
    seconds = int(seconds)
    return f'{seconds // 60}m {seconds % 60:02d}s'


@contextmanager
def heartbeat(label, *, interval=10., emit=None):
    """Report liveness, not an estimated fraction of numerical work done."""
    if interval <= 0:
        raise ValueError('Heartbeat interval must be positive')
    if emit is None:
        emit = lambda message: print(message, flush=True)
    stopped = Event()
    start = monotonic()
    def report():
        while not stopped.wait(interval):
            emit(f'  {label} · running · elapsed {duration(monotonic()-start)}')
    worker = Thread(target=report, name='concord-solver-progress', daemon=True)
    worker.start()
    outcome = 'complete'
    try:
        yield
    except BaseException:
        outcome = 'interrupted/failed'
        raise
    finally:
        stopped.set()
        worker.join()
        emit(f'  {label} · {outcome} · elapsed {duration(monotonic()-start)}')
