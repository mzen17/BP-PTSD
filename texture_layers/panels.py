import bpy


# ── UIList ────────────────────────────────────────────────────────────────────

class TEXTURE_LAYERS_UL_layers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname):
        layer = item
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            # Visibility eye
            row.prop(layer, 'visible', text='',
                     icon='HIDE_OFF' if layer.visible else 'HIDE_ON',
                     emboss=False)

            # Type badge
            _TYPE_ICON = {
                'PAINT':      'BRUSH_DATA',
                'FILL':       'SNAP_FACE',
                'ADJUSTMENT': 'MODIFIER',
            }
            row.label(text='', icon=_TYPE_ICON.get(layer.type, 'IMAGE_DATA'))

            # Name
            row.prop(layer, 'name', text='', emboss=False)

            # Blend mode (compact)
            row.prop(layer, 'blend_mode', text='')

            # Opacity slider
            row.prop(layer, 'opacity', text='', slider=True)

            # Lock
            row.prop(layer, 'locked', text='',
                     icon='LOCKED' if layer.locked else 'UNLOCKED',
                     emboss=False)

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text='', icon='IMAGE_DATA')


# ── Add-layer menu ────────────────────────────────────────────────────────────

class TEXTURE_LAYERS_MT_add_layer(bpy.types.Menu):
    bl_label = "Add Layer"

    def draw(self, context):
        layout = self.layout
        for t, label, icon in (
            ('PAINT',      'Paint Layer',      'BRUSH_DATA'),
            ('FILL',       'Fill Layer',       'SNAP_FACE'),
            ('ADJUSTMENT', 'Adjustment Layer', 'MODIFIER'),
        ):
            op = layout.operator('texture_layers.add_layer',
                                 text=label, icon=icon)
            op.layer_type = t


# ── Shared draw functions ─────────────────────────────────────────────────────

def _draw_adjustment_props(layout, layer):
    adj = layer.adjustment_type
    if adj == 'BRIGHTNESS_CONTRAST':
        col = layout.column(align=True)
        col.prop(layer, 'brightness', slider=True)
        col.prop(layer, 'contrast',   slider=True)

    elif adj == 'HSV':
        col = layout.column(align=True)
        col.prop(layer, 'hue',        slider=True)
        col.prop(layer, 'saturation', slider=True)
        col.prop(layer, 'value_mult', slider=True)

    elif adj == 'LEVELS':
        col = layout.column(align=True)
        col.label(text="Input Range:")
        row = col.row(align=True)
        row.prop(layer, 'levels_in_min',  text="Min")
        row.prop(layer, 'levels_gamma',   text="Mid")
        row.prop(layer, 'levels_in_max',  text="Max")
        col.separator(factor=0.5)
        col.label(text="Output Range:")
        row = col.row(align=True)
        row.prop(layer, 'levels_out_min', text="Min")
        row.prop(layer, 'levels_out_max', text="Max")


def _draw_layers_panel(layout, context):
    obj = context.active_object
    if obj is None:
        layout.label(text="No active object", icon='INFO')
        return

    stack = obj.texture_layer_stack

    # ── Not yet initialised ──────────────────────────────────────
    if stack.composite_image is None:
        box = layout.box()
        box.label(text="No layer stack", icon='INFO')
        row = box.row(align=True)
        row.prop(stack, 'stack_width',  text="W")
        row.prop(stack, 'stack_height', text="H")
        box.operator('texture_layers.new_stack', icon='ADD')

        layout.separator()
        layout.label(text="Import from PSD:")
        try:
            from psd_tools import PSDImage  # noqa: F401
            layout.operator('texture_layers.import_psd', icon='IMPORT')
        except ImportError:
            layout.label(text="psd-tools not installed", icon='ERROR')
            layout.operator('texture_layers.install_psd_tools', icon='PACKAGE')
        return

    # ── Header row ───────────────────────────────────────────────
    row = layout.row(align=True)
    row.label(text=f"{len(stack.layers)} Layer(s)", icon='RENDERLAYERS')
    row.prop(stack, 'auto_composite', text="Auto", toggle=True,
             icon='FILE_REFRESH')

    # ── Layer list ────────────────────────────────────────────────
    layout.template_list(
        'TEXTURE_LAYERS_UL_layers', '',
        stack, 'layers',
        stack, 'active_index',
        rows=4, maxrows=8,
    )

    # ── Toolbar ───────────────────────────────────────────────────
    row = layout.row(align=True)
    op = row.operator('texture_layers.add_layer', text='', icon='ADD')
    op.layer_type = 'PAINT'
    row.menu('TEXTURE_LAYERS_MT_add_layer', text='', icon='DOWNARROW_HLT')
    row.operator('texture_layers.delete_layer',    text='', icon='REMOVE')
    row.separator()
    op = row.operator('texture_layers.move_layer', text='', icon='TRIA_UP')
    op.direction = 'UP'
    op = row.operator('texture_layers.move_layer', text='', icon='TRIA_DOWN')
    op.direction = 'DOWN'
    row.separator()
    row.operator('texture_layers.duplicate_layer', text='', icon='DUPLICATE')
    row.operator('texture_layers.merge_down',      text='', icon='TRIA_DOWN_BAR')

    layout.separator(factor=0.5)

    # ── Paint / Composite actions ─────────────────────────────────
    col = layout.column(align=True)
    col.operator('texture_layers.set_paint_target', icon='BRUSH_DATA')
    col.operator('texture_layers.composite',         icon='FILE_REFRESH')

    # ── Active layer properties ───────────────────────────────────
    if stack.layers and 0 <= stack.active_index < len(stack.layers):
        layer = stack.layers[stack.active_index]
        box   = layout.box()

        # Header
        header = box.row()
        header.label(text=layer.name, icon='LAYER_ACTIVE')

        if layer.type == 'FILL':
            box.prop(layer, 'fill_color')

        # Adjustment controls
        box.prop(layer, 'adjustment_type',
                 text="Adjustment" if layer.type == 'ADJUSTMENT' else "FX")
        if layer.adjustment_type != 'NONE':
            _draw_adjustment_props(box, layer)

    # ── Footer ─────────────────────────────────────────────────────
    layout.separator(factor=0.5)
    row = layout.row(align=True)
    row.label(text="Composite:", icon='IMAGE_DATA')
    row.prop(stack, 'composite_image', text="")

    layout.separator(factor=0.5)
    split = layout.row(align=True)
    split.operator('texture_layers.setup_material', icon='MATERIAL')
    split.operator('texture_layers.import_psd',     icon='IMPORT')


