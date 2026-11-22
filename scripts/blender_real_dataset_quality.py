"""Read-only paired YOLO dataset calibration (alpha.5-step6).

Run via Blender 5.2+:
 blender --background --factory-startup --python-exit-code 1 \\
   --python scripts/blender_real_dataset_quality.py -- \\
   --clean-dir PATH --augmented-dir PATH --labels-dir PATH \\
   [--masks-dir PATH] --output-dir PATH [--profile LIGHT|MEDIUM|HEAVY]

Input images/labels/masks are NEVER written. Validated PASS references only are
listed in accepted_manifest.json; this tool does not train or run YOLO.
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
import numpy as np
from bvt_studio.real_dataset_qa import evaluate_dataset_pair

IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp'}


def sha256_file(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def images_by_stem(folder, suffixes):
    """Relative path without extension is the stable sample key."""
    mapping = {}
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if path.is_symlink():
            raise ValueError(f'Symlinked input not supported: {path}')
        key = path.relative_to(folder).with_suffix('').as_posix()
        if key in mapping:
            raise ValueError(f'Duplicate sample stem: {key}')
        mapping[key] = path
    return mapping


def load_blender_image(path, *, grayscale=False):
    """Decode input through Blender; rows are converted to YOLO top-down."""
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        width, height = map(int, image.size)
        if width < 1 or height < 1:
            raise ValueError(f'Empty image: {path}')
        count = len(image.pixels)
        channels, extra = divmod(count, width * height)
        if channels not in (1, 2, 3, 4) or extra:
            raise ValueError(f'Unexpected Blender pixel buffer shape: {path}')
        buf = np.empty(count, dtype=np.float32)
        image.pixels.foreach_get(buf)
        pixels = buf.reshape(height, width, channels)[::-1].copy()
        if grayscale:
            return pixels[:, :, 0]
        if channels == 1 or channels == 2:
            return np.repeat(pixels[:, :, :1], 3, axis=2)
        return pixels[:, :, :3].copy()
    finally:
        bpy.data.images.remove(image)


def save_overlay(filepath, augmented_rgb, objects):
    """Save diagnostic annotations to OUT only; no input pixels modified."""
    height, width, _ = augmented_rgb.shape
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[:, :, :3] = augmented_rgb
    for obj in objects:
        x0, y0, x1, y1 = obj['bbox_xyxy_px']
        color = {'PASS': (.1, 1., .2), 'REVIEW': (1., .75, .1),
                 'REJECT': (1., .05, .1)}[obj['status']]
        for thick in (0, 1):
            xa, xb = min(width-1,x0+thick), max(0,x1-thick-1)
            ya, yb = min(height-1,y0+thick), max(0,y1-thick-1)
            if xa <= xb and ya <= yb:
                rgba[ya, xa:xb+1, :3] = color
                rgba[yb, xa:xb+1, :3] = color
                rgba[ya:yb+1, xa, :3] = color
                rgba[ya:yb+1, xb, :3] = color
    filepath.parent.mkdir(parents=True, exist_ok=True)
    image = bpy.data.images.new('BVT_Step6_QA_Overlay', width=width, height=height, alpha=True)
    try:
        image.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).ravel())
        image.filepath_raw = str(filepath)
        image.file_format = 'PNG'
        image.save()
    finally:
        bpy.data.images.remove(image)


def configure(argv):
    parser = argparse.ArgumentParser(description='BVT real YOLO dataset paired QA')
    parser.add_argument('--clean-dir', required=True)
    parser.add_argument('--augmented-dir', required=True)
    parser.add_argument('--labels-dir', required=True)
    parser.add_argument('--masks-dir', help='Verified glass masks matched by sample key (optional)')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--profile', default='MEDIUM', choices=('LIGHT','MEDIUM','HEAVY'))
    parser.add_argument('--strict', action='store_true', help='Nonzero exit on REJECT/REVIEW/ERROR')
    parser.add_argument('--max-overlays', type=int, default=12,
                        help='Maximum diagnostic PNG overlays written (0 disables)')
    opts = parser.parse_args(argv)
    if opts.max_overlays < 0:
        parser.error('--max-overlays must be >= 0')
    dirs = {name:Path(getattr(opts,name)).expanduser().resolve() for name in
            ('clean_dir','augmented_dir','labels_dir','output_dir')}
    if opts.masks_dir:
        dirs['masks_dir'] = Path(opts.masks_dir).expanduser().resolve()
    for key, folder in dirs.items():
        if key != 'output_dir' and not folder.is_dir():
            parser.error(f'Missing {key}: {folder}')
    output = dirs['output_dir']
    for key, folder in dirs.items():
        if key == 'output_dir':
            continue
        if output == folder or output.is_relative_to(folder) or folder.is_relative_to(output):
            parser.error('Output and input directories must not overlap')
    return opts, dirs


def main(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    opts, dirs = configure(argv)
    clean = images_by_stem(dirs['clean_dir'], IMAGE_SUFFIXES)
    augmented = images_by_stem(dirs['augmented_dir'], IMAGE_SUFFIXES)
    labels = images_by_stem(dirs['labels_dir'], {'.txt'})
    masks = images_by_stem(dirs['masks_dir'], {'.png'}) if 'masks_dir' in dirs else {}
    if not clean:
        raise ValueError('No original images found')
    output = dirs['output_dir']
    output.mkdir(parents=True, exist_ok=True)
    cases, passed, object_csv, overlays = [], [], [], 0
    for key, base in clean.items():
        candidate, label_path, mask_path = augmented.get(key), labels.get(key), masks.get(key)
        sample = {'sample':key, 'status':'ERROR', 'profile':opts.profile,
                  'input':{}, 'reasons':[], 'objects':[]}
        files = {'clean':base, 'augmented':candidate, 'labels':label_path,
                 'mask':mask_path}
        hashes = {name:sha256_file(path) for name,path in files.items() if path is not None}
        sample['input'] = {
            'original':base.relative_to(dirs['clean_dir']).as_posix(),
            'augmented':candidate.relative_to(dirs['augmented_dir']).as_posix() if candidate else None,
            'labels':label_path.relative_to(dirs['labels_dir']).as_posix() if label_path else None,
            'mask':mask_path.relative_to(dirs['masks_dir']).as_posix() if mask_path else None,
            'sha256':hashes,
        }
        try:
            if candidate is None:
                raise ValueError('No augmented image for this sample')
            if label_path is None:
                raise ValueError('No matching YOLO Detect TXT')
            original = load_blender_image(base)
            modified = load_blender_image(candidate)
            mask_rgb = load_blender_image(mask_path, grayscale=True) if mask_path else None
            label_text = label_path.read_bytes().decode('utf-8-sig')
            quality = evaluate_dataset_pair(original, modified, label_text,
                                            profile=opts.profile, glass_mask=mask_rgb)
            sample.update(quality)
            if overlays < opts.max_overlays:
                location = output / 'overlays' / (key + '.png')
                save_overlay(location, modified, quality['objects'])
                sample['overlay'] = location.relative_to(output).as_posix()
                overlays += 1
            for obj in quality['objects']:
                object_csv.append(dict(sample=key, index=obj['index'],
                                       class_id=obj['class_id'], status=obj['status'],
                                       scope=obj['scope'],
                                       **obj['metrics']))
            if quality['accepted']:
                passed.append({'sample':key,'profile':opts.profile,
                               'input':sample['input']})
        except (ValueError, OSError, UnicodeError, RuntimeError) as exc:
            sample['status'] = 'ERROR'
            sample['accepted'] = False
            sample['reasons'] = [f'{type(exc).__name__}: {exc}']
        for name,path in files.items():
            if path and sha256_file(path) != hashes[name]:
                raise AssertionError(f'Input changed during read-only QA: {path}')
        cases.append(sample)
        print(f'BVT DATASET QA: {sample["status"]} — {key} — '
              f'{len(sample.get("objects",[]))} SKU(s)')
    extra = sorted(set(augmented)-set(clean))
    if extra:
        cases.append({'status':'ERROR','sample':'(unmatched augmented)',
                      'reasons':['Augmented files without corresponding original: '+', '.join(extra[:20])],
                      'accepted':False})
    counts = {state:sum(item['status']==state for item in cases)
              for state in ('PASS','REVIEW','REJECT','ERROR')}
    class_totals = {}
    for obj in object_csv:
        class_id = str(obj['class_id'])
        entry = class_totals.setdefault(class_id, {'class_id':class_id, 'sku_count':0,
                                                     'pass':0,'review':0,'reject':0})
        entry['sku_count'] += 1
        entry[obj['status'].lower()] += 1
    report = {
        'stage':'alpha.5-step6-pilot','base_commit':'60d8eb7',
        'blender':bpy.app.version_string,
        'profile':opts.profile, 'decoder':'Blender float RGB, top-down pixel alignment',
        'mask_policy':'Missing mask is REVIEW, never PASS; far-outside changes REJECT',
        'label_policy':'Read-only YOLO Detect TXT, verified SHA256 before/after',
        'metric_warning':'Pixel/gradient QA is not YOLO mAP, OCR, or photorealism validation',
        'counts':counts,'per_class':class_totals,'samples':cases,
    }
    (output/'real_dataset_quality_report.json').write_text(
        json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    (output/'accepted_manifest.json').write_text(
        json.dumps({'stage':'alpha.5-step6-pilot','accepted':passed,
                    'warning':'File references only; no images or labels copied'},
                   indent=2,ensure_ascii=False),encoding='utf-8')
    with (output/'samples.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream,fieldnames=['sample','status','profile','sku_count','reasons'])
        writer.writeheader()
        for x in cases:
            writer.writerow(dict(sample=x['sample'],status=x['status'],
                                 profile=x.get('profile',''),sku_count=len(x.get('objects',[])),
                                 reasons=' | '.join(x.get('reasons',[]))))
    with (output/'objects.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        columns = ['sample','index','class_id','status','scope','changed_ratio',
                   'bright_ratio','detail_loss_ratio','mean_rgb_delta',
                   'significant_edge_pixels','measured_pixels']
        writer = csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        writer.writerows(object_csv)
    with (output/'classes.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=['class_id','sku_count','pass','review','reject'])
        writer.writeheader()
        writer.writerows(class_totals[key] for key in sorted(class_totals,key=int))
    print('BVT REAL DATASET QA: '+str(counts))
    print('DATASET_QA_DIR='+str(output))
    if opts.strict and any(counts[state] for state in ('REVIEW','REJECT','ERROR')):
        raise SystemExit(2)
    return report


if __name__ == '__main__':
    main()
