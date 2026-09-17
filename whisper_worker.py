"""Isolated faster-whisper inference; also executable without importing ComfyUI.

Only the child loads CTranslate2 weights. A stuck native CUDA call can therefore
be terminated without leaving a background thread using the music GPU.
"""
from pathlib import Path
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

LOGGER = logging.getLogger(__name__)
POLL_SECONDS = 0.2
GPU_IDLE_SECONDS = 180
CPU_IDLE_SECONDS = 600


class WhisperCancelled(Exception):
    """Cancellation must never trigger the CPU fallback."""


def check_cancelled():
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
    except ImportError:
        return
    # ComfyUI's interrupt exception is an Exception on some host versions.
    try:
        throw_exception_if_processing_interrupted()
    except Exception as exc:
        raise WhisperCancelled() from exc


def wait_for_worker(proc, progress_path, *, idle_seconds, total_seconds):
    started = last_progress = last_log = time.monotonic()
    previous = None
    while proc.poll() is None:
        check_cancelled()
        now = time.monotonic()
        try:
            progress = progress_path.read_text(encoding='utf-8')
        except OSError:
            progress = ''
        if progress != previous:
            previous, last_progress = progress, now
        if now - last_progress > idle_seconds or now - started > total_seconds:
            raise TimeoutError('Whisper worker stopped making progress or exceeded its time limit. '
                               'Try device=cpu or a reviewed transcript; no partial lyrics were accepted.')
        if now - last_log >= 15:
            LOGGER.info('Cover Whisper: %s (elapsed %.0f s)', progress or 'starting', now - started)
            last_log = now
        time.sleep(POLL_SECONDS)


class IsolatedWhisperModel:
    def __init__(self, path, device, compute_type):
        self.path, self.device, self.compute_type = str(path), device, compute_type

    def transcribe(self, samples, **options):
        import numpy as np

        with tempfile.TemporaryDirectory(prefix='music-cover-whisper-') as directory:
            root = Path(directory)
            np.save(root / 'audio.npy', np.asarray(samples, dtype=np.float32), allow_pickle=False)
            request = dict(model=self.path, device=self.device, compute_type=self.compute_type,
                           options=options)
            (root / 'request.json').write_text(json.dumps(request), encoding='utf-8')
            flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            duration = len(samples) / 16000
            idle = GPU_IDLE_SECONDS if self.device == 'cuda' else CPU_IDLE_SECONDS
            LOGGER.info('Cover Whisper: starting isolated %s/%s transcription of %.1f s audio',
                        self.device, self.compute_type, duration)
            with (root / 'stderr.log').open('wb') as errors:
                proc = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), str(root)],
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=errors, **flags)
                try:
                    wait_for_worker(proc, root / 'progress.txt', idle_seconds=idle,
                                    total_seconds=max(1200, duration * 20))
                finally:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait()
            result_file = root / 'result.json'
            if not result_file.exists():
                detail = (root / 'stderr.log').read_text(encoding='utf-8', errors='replace')[-1500:]
                raise RuntimeError(f'Whisper worker exited ({proc.returncode}): {detail}')
            result = json.loads(result_file.read_text(encoding='utf-8'))
            if 'error' in result:
                kind = {'ValueError': ValueError, 'TypeError': TypeError}.get(result['type'], RuntimeError)
                raise kind(result['error'])
            segments = [SimpleNamespace(**{**segment, 'words': [SimpleNamespace(**word)
                        for word in segment['words']]}) for segment in result['segments']]
            return iter(segments), SimpleNamespace(**result['info'])


def _windows_dll_directories():
    """Make installed Torch/NVIDIA DLLs visible to CTranslate2 in the child."""
    if os.name != 'nt':
        return []
    import importlib.util
    paths = []
    spec = importlib.util.find_spec('torch')
    if spec and spec.origin:
        paths.append(Path(spec.origin).parent / 'lib')
    for entry in sys.path:
        nvidia = Path(entry) / 'nvidia'
        if nvidia.is_dir():
            paths.extend(nvidia.glob('*/bin'))
    paths = [path for path in paths if path.is_dir()]
    os.environ['PATH'] = os.pathsep.join([*(str(path) for path in paths), os.environ.get('PATH', '')])
    return [os.add_dll_directory(str(path)) for path in paths]


def main(root):
    root = Path(root)
    result = {}
    try:
        handles = _windows_dll_directories()  # Keep directory handles alive through inference.
        import numpy as np
        from faster_whisper import WhisperModel
        request = json.loads((root / 'request.json').read_text(encoding='utf-8'))
        progress = root / 'progress.txt'
        progress.write_text('loading checkpoint', encoding='utf-8')
        model = WhisperModel(request['model'], device=request['device'],
                             compute_type=request['compute_type'], local_files_only=True)
        samples = np.load(root / 'audio.npy', allow_pickle=False)
        progress.write_text('decoding first audio window', encoding='utf-8')
        iterator, info = model.transcribe(samples, **request['options'])
        result = {'info': {name: getattr(info, name, None) for name in
                  ('language', 'language_probability', 'duration', 'duration_after_vad')}, 'segments': []}
        for segment in iterator:
            result['segments'].append(dict(start=segment.start, end=segment.end, text=segment.text,
                words=[dict(word=word.word, start=word.start, end=word.end)
                       for word in (segment.words or [])]))
            progress.write_text(f'decoded through {segment.end:.1f} / {len(samples)/16000:.1f} s',
                                encoding='utf-8')
    except Exception as exc:
        result = {'error': str(exc), 'type': type(exc).__name__}
    (root / 'result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1])
