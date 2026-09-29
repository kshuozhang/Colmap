"""Isolated COLMAP process, using the macOS 11+ Python 3.9 wheel."""
import json
import sys
from pathlib import Path

import pycolmap as p


def main():
    stage, directory = sys.argv[1:3]
    root = Path(directory).resolve()
    config = json.loads((root / 'settings.json').read_text())
    images, database = str(root / 'images'), str(root / 'database.db')
    threads = config.get('threads', 4)
    if stage == 'features':
        opts = p.SiftExtractionOptions()
        opts.num_threads = threads
        opts.max_image_size = config['image_size']
        opts.max_num_features = 6000
        opts.first_octave = 0
        photos = json.loads((root / 'photos.json').read_text())
        same_size = len({tuple(photo['size']) for photo in photos}) == 1
        p.extract_features(database, images, camera_mode=p.CameraMode.SINGLE if same_size else p.CameraMode.AUTO,
                           sift_options=opts, device=p.Device.cpu)
    elif stage == 'matching':
        opts = p.SiftMatchingOptions()
        opts.num_threads = threads
        opts.max_num_matches = 6000
        matching = p.ExhaustiveMatchingOptions()
        matching.block_size = 25
        p.match_exhaustive(database, sift_options=opts, matching_options=matching,
                           device=p.Device.cpu)
    elif stage == 'mapping':
        opts = p.IncrementalPipelineOptions()
        opts.num_threads = threads
        opts.mapper.num_threads = threads
        opts.max_num_models = 5
        opts.min_model_size = 3
        output = root / 'sparse'
        output.mkdir(exist_ok=True)
        models = p.incremental_mapping(database, images, str(output), options=opts)
        if not models:
            raise RuntimeError('No connected reconstruction. Use sharper photos with more overlap and keep the subject still.')
        best_id, best = max(models.items(), key=lambda item: item[1].num_reg_images())
        # Returned dictionary IDs need not match numbered folders written by the mapper.
        # Persist the actual selected object, rather than guessing its on-disk index.
        selected = root / 'selected_sparse'
        selected.mkdir(exist_ok=True)
        best.write(str(selected))
        count = len(list((root / 'images').glob('*.jpg')))
        registered = best.num_reg_images()
        summary = {'model_id': best_id, 'registered': registered, 'total': count,
                   'points': best.num_points3D(), 'models': len(models)}
        (root / 'alignment.json').write_text(json.dumps(summary, indent=2))
        if registered < max(3, int(count * 0.6)):
            raise RuntimeError('Only %d/%d photos aligned. Add overlap and remove blurry or moving-subject photos before trying again.' % (registered, count))
    elif stage == 'undistort':
        summary = json.loads((root / 'alignment.json').read_text())
        opts = p.UndistortCameraOptions()
        opts.max_image_size = config['image_size']
        p.undistort_images(str(root / 'dense'), str(root / 'selected_sparse'),
                           images, undistort_options=opts)
    else:
        raise ValueError('Unknown stage: ' + stage)


if __name__ == '__main__':
    main()
