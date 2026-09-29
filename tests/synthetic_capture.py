"""Generate a textured ellipsoid photographed around 360 degrees; no external data.

Run with .colmap-env/bin/python (NumPy installed there).
This deliberately simple scene tests integration, not human-head accuracy.
"""
import math
from pathlib import Path
import struct
import zlib

import numpy as np


def png(path, image):
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
    h, w = image.shape[:2]
    raw = b''.join(b'\x00' + row.tobytes() for row in image)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def main():
    output = Path(__file__).resolve().parents[1] / '.test-data/capture'
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(73)
    texture = np.full((512, 1024, 3), [205., 193., 165.])
    for _ in range(2700):
        x, y = rng.integers(0, 1024), rng.integers(0, 512)
        r = rng.integers(2, 12)
        x0, x1 = max(0, x-r), min(1024, x+r+1)
        y0, y1 = max(0, y-r), min(512, y+r+1)
        xx, yy = np.meshgrid(np.arange(x0,x1),np.arange(y0,y1))
        mask = (xx-x)**2+(yy-y)**2 < r*r
        texture[y0:y1,x0:x1][mask] = rng.integers(15, 235, 3)
    resolution = 640
    yy, xx = np.meshgrid(np.arange(resolution), np.arange(resolution), indexing='ij')
    rays_x = (xx - resolution/2) / 800
    rays_y = -(yy - resolution/2) / 800
    scale = np.array([.72,.95,.70])
    views = [(2*math.pi*i/24,0.) for i in range(24)]
    views += [(2*math.pi*i/12, height) for height in (-1.4,1.4) for i in range(12)]
    for index, (angle, height) in enumerate(views):
        camera = np.array([3.4*math.sin(angle), height, 3.4*math.cos(angle)])
        forward = -camera / np.linalg.norm(camera)
        right = np.cross(forward, [0.,1.,0.]); right /= np.linalg.norm(right)
        up = np.cross(right,forward)
        directions = forward + rays_x[:,:,None]*right + rays_y[:,:,None]*up
        d, c = directions / scale, camera / scale
        a = (d*d).sum(axis=2); b = 2*(d*c).sum(axis=2); cc=(c*c).sum()-1
        disc=b*b-4*a*cc
        distance=(-b-np.sqrt(np.maximum(disc,0)))/(2*a)
        points=(camera+directions*distance[:,:,None])/scale
        u=(np.arctan2(points[:,:,0],points[:,:,2])/(2*math.pi)+.5)*1024
        v=(np.arcsin(np.clip(points[:,:,1],-1,1))/math.pi+.5)*511
        x0=np.floor(u).astype(int)%1024;y0=np.floor(v).astype(int).clip(0,511)
        fx=(u-np.floor(u))[:,:,None];fy=(v-np.floor(v))[:,:,None]
        color=((1-fx)*texture[y0,x0]+fx*texture[y0,(x0+1)%1024])*(1-fy)
        color+=((1-fx)*texture[np.minimum(y0+1,511),x0]+fx*texture[np.minimum(y0+1,511),(x0+1)%1024])*fy
        image=np.full((resolution,resolution,3),245,dtype=np.uint8)
        image[disc>=0]=color[disc>=0].astype(np.uint8)
        png(output/f'view_{index:02d}.png',image)
    print(output)


if __name__=='__main__':
    main()
