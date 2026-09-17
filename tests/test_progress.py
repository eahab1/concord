from threading import Event, enumerate as threads
import pytest
from concord.progress import heartbeat, duration


def test_heartbeat_while_blocking_and_stops():
    messages=[]; reported=Event()
    def emit(message):
        messages.append(message)
        if 'running' in message: reported.set()
    with heartbeat('500 Hz (0/7 frequencies finished)', interval=.01, emit=emit):
        assert reported.wait(2)
    assert 'running' in messages[0]
    assert 'complete' in messages[-1]
    assert not any(t.name=='concord-solver-progress' for t in threads())


@pytest.mark.parametrize('error',[RuntimeError('solver failed'),KeyboardInterrupt()])
def test_heartbeat_cleans_up_on_failure(error):
    messages=[]
    with pytest.raises(type(error)):
        with heartbeat('500 Hz',emit=messages.append):
            raise error
    assert 'interrupted/failed' in messages[-1]
    assert not any(t.name=='concord-solver-progress' for t in threads())


def test_duration():
    assert duration(125.8)=='2m 05s'
