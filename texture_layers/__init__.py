"""
Texture Layers — Mari / Substance Painter-style layer-based painting for Blender.

N-Panel location
  • 3D Viewport > Texture Paint mode > Sidebar > Tex Layers
  • Image Editor > Sidebar > Tex Layers
"""

bl_info = {
    "name":        "Texture Layers",
    "description": "Mari/Substance Painter-style layer-based texture painting",
    "author":      "Texture Layers Addon",
    "version":     (1, 0, 0),
    "blender":     (5, 1, 0),
    "location":    "3D Viewport (Texture Paint) / Image Editor > N-Panel > Tex Layers",
    "doc_url":     "",
    "tracker_url": "",
    "category":    "Paint",
}

import bpy
from bpy.props import PointerProperty

from . import props, operators, panels, compositor


# ── Auto-composite timer ──────────────────────────────────────────────────────

def _auto_composite_tick():
    """
    Called by bpy.app.timers every 0.5 s while at least one object has
    auto_composite enabled.  Returns the next delay in seconds.
    """
    ctx = bpy.context
    if ctx is None:
        return 1.0

    obj = getattr(ctx, 'active_object', None)
    if obj is not None:
        stack = obj.texture_layer_stack
        if stack.auto_composite and stack.composite_image is not None:
            compositor.composite_stack(obj)
            return 0.5

    return 1.0


# ── Registration ──────────────────────────────────────────────────────────────

_CLASSES = (
    [props.TextureLayer, props.TextureLayerStack]
    + operators.classes
    + panels.classes
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Object.texture_layer_stack = PointerProperty(
        type=props.TextureLayerStack,
        name="Texture Layer Stack",
    )

    if not bpy.app.timers.is_registered(_auto_composite_tick):
        bpy.app.timers.register(_auto_composite_tick, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_auto_composite_tick):
        bpy.app.timers.unregister(_auto_composite_tick)

    if hasattr(bpy.types.Object, 'texture_layer_stack'):
        del bpy.types.Object.texture_layer_stack

    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
