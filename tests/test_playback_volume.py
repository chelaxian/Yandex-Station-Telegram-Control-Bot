import io
import struct
import wave

import pytest

from stationbot.audio import apply_volume
from stationbot.errors import InvalidInput


@pytest.mark.parametrize(('level', 'expected'), [(0, (0, 0)), (50, (5000, -5000)), (100, (10000, -10000))])
def test_pcm_volume(level, expected):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        wav.writeframes(struct.pack('<hh', 10000, -10000))
    with wave.open(io.BytesIO(apply_volume(stream.getvalue(), level)), 'rb') as wav:
        assert struct.unpack('<hh', wav.readframes(2)) == expected


def test_refuses_invalid_volume_or_format():
    with pytest.raises(InvalidInput):
        apply_volume(b'bad', 10)
    with pytest.raises(InvalidInput):
        apply_volume(b'bad', 101)
