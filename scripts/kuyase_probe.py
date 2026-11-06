"""Probe an isolated KUYASE snapshot through a loopback-only ADB forward."""
import asyncio
import io
import math
import struct
import sys
import uuid
import wave

from stationbot.config import StationConfig
from stationbot.errors import Unavailable
from stationbot.luna import Luna


async def main():
    if len(sys.argv) != 3 or sys.argv[2] != '--snapshot-vm':
        raise SystemExit('Usage: python scripts/kuyase_probe.py MODEL --snapshot-vm')
    model = sys.argv[1]
    failures = []
    client = Luna(StationConfig(id='virtual', label='Virtual Station',
                                url='http://127.0.0.1:18210/api', expected_model=model,
                                allow_owner_tools=True))
    try:
        device = await client.device()
        print('device', device.model, 'ring', device.ring_count, 'logo', device.logo_count,
              'features', ','.join(sorted(device.features)), flush=True)
        original_volume = (await client.volume())['percent']
        print('volume', original_volume, flush=True)
        try:
            print('volume_set', await client.volume(30), flush=True)
        finally:
            print('volume_restore', await client.volume(original_volume), flush=True)
        try:
            print('clock', (await client.clock())['available'], flush=True)
        except Unavailable:
            print('clock unavailable', flush=True)
        else:
            try:
                print('clock_set', await client.clock('12:34'), flush=True)
                print('clock_release', await client.clock('off'), flush=True)
            except Exception as exc:
                print('clock_error', type(exc).__name__, str(exc), flush=True)
                failures.append('clock')
        print('sensors', len(await client.sensors()), flush=True)
        for name, operation in [('microphones', client.microphone_devices),
                                ('plugins', client.plugins), ('media', client.media)]:
            try:
                result = await operation()
                print(name, 'available', len(result) if isinstance(result, list) else type(result).__name__, flush=True)
            except Unavailable as exc:
                print(name, 'unavailable', str(exc), flush=True)
        if 'microphone.capture' in device.features:
            try:
                recording = await client.record(1)
                with wave.open(io.BytesIO(recording), 'rb') as wav:
                    duration = wav.getnframes() / wav.getframerate()
                print('microphone_record_wav_bytes', len(recording), 'duration_seconds', round(duration, 3), flush=True)
                if duration < 0.8:
                    print('microphone_record_short: requested 1 second', flush=True)
                    failures.append('microphone_record_short')
            except Exception as exc:
                print('microphone_record_error', type(exc).__name__, str(exc), flush=True)
                failures.append('microphone_record')
        if 'owner.tools.v1' in device.features:
            try:
                result = await client.owner('GET', 'system')
                print('owner_system', type(result).__name__, flush=True)
                result = await client.shell('id -u')
                print('owner_shell_exit', result.get('exit_code'), flush=True)
                if result.get('exit_code') != 0:
                    failures.append('owner_shell')
            except Exception as exc:
                print('owner_error', type(exc).__name__, str(exc), flush=True)
                failures.append('owner')
        if 'led.ring.rgb' in device.features and device.ring_count:
            print('led', await client.led('ring', '#103020'), flush=True)
            try:
                print('led_release', await client.led('ring', None), flush=True)
            except Unavailable as exc:
                print('led_release_error', str(exc), flush=True)
                failures.append('led_release')
                response = await client.http.post('led/off/ring')
                print('led_release_diagnostic', response.status_code, response.text[:500], flush=True)
        else:
            print('ring unavailable', flush=True)
        if 'led.logo' in device.features and device.logo_count:
            try:
                print('logo_set', await client.led('logo', '#103020'), flush=True)
                print('logo_release', await client.led('logo', None), flush=True)
            except Exception as exc:
                print('logo_error', type(exc).__name__, str(exc), flush=True)
                failures.append('logo')
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            wav.writeframes(b''.join(struct.pack('<h', int(300 * math.sin(i / 20))) for i in range(4800)))
        job = await client.play(output.getvalue(), f'kuyase-{uuid.uuid4()}')
        print('audio_start', job['state'], flush=True)
        for _ in range(30):
            job = await client.audio_status(job['id'])
            if job['state'] not in {'queued', 'playing'}:
                break
            await asyncio.sleep(.25)
        print('audio_final', job['state'], 'cleanup', job['cleanup'], flush=True)
        if job['state'] != 'succeeded' or job['cleanup'] != 'complete':
            raise RuntimeError('Audio job did not complete with cleanup')
        if failures:
            raise RuntimeError('Failed checks: ' + ', '.join(failures))
    finally:
        await client.close()


asyncio.run(main())
