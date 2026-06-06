import bpy
from bpy.props import (
    StringProperty, BoolProperty, FloatProperty, IntProperty,
    EnumProperty, CollectionProperty, PointerProperty, FloatVectorProperty,
)
from bpy.types import PropertyGroup


def _trigger_composite(self, context):
    obj = context.active_object
    if obj and obj.texture_layer_stack.auto_composite:
        from . import compositor
        compositor.composite_stack(obj)


BLEND_MODE_ITEMS = [
    ('NORMAL',      'Normal',        ''),
    ('MULTIPLY',    'Multiply',      ''),
    ('SCREEN',      'Screen',        ''),
    ('OVERLAY',     'Overlay',       ''),
    ('SOFT_LIGHT',  'Soft Light',    ''),
    ('HARD_LIGHT',  'Hard Light',    ''),
    ('ADD',         'Add',           ''),
    ('SUBTRACT',    'Subtract',      ''),
    ('DARKEN',      'Darken',        ''),
    ('LIGHTEN',     'Lighten',       ''),
    ('DIFFERENCE',  'Difference',    ''),
    ('HUE',         'Hue',           ''),
    ('SATURATION',  'Saturation',    ''),
    ('COLOR',       'Color',         ''),
    ('VALUE',       'Value',         ''),
]

ADJUSTMENT_ITEMS = [
    ('NONE',               'None',               ''),
    ('BRIGHTNESS_CONTRAST','Brightness/Contrast', ''),
    ('HSV',                'Hue/Sat/Value',       ''),
    ('LEVELS',             'Levels',              ''),
]


class TextureLayer(PropertyGroup):
    type: EnumProperty(
        name="Type",
        items=[
            ('PAINT',      'Paint',      'Paintable image layer', 'BRUSH_DATA', 0),
            ('FILL',       'Fill',       'Solid color layer',     'SNAP_FACE',  1),
            ('ADJUSTMENT', 'Adjustment', 'Non-destructive FX',    'MODIFIER',   2),
        ],
        default='PAINT',
        update=_trigger_composite,
    )
    image: PointerProperty(type=bpy.types.Image)
    visible: BoolProperty(name="Visible", default=True, update=_trigger_composite)
    locked:  BoolProperty(name="Locked",  default=False)
    opacity: FloatProperty(
        name="Opacity", default=1.0, min=0.0, max=1.0,
        subtype='FACTOR', update=_trigger_composite,
    )
    blend_mode: EnumProperty(
        name="Blend Mode", items=BLEND_MODE_ITEMS,
        default='NORMAL', update=_trigger_composite,
    )

    # ── Adjustment type ────────────────────────────────────────────
    adjustment_type: EnumProperty(
        name="Adjustment", items=ADJUSTMENT_ITEMS,
        default='NONE', update=_trigger_composite,
    )

    # Brightness / Contrast
    brightness: FloatProperty(name="Brightness", default=0.0, min=-1.0, max=1.0, update=_trigger_composite)
    contrast:   FloatProperty(name="Contrast",   default=0.0, min=-1.0, max=1.0, update=_trigger_composite)

    # Hue / Saturation / Value
    hue:        FloatProperty(name="Hue",        default=0.5, min=0.0, max=1.0, update=_trigger_composite)
    saturation: FloatProperty(name="Saturation", default=1.0, min=0.0, max=2.0, update=_trigger_composite)
    value_mult: FloatProperty(name="Value",      default=1.0, min=0.0, max=2.0, update=_trigger_composite)

    # Levels
    levels_in_min:  FloatProperty(name="In Min",  default=0.0, min=0.0, max=1.0,  update=_trigger_composite)
    levels_in_max:  FloatProperty(name="In Max",  default=1.0, min=0.0, max=1.0,  update=_trigger_composite)
    levels_gamma:   FloatProperty(name="Gamma",   default=1.0, min=0.1, max=9.99, update=_trigger_composite)
    levels_out_min: FloatProperty(name="Out Min", default=0.0, min=0.0, max=1.0,  update=_trigger_composite)
    levels_out_max: FloatProperty(name="Out Max", default=1.0, min=0.0, max=1.0,  update=_trigger_composite)

    # Fill layer color
    fill_color: FloatVectorProperty(
        name="Fill Color", size=4,
        default=(0.5, 0.5, 0.5, 1.0), min=0.0, max=1.0,
        subtype='COLOR', update=_trigger_composite,
    )


class TextureLayerStack(PropertyGroup):
    layers:          CollectionProperty(type=TextureLayer)
    active_index:    IntProperty(name="Active Layer", default=0)
    composite_image: PointerProperty(type=bpy.types.Image, name="Composite Image")
    auto_composite:  BoolProperty(name="Auto Composite", default=False)
    stack_width:     IntProperty(name="Width",  default=2048, min=1, max=16384)
    stack_height:    IntProperty(name="Height", default=2048, min=1, max=16384)
