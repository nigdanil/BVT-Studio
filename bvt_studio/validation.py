"""Pure-Python YOLO quality report rules, independent of Blender's bpy API.

Blocking errors come from annotation.collect_boxes (the export contract).
Heuristic warnings never block export.  This keeps labels and QA aligned.
"""


ERROR_CODES = (
    ('No active scene camera', 'NO_CAMERA'),
    ('No enabled annotation planes', 'NO_ANNOTATIONS'),
    ('negative class ID', 'NEGATIVE_CLASS_ID'),
    ('conflicting names', 'CLASS_NAME_CONFLICT'),
    ('empty mesh', 'EMPTY_MESH'),
    ('behind camera', 'BEHIND_CAMERA'),
    ('outside frame', 'OUTSIDE_FRAME'),
    ('zero or tiny projected bbox', 'DEGENERATE_BOX'),
    ('Class IDs must be contiguous', 'CLASS_ID_GAP'),
    ('Near-duplicate boxes:', 'DUPLICATE_BOX'),
)


def intersection_over_union(first, second):
    """IoU of normalized bounding rectangles; works with dicts from collect_boxes."""
    xmin = max(first['xmin'], second['xmin'])
    ymin = max(first['ymin'], second['ymin'])
    xmax = min(first['xmax'], second['xmax'])
    ymax = min(first['ymax'], second['ymax'])
    intersection = max(0.0, xmax - xmin) * max(0.0, ymax - ymin)
    area_a = max(0.0, first['w']) * max(0.0, first['h'])
    area_b = max(0.0, second['w']) * max(0.0, second['h'])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _target_name(message, object_names):
    """Associate legacy error text with a scene object if possible.

    Choose longest matching name first: plane_p_001 must not shadow plane_p_001.001.
    """
    for name in sorted(object_names, key=len, reverse=True):
        if message.startswith(name + ':'):
            return name
    if message.startswith('Near-duplicate boxes: '):
        pair = message[len('Near-duplicate boxes: '):]
        for name in sorted(object_names, key=len, reverse=True):
            if pair.startswith(name + ' and '):
                return name
    return ''


def quality_report(boxes, blocking_errors, object_names, width, height):
    """Return a reproducible severity-coded snapshot for display in the sidebar.

    `blocking_errors` is the existing canonical collect_boxes error list.
    The extra overlap/tiny-object checks are warnings only.
    """
    issues = []
    for message in blocking_errors:
        code = next((code for pattern, code in ERROR_CODES if pattern in message),
                    'VALIDATION_ERROR')
        issues.append(dict(
            severity='ERROR', code=code, message=message,
            object_name=_target_name(message, object_names),
        ))

    width, height = max(int(width), 1), max(int(height), 1)
    for box in boxes:
        projected_w = box['w'] * width
        projected_h = box['h'] * height
        if projected_w < 5.0 or projected_h < 5.0:
            issues.append(dict(
                severity='WARNING', code='TINY_OBJECT',
                message=(f"{box['object']}: only {projected_w:.1f} x "
                         f"{projected_h:.1f} px at export resolution"),
                object_name=box['object'],
            ))

    for index, a in enumerate(boxes):
        for b in boxes[index + 1:]:
            overlap = intersection_over_union(a, b)
            if overlap >= 0.70:
                # Same-class near-identical objects are already hard errors.
                if overlap > 0.95 and a['class_id'] == b['class_id']:
                    continue
                issues.append(dict(
                    severity='WARNING', code='HIGH_OVERLAP',
                    message=(f"{a['object']} / {b['object']}: "
                             f"overlap {overlap:.0%}; review manually"),
                    object_name=a['object'],
                ))

    return dict(
        boxes=len(boxes),
        errors=sum(issue['severity'] == 'ERROR' for issue in issues),
        warnings=sum(issue['severity'] == 'WARNING' for issue in issues),
        issues=issues,
    )
