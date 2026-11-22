"""Dependency-free, pixel-accurate YOLO overlay and portable YAML metadata.

The preview is an SVG *sidecar* that references the clean PNG using a
relative URI. Unlike Blender's viewport outlines, every rectangle comes
from the exact normalized YOLO coordinates written to the TXT label file.
"""
from html import escape
from pathlib import Path
from urllib.parse import quote


_COLORS = ('#00ff91', '#00bfff', '#ffca28', '#ff5c7a',
           '#bd82ff', '#49ead8', '#ff8a3d', '#f0ff6b')


def label_text(boxes):
    """Serialized values used by *both* TXT and preview (7 decimals)."""
    return ''.join(
        f"{int(b['class_id'])} {b['x']:.7f} {b['y']:.7f} "
        f"{b['w']:.7f} {b['h']:.7f}\n" for b in boxes
    )


def parse_label_text(text):
    """Parse the actual YOLO TXT, not unrounded floating point geometry."""
    rows = []
    for index, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f'YOLO line {index}: expected 5 values')
        cls = int(fields[0])
        x, y, w, h = map(float, fields[1:])
        if cls < 0 or not (0 <= x <= 1 and 0 <= y <= 1 and
                           0 < w <= 1 and 0 < h <= 1):
            raise ValueError(f'YOLO line {index}: values out of range')
        rows.append((cls, x, y, w, h))
    return rows


def portable_data_yaml(classes):
    """Omit absolute `path:`; the YAML file's directory is the dataset root.

    Ultralytics resolves train/val relative to the YAML location when no
    `path` is supplied. Validation files are not auto-generated here.
    """
    import json
    if not classes or set(classes) != set(range(len(classes))):
        raise ValueError('YOLO class IDs must be contiguous from 0')
    out = ['train: images/train', 'val: images/val',
           f'nc: {len(classes)}', 'names:']
    for idx in sorted(classes):
        out.append(f'  {idx}: {json.dumps(classes[idx], ensure_ascii=False)}')
    return '\n'.join(out) + '\n'


def svg_from_labels(label_contents, class_names, width, height, image_filename):
    """Return a standalone SVG overlay document referencing a clean PNG.

    image_filename is a filename (not a path); URI is relative to
    previews/<stem>.svg, e.g. ../images/train/sample_000001.png.
    """
    if width <= 0 or height <= 0:
        raise ValueError('Image dimensions must be positive')
    if Path(image_filename).name != image_filename or image_filename in {'.', '..'}:
        raise ValueError('Expected an image filename without directories')
    labels = parse_label_text(label_contents)
    uri = '../images/train/' + quote(image_filename, safe='')
    result = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (f'<svg xmlns="http://www.w3.org/2000/svg" '
         f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'),
        '<title>BVT Studio — YOLO export preview</title>',
        '<desc>Colored rectangles are computed from the exported YOLO TXT.</desc>',
        f'<image href="{escape(uri, quote=True)}" x="0" y="0" '
        f'width="{width}" height="{height}"/>',
    ]
    stroke = max(1.0, min(width, height) / 500.0)
    font = max(10.0, min(width, height) / 70.0)
    for cls, x, y, w, h in labels:
        left = (x - w / 2) * width
        top = (y - h / 2) * height
        bw, bh = w * width, h * height
        color = _COLORS[cls % len(_COLORS)]
        # Escape user-entered class names. Rounded TXT coordinates may
        # produce harmless <1e-4px deviations at frame edges.
        title = escape(f'{cls}: {class_names.get(cls, str(cls))}')
        result.append(
            f'<rect x="{left:.4f}" y="{top:.4f}" width="{bw:.4f}" '
            f'height="{bh:.4f}" fill="none" stroke="{color}" '
            f'stroke-width="{stroke:.2f}"/>'
        )
        # Keep label inside the image when its box touches the top edge.
        baseline = max(font, top - 2.0)
        result.append(
            f'<text x="{max(0.0, left):.4f}" y="{baseline:.4f}" '
            f'font-family="sans-serif" font-size="{font:.2f}" '
            f'font-weight="bold" stroke="#000" stroke-width="2.2" '
            f'paint-order="stroke" fill="{color}">{title}</text>'
        )
    result.append('</svg>')
    return '\n'.join(result) + '\n'
