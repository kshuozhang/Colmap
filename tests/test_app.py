import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import threading
import urllib.request
import urllib.error

from PIL import Image
import app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.jobs = patch.object(app, 'JOBS', Path(self.temp.name))
        self.jobs.start()
        app.CANCEL.clear()

    def tearDown(self):
        self.jobs.stop()
        self.temp.cleanup()
        app.CANCEL.clear()

    def project(self):
        state = app.create_project('A head', 'draft')
        return app.project_path(state['id'])

    def test_photo_orientation_resize_and_original_unchanged(self):
        root = self.project()
        original = root/'originals'/'portrait.jpg'
        image = Image.new('RGB',(2000,1000),'red')
        exif = Image.Exif();exif[274] = 6
        image.save(original,exif=exif)
        before = original.read_bytes()
        app.prepare(root,{'image_size':800})
        with Image.open(root/'images'/'0000.jpg') as result:
            self.assertEqual(result.size,(400,800))
        self.assertEqual(before,original.read_bytes())

    def test_invalid_photo_names_source(self):
        root = self.project()
        (root/'originals'/'bad.jpg').write_text('not an image')
        with self.assertRaisesRegex(ValueError,'bad.jpg'):
            app.prepare(root,{'image_size':800})

    def test_heic_photo_import(self):
        root=self.project()
        source=root/'originals'/'phone.heic'
        Image.new('RGB',(400,600),(70,130,180)).save(source,format='HEIF')
        app.prepare(root,{'image_size':800})
        with Image.open(root/'images'/'0000.jpg') as result:
            self.assertEqual(result.size,(400,600))
            self.assertEqual(result.format,'JPEG')

    def test_low_photo_count_never_launches(self):
        root=self.project()
        with self.assertRaisesRegex(ValueError,'12–200'):
            app.start_project(root)
        self.assertEqual(app.read_state(root)['state'],'uploading')

    def test_project_traversal_rejected(self):
        with self.assertRaises(ValueError):app.project_path('../secrets')

    def test_openmvs_material_remains_visible_in_obj_readers(self):
        root=self.project()
        material=root/'head.mtl'
        material.write_text('newmtl material_00\nTr 1.000000\nmap_Kd texture.jpg\n')
        app.normalize_materials(root)
        self.assertIn('d 1.0\n',material.read_text())
        self.assertNotIn('Tr ',material.read_text())
        self.assertIn('map_Kd texture.jpg',material.read_text())

    def test_subprocess_failure_is_reported(self):
        root=self.project()
        with self.assertRaisesRegex(RuntimeError,'exit 7'):
            app.run_command(root,[app.sys.executable,'-c','raise SystemExit(7)'])

    def test_worker_error_reaches_user(self):
        root=self.project()
        with self.assertRaisesRegex(RuntimeError,'Only 2/24 photos aligned'):
            app.run_command(root,[app.sys.executable,'-c','raise RuntimeError("Only 2/24 photos aligned")'])

    def test_cancel_stops_active_process(self):
        root=self.project(); errors=[]
        def run():
            try:app.run_command(root,[app.sys.executable,'-c','import time; time.sleep(60)'])
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=run);thread.start()
        for _ in range(100):
            with app.LOCK:
                if app.PROCESS is not None:break
            app.time.sleep(.01)
        app.stop_process();thread.join(8)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(errors[0],InterruptedError)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch.object(app,'JOBS',Path(self.temp.name));self.patch.start()
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.patch.stop();self.temp.cleanup()

    def request(self,path,data=None,headers=None):
        headers=headers or {}
        request=urllib.request.Request(self.url+path,data=data,headers=headers)
        return urllib.request.urlopen(request)

    def test_token_required(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/projects',b'{}')
        self.assertEqual(error.exception.code,403)

    def test_external_origin_rejected(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/info',headers={'Origin':'https://example.com'})

    def test_upload_and_traversal(self):
        headers={'X-Head-Studio-Token':app.TOKEN}
        with self.request('/api/projects',b'{"name":"test","preset":"draft"}',headers) as response:
            identifier=json.load(response)['id']
        photo=io.BytesIO();Image.new('RGB',(300,300)).save(photo,format='PNG')
        with self.request(f'/api/projects/{identifier}/photos',photo.getvalue(),dict(headers,**{'X-Filename':'../../escape.png'})) as response:
            self.assertEqual(json.load(response)['count'],1)
        self.assertTrue((app.JOBS/identifier/'originals'/'0000_escape.png').is_file())
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/%2e%2e/README.md')


if __name__=='__main__':unittest.main()
