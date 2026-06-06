import bpy
import numpy as np
from bpy.props import StringProperty, IntProperty, EnumProperty, BoolProperty
from . import compositor


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique_name(base: str, collection) -> str:
    names = {img.name for img in collection}
    if base not in names:
        return base
    i = 1
    while f"{base}.{i:03d}" in names:
        i += 1
    return f"{base}.{i:03d}"


def _blank_pixels(width: int, height: int) -> list:
    return [0.0] * (width * height * 4)


# ── Stack initialisation ──────────────────────────────────────────────────────

class TEXTURE_LAYERS_OT_new_stack(bpy.types.Operator):
    """Create a new texture layer stack for the active object"""
    bl_idname  = "texture_layers.new_stack"
    bl_label   = "New Layer Stack"
    bl_options = {'REGISTER', 'UNDO'}

    width:  IntProperty(name="Width",  default=2048, min=64, max=16384)
    height: IntProperty(name="Height", default=2048, min=64, max=16384)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        stack = context.active_object.texture_layer_stack
        self.width  = stack.stack_width
        self.height = stack.stack_height
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        col = self.layout.column(align=True)
        col.prop(self, 'width')
        col.prop(self, 'height')

    def execute(self, context):
        obj   = context.active_object
        stack = obj.texture_layer_stack

        stack.layers.clear()
        stack.active_index  = 0
        stack.stack_width   = self.width
        stack.stack_height  = self.height

        img_name = _unique_name(f"{obj.name}_composite", bpy.data.images)
        comp     = bpy.data.images.new(img_name, width=self.width, height=self.height, alpha=True)
        comp.use_fake_user  = True
        stack.composite_image = comp

        bpy.ops.texture_layers.add_layer(layer_type='PAINT')
        bpy.ops.texture_layers.setup_material()

        self.report({'INFO'}, f"Layer stack {self.width}×{self.height} created")
        return {'FINISHED'}


# ── Layer CRUD ────────────────────────────────────────────────────────────────