def _draw_brushes_panel(layout, context):
    ts = context.scene.tool_settings
    ip = ts.image_paint

    # Current brush
    layout.template_ID(ip, 'brush', new='brush.add')

    if ip.brush:
        brush = ip.brush
        col = layout.column(align=True)
        col.prop(brush, 'size',     text="Size",     slider=True)
        col.prop(brush, 'strength', text="Strength", slider=True)
        col.prop(brush, 'blend',    text="Mode")

        layout.separator(factor=0.5)
        layout.operator('texture_layers.new_brush_preset', icon='PLUS')

    layout.separator()
    layout.label(text="All Presets:", icon='PRESET')

    col = layout.column(align=True)
    active_brush = ip.brush
    for brush in sorted(bpy.data.brushes, key=lambda b: b.name):
        if not brush.use_paint_image:
            continue
        op = col.operator(
            'texture_layers.set_brush',
            text=brush.name,
            icon='BRUSH_DATA',
            depress=(brush == active_brush),
        )
        op.brush_name = brush.name


def _draw_project_panel(layout, context):
    ip = context.scene.tool_settings.image_paint

    col = layout.column()
    col.label(text="Projection Settings", icon='UV')
    col.prop(ip, 'use_occlude',            text="Occlude")
    col.prop(ip, 'use_backface_culling',   text="Backface Culling")
    col.prop(ip, 'use_normal_falloff',     text="Normal Falloff")
    if ip.use_normal_falloff:
        col.prop(ip, 'normal_angle')

    col.separator()
    col.label(text="Seam:")
    col.prop(ip, 'seam_bleed')

    col.separator()
    col.label(text="Clone Source:")
    col.prop(ip, 'use_clone_layer')


# ── Mixin base classes ────────────────────────────────────────────────────────

class _LayersBase:
    bl_label   = "Layers"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context): _draw_layers_panel(self.layout, context)


class _BrushesBase:
    bl_label   = "Brush Library"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context): _draw_brushes_panel(self.layout, context)


class _ProjectBase:
    bl_label   = "Project Image"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context): _draw_project_panel(self.layout, context)


# ── 3D Viewport panels (only visible in Texture Paint mode) ───────────────────

class TEXTURE_LAYERS_PT_layers_3d(_LayersBase, bpy.types.Panel):
    bl_idname     = "TEXTURE_LAYERS_PT_layers_3d"
    bl_space_type = 'VIEW_3D'
    bl_region_type= 'UI'
    bl_category   = "Tex Layers"
    bl_label      = "Layers"

    @classmethod
    def poll(cls, context): return context.mode == 'PAINT_TEXTURE'


class TEXTURE_LAYERS_PT_brushes_3d(_BrushesBase, bpy.types.Panel):
    bl_idname     = "TEXTURE_LAYERS_PT_brushes_3d"
    bl_space_type = 'VIEW_3D'
    bl_region_type= 'UI'
    bl_category   = "Tex Layers"
    bl_label      = "Brush Library"

    @classmethod
    def poll(cls, context): return context.mode == 'PAINT_TEXTURE'


class TEXTURE_LAYERS_PT_project_3d(_ProjectBase, bpy.types.Panel):
    bl_idname     = "TEXTURE_LAYERS_PT_project_3d"
    bl_space_type = 'VIEW_3D'
    bl_region_type= 'UI'
    bl_category   = "Tex Layers"
    bl_label      = "Project Image"

    @classmethod
    def poll(cls, context): return context.mode == 'PAINT_TEXTURE'


# ── Image Editor panels ───────────────────────────────────────────────────────

class TEXTURE_LAYERS_PT_layers_img(_LayersBase, bpy.types.Panel):
    bl_idname     = "TEXTURE_LAYERS_PT_layers_img"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type= 'UI'
    bl_category   = "Tex Layers"
    bl_label      = "Layers"


class TEXTURE_LAYERS_PT_brushes_img(_BrushesBase, bpy.types.Panel):
    bl_idname     = "TEXTURE_LAYERS_PT_brushes_img"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type= 'UI'
    bl_category   = "Tex Layers"
    bl_label      = "Brush Library"


class TEXTURE_LAYERS_PT_project_img(_ProjectBase, bpy.types.Panel):
    bl_idname     = "TEXTURE_LAYERS_PT_project_img"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type= 'UI'
    bl_category   = "Tex Layers"
    bl_label      = "Project Image"


# ── Registration list ─────────────────────────────────────────────────────────

classes = [
    TEXTURE_LAYERS_UL_layers,
    TEXTURE_LAYERS_MT_add_layer,
    TEXTURE_LAYERS_PT_layers_3d,
    TEXTURE_LAYERS_PT_brushes_3d,
    TEXTURE_LAYERS_PT_project_3d,
    TEXTURE_LAYERS_PT_layers_img,
    TEXTURE_LAYERS_PT_brushes_img,
    TEXTURE_LAYERS_PT_project_img,
]
