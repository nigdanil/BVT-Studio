"""BVT Studio — 2.5D image, glass and YOLO workflow for Blender 5.2+."""
bl_info = {
    "name": "BVT Studio — 2.5D Dataset Builder",
    "author": "BVT Studio contributors",
    "version": (0, 2, 2),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar (N) > BVT Studio",
    "description": "Photo planes, named glass collections, YOLO annotations and export",
    "category": "3D View",
}

from . import props, scene_tools, glass, annotation, ui

MODULES = (props, scene_tools, glass, annotation, ui)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()


if __name__ == "__main__":
    register()