class TEXTURE_LAYERS_OT_add_layer(bpy.types.Operator):
    """Add a layer above the current active layer"""
    bl_idname  = "texture_layers.add_layer"
    bl_label   = "Add Layer"
    bl_options = {'REGISTER', 'UNDO'}

    layer_type: EnumProperty(
        name="Type",
        items=[
            ('PAINT',      'Paint Layer',      ''),
            ('FILL',       'Fill Layer',       ''),
            ('ADJUSTMENT', 'Adjustment Layer', ''),
        ],
        default='PAINT',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.texture_layer_stack.composite_image is not None

    def execute(self, context):
        obj   = context.active_object
        stack = obj.texture_layer_stack
        idx   = stack.active_index

        layer      = stack.layers.add()
        layer.type = self.layer_type

        # Place directly above the current active layer
        new_pos = max(0, idx)
        stack.layers.move(len(stack.layers) - 1, new_pos)
        stack.active_index = new_pos

        if self.layer_type == 'PAINT':
            count    = sum(1 for l in stack.layers if l.type == 'PAINT')
            img_name = _unique_name(f"{obj.name}_layer_{count:03d}", bpy.data.images)
            img      = bpy.data.images.new(
                img_name,
                width  = stack.stack_width,
                height = stack.stack_height,
                alpha  = True,
            )
            img.use_fake_user = True
            img.pixels[:]     = _blank_pixels(stack.stack_width, stack.stack_height)
            layer.image = img
            layer.name  = img_name

        elif self.layer_type == 'FILL':
            layer.name = "Fill Layer"

        elif self.layer_type == 'ADJUSTMENT':
            layer.name = "Adjustment Layer"

        compositor.composite_stack(obj)
        return {'FINISHED'}


class TEXTURE_LAYERS_OT_delete_layer(bpy.types.Operator):
    """Delete the active layer"""
    bl_idname  = "texture_layers.delete_layer"
    bl_label   = "Delete Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and len(obj.texture_layer_stack.layers) > 0

    def execute(self, context):
        obj   = context.active_object
        stack = obj.texture_layer_stack
        idx   = stack.active_index
        layer = stack.layers[idx]

        if layer.image:
            layer.image.use_fake_user = False
            if layer.image.users == 0:
                bpy.data.images.remove(layer.image)

        stack.layers.remove(idx)
        stack.active_index = max(0, min(idx, len(stack.layers) - 1))

        compositor.composite_stack(obj)
        return {'FINISHED'}


class TEXTURE_LAYERS_OT_move_layer(bpy.types.Operator):
    """Move the active layer up or down in the stack"""
    bl_idname  = "texture_layers.move_layer"
    bl_label   = "Move Layer"
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(
        items=[('UP', 'Up', ''), ('DOWN', 'Down', '')],
        default='UP',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and len(obj.texture_layer_stack.layers) > 1

    def execute(self, context):
        obj   = context.active_object
        stack = obj.texture_layer_stack
        idx   = stack.active_index
        n     = len(stack.layers)

        if self.direction == 'UP' and idx > 0:
            stack.layers.move(idx, idx - 1)
            stack.active_index = idx - 1
        elif self.direction == 'DOWN' and idx < n - 1:
            stack.layers.move(idx, idx + 1)
            stack.active_index = idx + 1

        compositor.composite_stack(obj)
        return {'FINISHED'}


class TEXTURE_LAYERS_OT_duplicate_layer(bpy.types.Operator):
    """Duplicate the active layer"""
    bl_idname  = "texture_layers.duplicate_layer"
    bl_label   = "Duplicate Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and len(obj.texture_layer_stack.layers) > 0

    def execute(self, context):
        obj   = context.active_object
        stack = obj.texture_layer_stack
        idx   = stack.active_index
        src   = stack.layers[idx]

        dst = stack.layers.add()
        # Copy scalar properties
        for attr in ('type', 'visible', 'locked', 'opacity', 'blend_mode',
                     'adjustment_type', 'brightness', 'contrast',
                     'hue', 'saturation', 'value_mult',
                     'levels_in_min', 'levels_in_max', 'levels_gamma',
                     'levels_out_min', 'levels_out_max'):
            setattr(dst, attr, getattr(src, attr))
        dst.fill_color = src.fill_color
        dst.name       = src.name + " copy"

        if src.type == 'PAINT' and src.image:
            new_img = src.image.copy()
            new_img.name          = _unique_name(src.image.name + "_copy", bpy.data.images)
            new_img.use_fake_user = True
            dst.image = new_img

        stack.layers.move(len(stack.layers) - 1, idx)
        stack.active_index = idx

        compositor.composite_stack(obj)
        return {'FINISHED'}


class TEXTURE_LAYERS_OT_merge_down(bpy.types.Operator):
    """Merge the active layer into the one directly below it"""
    bl_idname  = "texture_layers.merge_down"
    bl_label   = "Merge Down"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None:
            return False
        stack = obj.texture_layer_stack
        idx   = stack.active_index
        return len(stack.layers) > 1 and idx < len(stack.layers) - 1

    def execute(self, context):
        obj   = context.active_object
        stack = obj.texture_layer_stack
        idx   = stack.active_index
        top   = stack.layers[idx]
        bot   = stack.layers[idx + 1]

        if top.type != 'PAINT' or bot.type != 'PAINT':
            self.report({'WARNING'}, "Merge Down only supports Paint layers")
            return {'CANCELLED'}
        if top.image is None or bot.image is None:
            return {'CANCELLED'}

        w, h = stack.stack_width, stack.stack_height

        top_pix = compositor.get_layer_pixels(top, w, h)
        bot_pix = compositor.get_layer_pixels(bot, w, h)
        if top_pix is None or bot_pix is None:
            return {'CANCELLED'}

        top_pix = compositor.apply_adjustments(top, top_pix)
        bot_pix = compositor.apply_adjustments(bot, bot_pix)

        top_a       = top_pix[:, 3:4] * top.opacity
        merged_rgb  = compositor._blend(bot_pix[:, :3], top_pix[:, :3], top_a, top.blend_mode)
        merged_a    = bot_pix[:, 3:4] + top_a * (1.0 - bot_pix[:, 3:4])
        merged      = np.concatenate([merged_rgb, merged_a], axis=1)

        bot.image.pixels[:] = merged.flatten().tolist()
        bot.image.update()

        if top.image:
            top.image.use_fake_user = False
            if top.image.users == 0:
                bpy.data.images.remove(top.image)
        stack.layers.remove(idx)
        stack.active_index = max(0, idx - 1)

        compositor.composite_stack(obj)
        return {'FINISHED'}


# ── Paint target ──────────────────────────────────────────────────────────────

class TEXTURE_LAYERS_OT_set_paint_target(bpy.types.Operator):
    """Use the active layer as the texture-paint canvas"""
    bl_idname = "texture_layers.set_paint_target"
    bl_label  = "Paint This Layer"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None:
            return False
        stack = obj.texture_layer_stack
        if not stack.layers:
            return False
        layer = stack.layers[stack.active_index]
        return layer.type == 'PAINT' and layer.image is not None

    def execute(self, context):
        obj   = context.active_object
        stack = obj.texture_layer_stack
        layer = stack.layers[stack.active_index]
        img   = layer.image

        # Set canvas for texture paint
        context.scene.tool_settings.image_paint.canvas = img

        # Mirror in all open Image Editors
        for area in context.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.spaces.active.image = img

        self.report({'INFO'}, f"Painting on: {layer.name}")
        return {'FINISHED'}


# ── Composite ─────────────────────────────────────────────────────────────────

class TEXTURE_LAYERS_OT_composite(bpy.types.Operator):
    """Flatten all visible layers into the composite image"""
    bl_idname = "texture_layers.composite"
    bl_label  = "Composite Now"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.texture_layer_stack.composite_image is not None

    def execute(self, context):
        compositor.composite_stack(context.active_object)
        return {'FINISHED'}


# ── Material setup ────────────────────────────────────────────────────────────

class TEXTURE_LAYERS_OT_setup_material(bpy.types.Operator):
    """Wire the composite image into the active material's Base Color"""
    bl_idname  = "texture_layers.setup_material"
    bl_label   = "Setup Material"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.texture_layer_stack.composite_image is not None

    def execute(self, context):
        obj      = context.active_object
        comp_img = obj.texture_layer_stack.composite_image

        if not obj.data.materials:
            mat = bpy.data.materials.new(f"{obj.name}_Material")
            obj.data.materials.append(mat)
        else:
            mat = obj.active_material
            if mat is None:
                mat = bpy.data.materials.new(f"{obj.name}_Material")
                obj.data.materials[obj.active_material_index] = mat

        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        def find_or_create(node_type, loc):
            for n in nodes:
                if n.type == node_type:
                    return n
            n = nodes.new(f'ShaderNode{node_type.title().replace("_","")}')
            n.location = loc
            return n

        principled = None
        for n in nodes:
            if n.type == 'BSDF_PRINCIPLED':
                principled = n
                break
        if principled is None:
            principled = nodes.new('ShaderNodeBsdfPrincipled')
            principled.location = (0, 0)

        output = None
        for n in nodes:
            if n.type == 'OUTPUT_MATERIAL':
                output = n
                break
        if output is None:
            output = nodes.new('ShaderNodeOutputMaterial')
            output.location = (320, 0)

        # Image texture node — reuse if already pointing at our composite
        tex_node = None
        for n in nodes:
            if n.type == 'TEX_IMAGE' and n.image == comp_img:
                tex_node = n
                break
        if tex_node is None:
            tex_node          = nodes.new('ShaderNodeTexImage')
            tex_node.location = (-370, 0)
        tex_node.image = comp_img

        links.new(tex_node.outputs['Color'],   principled.inputs['Base Color'])
        links.new(principled.outputs['BSDF'],  output.inputs['Surface'])

        self.report({'INFO'}, f"Material linked to {comp_img.name}")
        return {'FINISHED'}


# ── PSD import ────────────────────────────────────────────────────────────────

class TEXTURE_LAYERS_OT_install_psd_tools(bpy.types.Operator):
    """Install the psd-tools and pillow packages via pip"""
    bl_idname = "texture_layers.install_psd_tools"
    bl_label  = "Install psd-tools"

    def execute(self, context):
        import subprocess, sys
        try:
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install', 'psd-tools', 'pillow'],
                timeout=120,
            )
            self.report({'INFO'}, "psd-tools installed — please restart Blender")
        except Exception as e:
            self.report({'ERROR'}, f"Installation failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


class TEXTURE_LAYERS_OT_import_psd(bpy.types.Operator):
    """Import layers from a PSD file into the current stack"""
    bl_idname  = "texture_layers.import_psd"
    bl_label   = "Import PSD"
    bl_options = {'REGISTER', 'UNDO'}

    filepath:   StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.psd;*.psb', options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            from psd_tools import PSDImage
            from PIL import Image as PILImage
        except ImportError:
            self.report({'ERROR'},
                "psd-tools is not installed. Click 'Install psd-tools' first.")
            return {'CANCELLED'}

        obj   = context.active_object
        stack = obj.texture_layer_stack

        try:
            psd = PSDImage.open(self.filepath)
        except Exception as e:
            self.report({'ERROR'}, f"Cannot open PSD: {e}")
            return {'CANCELLED'}

        w, h = psd.width, psd.height

        # Bootstrap stack if not yet initialised
        if stack.composite_image is None:
            stack.stack_width  = w
            stack.stack_height = h
            img_name = _unique_name(f"{obj.name}_composite", bpy.data.images)
            comp = bpy.data.images.new(img_name, width=w, height=h, alpha=True)
            comp.use_fake_user  = True
            stack.composite_image = comp

        imported = 0
        psd_layers = list(psd)
        for psd_layer in reversed(psd_layers):
            try:
                pil_img = psd_layer.composite()
            except Exception:
                continue
            if pil_img is None:
                continue

            if pil_img.size != (w, h):
                pil_img = pil_img.resize((w, h), PILImage.LANCZOS)

            pil_img = pil_img.convert('RGBA')
            arr = np.array(pil_img, dtype=np.float32) / 255.0
            arr = np.flipud(arr).reshape(-1, 4)          # Blender: bottom-left origin

            img_name = _unique_name(
                f"{obj.name}_{psd_layer.name or 'layer'}", bpy.data.images)
            bl_img = bpy.data.images.new(img_name, width=w, height=h, alpha=True)
            bl_img.use_fake_user = True
            bl_img.pixels[:] = arr.flatten().tolist()

            layer       = stack.layers.add()
            layer.type  = 'PAINT'
            layer.name  = psd_layer.name or f"PSD Layer {imported}"
            layer.image = bl_img
            layer.visible = getattr(psd_layer, 'visible', True)
            if hasattr(psd_layer, 'opacity'):
                layer.opacity = psd_layer.opacity / 255.0
            imported += 1

        bpy.ops.texture_layers.setup_material()
        compositor.composite_stack(obj)

        self.report({'INFO'}, f"Imported {imported} layers from PSD")
        return {'FINISHED'}


# ── Brush library ─────────────────────────────────────────────────────────────

class TEXTURE_LAYERS_OT_set_brush(bpy.types.Operator):
    """Activate a brush by name"""
    bl_idname = "texture_layers.set_brush"
    bl_label  = "Set Brush"

    brush_name: StringProperty()

    def execute(self, context):
        brush = bpy.data.brushes.get(self.brush_name)
        if brush:
            context.tool_settings.image_paint.brush = brush
        return {'FINISHED'}


class TEXTURE_LAYERS_OT_new_brush_preset(bpy.types.Operator):
    """Duplicate the current brush and save it as a named preset"""
    bl_idname  = "texture_layers.new_brush_preset"
    bl_label   = "Save Brush Preset"
    bl_options = {'REGISTER', 'UNDO'}

    name: StringProperty(name="Preset Name", default="My Brush")

    def invoke(self, context, event):
        self.name = context.tool_settings.image_paint.brush.name + " copy"
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, 'name')

    @classmethod
    def poll(cls, context):
        ip = context.scene.tool_settings.image_paint
        return ip.brush is not None

    def execute(self, context):
        src = context.tool_settings.image_paint.brush
        new = src.copy()
        new.name          = self.name
        new.use_fake_user = True
        self.report({'INFO'}, f"Saved preset: {self.name}")
        return {'FINISHED'}


# ── Registration list (consumed by __init__.py) ───────────────────────────────

classes = [
    TEXTURE_LAYERS_OT_new_stack,
    TEXTURE_LAYERS_OT_add_layer,
    TEXTURE_LAYERS_OT_delete_layer,
    TEXTURE_LAYERS_OT_move_layer,
    TEXTURE_LAYERS_OT_duplicate_layer,
    TEXTURE_LAYERS_OT_merge_down,
    TEXTURE_LAYERS_OT_set_paint_target,
    TEXTURE_LAYERS_OT_composite,
    TEXTURE_LAYERS_OT_setup_material,
    TEXTURE_LAYERS_OT_install_psd_tools,
    TEXTURE_LAYERS_OT_import_psd,
    TEXTURE_LAYERS_OT_set_brush,
    TEXTURE_LAYERS_OT_new_brush_preset,
]
