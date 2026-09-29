"""Head Studio: local-only photo-to-mesh application."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
import zipfile

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()
ROOT = Path(__file__).resolve().parent
JOBS = ROOT / 'projects'
STATIC = ROOT / 'static'
COLMAP_PYTHON = ROOT / '.colmap-env/bin/python'
MVS = ROOT / 'tools/openmvs'
FORMATS = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.tif', '.tiff', '.webp'}
PRESETS = {'draft': (1600, 1000, 3), 'balanced': (2400, 1600, 4)}
STEPS = ['Prepare photos', 'Find image features', 'Match photos', 'Align cameras',
         'Correct lens distortion', 'Import geometry', 'Build dense surface',
         'Create mesh', 'Apply photo textures', 'Package model']
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.RLock()
ACTIVE = None
CANCEL = threading.Event()
PROCESS = None


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


def project_path(identifier):
    if not re.fullmatch(r'[a-f0-9]{16}', identifier):
        raise ValueError('Invalid project ID')
    path = JOBS / identifier
    if not path.is_dir():
        raise ValueError('Project not found')
    return path


def read_state(root):
    return json.loads((root / 'status.json').read_text())


def update(root, **values):
    with LOCK:
        state = read_state(root)
        state.update(values)
        state['updated'] = time.time()
        atomic_json(root / 'status.json', state)
    return state


def check_tools():
    checks = {'COLMAP': COLMAP_PYTHON.is_file()}
    for name in ('InterfaceCOLMAP', 'DensifyPointCloud', 'ReconstructMesh', 'TextureMesh'):
        checks[name] = os.access(MVS / name, os.X_OK)
    return checks


def create_project(name, preset):
    if preset not in PRESETS:
        raise ValueError('Choose Draft or Balanced quality')
    identifier = secrets.token_hex(8)
    root = JOBS / identifier
    (root / 'originals').mkdir(parents=True)
    image_size, dense_size, threads = PRESETS[preset]
    atomic_json(root / 'settings.json', {'preset': preset, 'image_size': image_size,
                'dense_size': dense_size, 'threads': threads})
    state = {'id': identifier, 'name': str(name).strip()[:100] or 'Untitled head',
             'state': 'uploading', 'step': 0, 'message': 'Add your photos',
             'count': 0, 'created': time.time(), 'preset': preset, 'warnings': []}
    atomic_json(root / 'status.json', state)
    return state


def check_cancel():
    if CANCEL.is_set():
        raise InterruptedError('Reconstruction cancelled. Imported photos remain in the project.')


def run_command(root, args):
    global PROCESS
    check_cancel()
    with (root / 'process.log').open('a', buffering=1) as log:
        log.write('\n$ ' + ' '.join(map(str, args)) + '\n')
        env = dict(os.environ, OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1',
                   VECLIB_MAXIMUM_THREADS='4', PYTHONUNBUFFERED='1')
        with LOCK:
            check_cancel()
            PROCESS = subprocess.Popen(list(map(str, args)), cwd=root, env=env,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            proc = PROCESS
        result = proc.wait()
        with LOCK:
            PROCESS = None
        check_cancel()
        if result:
            with (root / 'process.log').open('rb') as stream:
                stream.seek(max(0, (root / 'process.log').stat().st_size - 4000))
                tail = stream.read().decode(errors='replace')
            errors = re.findall(r'^(?:RuntimeError|ValueError): (.+)$', tail, re.MULTILINE)
            if errors:
                raise RuntimeError(errors[-1])
            raise RuntimeError(f'{Path(str(args[0])).name} stopped (exit {result}). See the processing log for details.')


def stop_process():
    CANCEL.set()
    with LOCK:
        proc = PROCESS
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            def force_stop():
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            threading.Thread(target=force_stop, daemon=True).start()


def prepare(root, settings):
    images = root / 'images'
    images.mkdir(exist_ok=True)
    originals = sorted((root / 'originals').iterdir())
    manifest = []
    for index, source in enumerate(originals):
        check_cancel()
        try:
            with Image.open(source) as raw:
                # Keep lens hints for calibration, but omit GPS and other metadata.
                exif = Image.Exif()
                for tag in (271, 272, 37386, 41989):
                    if tag in raw.getexif():
                        exif[tag] = raw.getexif()[tag]
                photo = ImageOps.exif_transpose(raw).convert('RGB')
                photo.thumbnail((settings['image_size'], settings['image_size']), Image.Resampling.LANCZOS)
                if min(photo.size) < 200:
                    raise ValueError('photo is too small (minimum short edge: 200 pixels)')
                target = images / f'{index:04d}.jpg'
                photo.save(target, quality=95, exif=exif)
                manifest.append({'source': source.name, 'prepared': target.name, 'size': photo.size})
        except Exception as error:
            raise ValueError(f'Cannot import {source.name}: {error}') from error
        update(root, message=f'Preparing photo {index + 1} of {len(originals)}')
    atomic_json(root / 'photos.json', manifest)


def normalize_materials(result):
    # OpenMVS 2.4 writes Tr=1 for opaque surfaces; standard OBJ readers interpret
    # that as fully transparent. These reconstructed surfaces are all opaque.
    for path in result.glob('*.mtl'):
        path.write_text(re.sub(r'^Tr\s+[^\r\n]+', 'd 1.0', path.read_text(), flags=re.MULTILINE))


def pipeline(root):
    global ACTIVE
    try:
        settings = json.loads((root / 'settings.json').read_text())
        threads = settings['threads']
        dense = root / 'dense'
        result = root / 'result'
        result.mkdir(exist_ok=True)
        for index, label in enumerate(STEPS):
            check_cancel()
            update(root, state='running', step=index, message=label)
            if index == 0:
                prepare(root, settings)
            elif index in (1, 2, 3, 4):
                stage = ('features', 'matching', 'mapping', 'undistort')[index - 1]
                run_command(root, [COLMAP_PYTHON, ROOT / 'colmap_worker.py', stage, root])
                if stage == 'mapping':
                    summary = json.loads((root / 'alignment.json').read_text())
                    warnings = []
                    if summary['registered'] < summary['total']:
                        warnings.append(f"{summary['registered']}/{summary['total']} photos aligned; inspect for missing coverage.")
                    update(root, alignment=summary, warnings=warnings)
            elif index == 5:
                run_command(root, [MVS / 'InterfaceCOLMAP', '-i', dense, '-o', dense / 'scene.mvs',
                                  '--image-folder', dense / 'images', '--max-threads', threads])
            elif index == 6:
                run_command(root, [MVS / 'DensifyPointCloud', '-i', dense / 'scene.mvs',
                                  '-o', dense / 'scene_dense.mvs', '-w', dense,
                                  '--resolution-level', 0, '--max-resolution', settings['dense_size'],
                                  '--number-views', 4, '--max-threads', threads, '--tower-mode', 0,
                                  '--remove-dmaps', 1])
            elif index == 7:
                run_command(root, [MVS / 'ReconstructMesh', '-i', dense / 'scene_dense.mvs',
                                  '-o', dense / 'scene_mesh.ply', '-w', dense,
                                  '--max-threads', threads, '--target-face-num', 300000])
                if not (dense / 'scene_mesh.ply').is_file():
                    raise RuntimeError('No mesh surface could be reconstructed. Inspect alignment and capture more overlapping views.')
            elif index == 8:
                run_command(root, [MVS / 'TextureMesh', '-i', dense / 'scene_dense.mvs',
                                  '--mesh-file', dense / 'scene_mesh.ply',
                                  '-o', result / 'head.obj', '-w', dense, '--export-type', 'obj',
                                  '--max-threads', threads, '--max-texture-size', 4096,
                                  '--global-seam-leveling', 0, '--local-seam-leveling', 0,
                                  '--sharpness-weight', 0])
                if not (result / 'head.obj').is_file():
                    raise RuntimeError('Texturing did not produce head.obj. Check the processing log.')
                normalize_materials(result)
            elif index == 9:
                (result / 'README.txt').write_text(
                    'Open head.obj in Blender or MeshLab. Keep its MTL and texture images beside it.\n'
                    'Scale and orientation are arbitrary. Inspect all sides for holes.\n'
                    'Background/shoulders may need cropping; this is not automatically a watertight printable mesh.\n')
                with zipfile.ZipFile(root / 'head-model.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
                    for file in sorted(result.iterdir()):
                        if file.is_file() and file.suffix.lower() in {'.obj', '.mtl', '.png', '.jpg', '.jpeg', '.txt'}:
                            archive.write(file, file.name)
        update(root, state='complete', step=len(STEPS), message='Your textured model is ready',
               output=str(result), finished=time.time())
    except InterruptedError as error:
        update(root, state='cancelled', message=str(error))
    except Exception as error:
        with (root / 'process.log').open('a') as log:
            log.write('\nERROR: ' + str(error) + '\n')
        update(root, state='failed', message=str(error))
    finally:
        with LOCK:
            ACTIVE = None


def start_project(root):
    global ACTIVE
    with LOCK:
        if ACTIVE:
            raise ValueError('Another project is processing. Wait or cancel it first.')
        state = read_state(root)
        if state['state'] != 'uploading':
            raise ValueError('This project has already started. Create a new project to try again.')
        count = len(list((root / 'originals').iterdir()))
        if not 12 <= count <= 200:
            raise ValueError('Import 12–200 photos. For a full head, aim for 80–150.')
        missing = [name for name, ok in check_tools().items() if not ok]
        if missing:
            raise ValueError('Missing tools: ' + ', '.join(missing))
        if shutil.disk_usage(root).free < 10 * 1024**3:
            raise ValueError('At least 10 GB of free disk space is needed.')
        ACTIVE = root.name
        CANCEL.clear()
        update(root, state='running', count=count, message='Starting reconstruction')
        threading.Thread(target=pipeline, args=(root,), daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, value, status=200):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def local_request(self):
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in allowed:
            raise ValueError('Only local requests are accepted')
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://' + host for host in allowed}:
            raise ValueError('Only this app may submit requests')

    def serve_file(self, path, download=False):
        if not path.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(path)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(path.stat().st_size))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        if download:
            self.send_header('Content-Disposition', f'attachment; filename="{path.name}"')
        self.end_headers()
        with path.open('rb') as source:
            shutil.copyfileobj(source, self.wfile)

    def do_GET(self):
        try:
            self.local_request()
            path = unquote(urlparse(self.path).path)
            if path == '/api/info':
                self.reply({'token': TOKEN, 'tools': check_tools(), 'steps': STEPS,
                            'free_gb': round(shutil.disk_usage(ROOT).free / 1024**3, 1)})
            elif path == '/api/projects':
                states = [read_state(folder) for folder in JOBS.iterdir() if (folder / 'status.json').exists()]
                self.reply(sorted(states, key=lambda s: s['created'], reverse=True))
            elif path.startswith('/api/projects/'):
                parts = path.strip('/').split('/')
                root = project_path(parts[2])
                if len(parts) == 4 and parts[3] == 'log':
                    log = root / 'process.log'
                    if log.exists():
                        with log.open('rb') as stream:
                            stream.seek(max(0, log.stat().st_size - 18000))
                            content = stream.read().decode(errors='replace')
                    else:
                        content = 'Waiting to start…'
                    self.reply({'text': content})
                elif len(parts) == 4 and parts[3] == 'download':
                    self.serve_file(root / 'head-model.zip', True)
                elif len(parts) >= 5 and parts[3] == 'result':
                    result_root = (root / 'result').resolve()
                    file = (result_root / '/'.join(parts[4:])).resolve()
                    if not file.is_relative_to(result_root):
                        raise ValueError('Invalid file')
                    self.serve_file(file)
                elif len(parts) == 3:
                    self.reply(read_state(root))
                else:
                    self.send_error(404)
            else:
                target = (STATIC / ('index.html' if path == '/' else path.lstrip('/'))).resolve()
                if not target.is_relative_to(STATIC.resolve()):
                    raise ValueError('Invalid path')
                self.serve_file(target)
        except (ValueError, KeyError) as error:
            self.reply({'error': str(error)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        try:
            self.local_request()
            if self.headers.get('X-Head-Studio-Token') != TOKEN:
                self.reply({'error': 'Reload the app to reconnect.'}, 403)
                return
            path = urlparse(self.path).path
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 80 * 1024**2:
                raise ValueError('Request is empty or larger than 80 MB')
            if path.endswith('/photos'):
                root = project_path(path.strip('/').split('/')[2])
                with LOCK:
                    state = read_state(root)
                    if state['state'] != 'uploading':
                        raise ValueError('This project is no longer accepting photos')
                    count = len(list((root / 'originals').iterdir()))
                    if count >= 200:
                        raise ValueError('Maximum 200 photos per project')
                    filename = Path(unquote(self.headers.get('X-Filename', 'photo.jpg'))).name
                    suffix = Path(filename).suffix.lower()
                    if suffix not in FORMATS:
                        raise ValueError('Unsupported photo format')
                    safe = re.sub(r'[^A-Za-z0-9._-]', '_', filename)[:140]
                    destination = root / 'originals' / f'{count:04d}_{safe}'
                    remaining = length
                    try:
                        with destination.open('wb') as stream:
                            while remaining:
                                chunk = self.rfile.read(min(remaining, 1024**2))
                                if not chunk:
                                    raise ValueError('Photo upload interrupted')
                                stream.write(chunk)
                                remaining -= len(chunk)
                        update(root, count=count + 1)
                    except Exception:
                        destination.unlink(missing_ok=True)
                        raise
                self.reply({'count': count + 1})
                return
            if length > 16384:
                raise ValueError('Request is too large')
            data = json.loads(self.rfile.read(length))
            if path == '/api/projects':
                self.reply(create_project(data.get('name', ''), data.get('preset', 'balanced')))
            elif path.endswith('/start'):
                root = project_path(path.strip('/').split('/')[2])
                start_project(root)
                self.reply(read_state(root))
            elif path.endswith('/cancel'):
                root = project_path(path.strip('/').split('/')[2])
                with LOCK:
                    if ACTIVE != root.name:
                        raise ValueError('This project is not running')
                    stop_process()
                self.reply({'ok': True})
            else:
                self.send_error(404)
        except (ValueError, KeyError, IndexError) as error:
            self.reply({'error': str(error)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            self.reply({'error': str(error)}, 500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        checks = check_tools()
        print(json.dumps(checks, indent=2))
        return 0 if all(checks.values()) else 1
    JOBS.mkdir(exist_ok=True)
    # Bind before recovering state: a second launch must not alter active jobs.
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    for folder in JOBS.iterdir():
        if (folder / 'status.json').exists() and read_state(folder)['state'] == 'running':
            update(folder, state='interrupted', message='The app stopped during processing. Create a new project using the original photos.')
    def terminate(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, terminate)
    signal.signal(signal.SIGTERM, terminate)
    print(f'Head Studio is ready: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        stop_process()
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
