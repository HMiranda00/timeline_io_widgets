# SPDX-License-Identifier: GPL-3.0-or-later
# Timeline In/Out Widgets - Blender 5.0 Extension
# Adds draggable in/out frame handles as overlays in animation editors

import bpy
import gpu
from gpu_extras.batch import batch_for_shader


# -----------------------------------------------------------------------------
# Global State
# -----------------------------------------------------------------------------

class TimelineWidgetState:
    """Stores the state for the timeline widget overlay"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.draw_handlers = {}
            cls._instance.is_dragging_in = False
            cls._instance.is_dragging_out = False
            cls._instance.hover_in = False
            cls._instance.hover_out = False
            cls._instance.enabled = True
        return cls._instance


state = TimelineWidgetState()


# -----------------------------------------------------------------------------
# Coordinate Conversion Functions
# -----------------------------------------------------------------------------

def frame_to_region_x(context, frame):
    """Convert a frame number to region x coordinate using View2D."""
    region = context.region
    view2d = region.view2d
    x, _ = view2d.view_to_region(float(frame), 0.0, clip=False)
    return x


def region_x_to_frame(context, x):
    """Convert region x coordinate to frame number using View2D."""
    region = context.region
    view2d = region.view2d
    frame, _ = view2d.region_to_view(float(x), 0.0)
    return int(round(frame))


# -----------------------------------------------------------------------------
# Drawing Configuration
# -----------------------------------------------------------------------------

# Line thickness
LINE_WIDTH = 2

# Height of the timeline header (where frame numbers are displayed)
HEADER_HEIGHT = 22

# Bracket dimensions
BRACKET_HEIGHT = 45
BRACKET_ARM_LENGTH = 12


# -----------------------------------------------------------------------------
# Drawing Functions
# -----------------------------------------------------------------------------

def draw_rect(shader, x, y, width, height, color):
    """Draw a filled rectangle"""
    vertices = [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
    ]
    indices = [(0, 1, 2), (0, 2, 3)]
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.uniform_float("color", color)
    batch.draw(shader)


def draw_handle(shader, x, region_height, color, is_in_handle=True):
    """
    Draw a complete handle with:
    - Short indicator line in the header (over the numbers)
    - Main vertical line below the header
    - Bracket shape at bottom
    """
    line_w = LINE_WIDTH
    half_w = line_w / 2
    
    # Area boundaries
    header_top = region_height
    header_bottom = region_height - HEADER_HEIGHT
    content_bottom = 0
    
    # 1. Draw short indicator line in header area (over the numbers)
    indicator_height = HEADER_HEIGHT - 4  # Slight padding from edges
    draw_rect(shader, 
              x - half_w, 
              header_bottom + 2,  # 2px padding from bottom of header
              line_w, 
              indicator_height, 
              color)
    
    # 2. Draw main vertical line (from header bottom to bracket top)
    main_line_top = header_bottom
    main_line_bottom = BRACKET_HEIGHT
    draw_rect(shader,
              x - half_w,
              main_line_bottom,
              line_w,
              main_line_top - main_line_bottom,
              color)
    
    # 3. Draw bracket at bottom
    if is_in_handle:
        # "[" shape - vertical bar + arms extending right
        # Vertical bar of bracket
        draw_rect(shader, x - half_w, content_bottom, line_w, BRACKET_HEIGHT, color)
        
        # Top arm (horizontal, extending right)
        draw_rect(shader, 
                  x - half_w, 
                  BRACKET_HEIGHT - line_w, 
                  BRACKET_ARM_LENGTH, 
                  line_w, 
                  color)
        
        # Bottom arm (horizontal, extending right)
        draw_rect(shader, 
                  x - half_w, 
                  content_bottom, 
                  BRACKET_ARM_LENGTH, 
                  line_w, 
                  color)
    else:
        # "]" shape - vertical bar + arms extending left
        # Vertical bar of bracket
        draw_rect(shader, x - half_w, content_bottom, line_w, BRACKET_HEIGHT, color)
        
        # Top arm (horizontal, extending left)
        draw_rect(shader, 
                  x - BRACKET_ARM_LENGTH + half_w, 
                  BRACKET_HEIGHT - line_w, 
                  BRACKET_ARM_LENGTH, 
                  line_w, 
                  color)
        
        # Bottom arm (horizontal, extending left)
        draw_rect(shader, 
                  x - BRACKET_ARM_LENGTH + half_w, 
                  content_bottom, 
                  BRACKET_ARM_LENGTH, 
                  line_w, 
                  color)


def draw_range_overlay(shader, in_x, out_x, region_height, color):
    """Draw the highlighted range area between the brackets"""
    if in_x >= out_x:
        return
    
    # Only draw in the content area (below header, within bracket height)
    overlay_bottom = LINE_WIDTH  # Slight offset from bracket bottom
    overlay_top = BRACKET_HEIGHT - LINE_WIDTH  # Up to bracket top arm
    
    draw_rect(shader, 
              in_x + LINE_WIDTH,  # Offset to be inside the bracket
              overlay_bottom, 
              out_x - in_x - LINE_WIDTH * 2,  # Width between brackets
              overlay_top - overlay_bottom, 
              color)


def draw_label(x, y, text):
    """Draw a text label with background"""
    import blf
    
    font_id = 0
    blf.size(font_id, 11)
    
    text_w, text_h = blf.dimensions(font_id, text)
    padding = 4
    
    # Background
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    
    bg_verts = [
        (x - padding, y - padding),
        (x + text_w + padding, y - padding),
        (x + text_w + padding, y + text_h + padding),
        (x - padding, y + text_h + padding),
    ]
    bg_batch = batch_for_shader(shader, 'TRIS', {"pos": bg_verts}, 
                                 indices=[(0, 1, 2), (0, 2, 3)])
    shader.uniform_float("color", (0.0, 0.0, 0.0, 0.85))
    bg_batch.draw(shader)
    
    # Text
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, text)


def draw_timeline_widgets():
    """Main draw callback for timeline widgets"""
    if not state.enabled:
        return
    
    context = bpy.context
    
    if context is None:
        return
    
    region = context.region
    if region is None:
        return
    
    scene = context.scene
    if scene is None:
        return
    
    height = region.height
    width = region.width
    
    # Convert frame positions to region coordinates
    try:
        in_x = frame_to_region_x(context, scene.frame_start)
        out_x = frame_to_region_x(context, scene.frame_end)
    except Exception as e:
        print(f"Timeline IO Widgets: Error converting coordinates: {e}")
        return
    
    # Check if handles are visible
    margin = 100
    if in_x > width + margin and out_x > width + margin:
        return
    if in_x < -margin and out_x < -margin:
        return
    
    # Colors
    in_color_base = (0.3, 0.9, 0.4, 0.9)      # Green
    in_color_hover = (0.4, 1.0, 0.5, 1.0)
    in_color_drag = (0.5, 1.0, 0.6, 1.0)
    
    out_color_base = (1.0, 0.35, 0.3, 0.9)    # Red
    out_color_hover = (1.0, 0.5, 0.45, 1.0)
    out_color_drag = (1.0, 0.65, 0.6, 1.0)
    
    range_color = (0.4, 0.55, 0.8, 0.15)      # Blue tint
    
    # Select colors based on state
    if state.is_dragging_in:
        in_color = in_color_drag
    elif state.hover_in:
        in_color = in_color_hover
    else:
        in_color = in_color_base
    
    if state.is_dragging_out:
        out_color = out_color_drag
    elif state.hover_out:
        out_color = out_color_hover
    else:
        out_color = out_color_base
    
    # Setup GPU state
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    
    # Draw range overlay (between brackets only)
    draw_range_overlay(shader, in_x, out_x, height, range_color)
    
    # Draw handles
    draw_handle(shader, in_x, height, in_color, is_in_handle=True)
    draw_handle(shader, out_x, height, out_color, is_in_handle=False)
    
    gpu.state.blend_set('NONE')
    
    # Draw labels when hovering or dragging
    if state.hover_in or state.is_dragging_in:
        label_x = in_x + 10
        draw_label(label_x, height - HEADER_HEIGHT - 20, f"IN: {scene.frame_start}")
    
    if state.hover_out or state.is_dragging_out:
        import blf
        text = f"OUT: {scene.frame_end}"
        blf.size(0, 11)
        text_w, _ = blf.dimensions(0, text)
        label_x = out_x - text_w - 10
        draw_label(label_x, height - HEADER_HEIGHT - 20, text)


# -----------------------------------------------------------------------------
# Operators
# -----------------------------------------------------------------------------

class TIMELINE_OT_drag_io_handle(bpy.types.Operator):
    """Drag the in/out frame handles to adjust frame range"""
    bl_idname = "timeline.drag_io_handle"
    bl_label = "Drag In/Out Handle"
    bl_options = {'INTERNAL', 'UNDO'}
    
    handle_type: bpy.props.StringProperty(default="")
    initial_frame: bpy.props.IntProperty()
    
    @classmethod
    def poll(cls, context):
        return (context.area is not None and 
                context.region is not None and 
                state.enabled)
    
    def invoke(self, context, event):
        scene = context.scene
        mouse_x = event.mouse_region_x
        
        try:
            in_x = frame_to_region_x(context, scene.frame_start)
            out_x = frame_to_region_x(context, scene.frame_end)
        except Exception:
            return {'PASS_THROUGH'}
        
        threshold = 25
        
        dist_in = abs(mouse_x - in_x)
        dist_out = abs(mouse_x - out_x)
        
        if dist_in < threshold and dist_in <= dist_out:
            self.handle_type = "in"
            self.initial_frame = scene.frame_start
            state.is_dragging_in = True
        elif dist_out < threshold:
            self.handle_type = "out"
            self.initial_frame = scene.frame_end
            state.is_dragging_out = True
        else:
            return {'PASS_THROUGH'}
        
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        scene = context.scene
        
        if event.type == 'MOUSEMOVE':
            try:
                new_frame = region_x_to_frame(context, event.mouse_region_x)
            except Exception:
                return {'RUNNING_MODAL'}
            
            if self.handle_type == "in":
                new_frame = max(0, min(new_frame, scene.frame_end - 1))
                scene.frame_start = new_frame
            else:
                new_frame = max(scene.frame_start + 1, new_frame)
                scene.frame_end = new_frame
            
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            state.is_dragging_in = False
            state.is_dragging_out = False
            context.area.tag_redraw()
            return {'FINISHED'}
        
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            if self.handle_type == "in":
                scene.frame_start = self.initial_frame
            else:
                scene.frame_end = self.initial_frame
            
            state.is_dragging_in = False
            state.is_dragging_out = False
            context.area.tag_redraw()
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}


class TIMELINE_OT_toggle_io_widgets(bpy.types.Operator):
    """Toggle the In/Out frame widgets visibility"""
    bl_idname = "timeline.toggle_io_widgets"
    bl_label = "Toggle In/Out Widgets"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        state.enabled = not state.enabled
        
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        
        self.report({'INFO'}, f"In/Out widgets {'enabled' if state.enabled else 'disabled'}")
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# UI Menu
# -----------------------------------------------------------------------------

def draw_menu_item(self, context):
    layout = self.layout
    layout.separator()
    icon = 'CHECKBOX_HLT' if state.enabled else 'CHECKBOX_DEHLT'
    layout.operator(TIMELINE_OT_toggle_io_widgets.bl_idname,
                   text="In/Out Frame Handles", icon=icon)


# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

ANIMATION_SPACES = [
    'SpaceDopeSheetEditor',
    'SpaceGraphEditor',
    'SpaceNLA',
    'SpaceSequenceEditor',
]

VIEW_MENUS = [
    'DOPESHEET_MT_view',
    'GRAPH_MT_view',
    'NLA_MT_view',
    'SEQUENCER_MT_view',
]

addon_keymaps = []

classes = (
    TIMELINE_OT_drag_io_handle,
    TIMELINE_OT_toggle_io_widgets,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    for space_name in ANIMATION_SPACES:
        space_type = getattr(bpy.types, space_name, None)
        if space_type is not None:
            handler = space_type.draw_handler_add(
                draw_timeline_widgets, (), 'WINDOW', 'POST_PIXEL'
            )
            state.draw_handlers[space_name] = (space_type, handler)
    
    for menu_name in VIEW_MENUS:
        menu_type = getattr(bpy.types, menu_name, None)
        if menu_type is not None:
            menu_type.append(draw_menu_item)
    
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Dopesheet', space_type='DOPESHEET_EDITOR')
        kmi = km.keymap_items.new(TIMELINE_OT_drag_io_handle.bl_idname, 
                                   'LEFTMOUSE', 'PRESS')
        addon_keymaps.append((km, kmi))
        
        km = kc.keymaps.new(name='Graph Editor', space_type='GRAPH_EDITOR')
        kmi = km.keymap_items.new(TIMELINE_OT_drag_io_handle.bl_idname,
                                   'LEFTMOUSE', 'PRESS')
        addon_keymaps.append((km, kmi))
        
        km = kc.keymaps.new(name='NLA Editor', space_type='NLA_EDITOR')
        kmi = km.keymap_items.new(TIMELINE_OT_drag_io_handle.bl_idname,
                                   'LEFTMOUSE', 'PRESS')
        addon_keymaps.append((km, kmi))
        
        km = kc.keymaps.new(name='Sequencer', space_type='SEQUENCE_EDITOR')
        kmi = km.keymap_items.new(TIMELINE_OT_drag_io_handle.bl_idname,
                                   'LEFTMOUSE', 'PRESS')
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    addon_keymaps.clear()
    
    for menu_name in VIEW_MENUS:
        menu_type = getattr(bpy.types, menu_name, None)
        if menu_type is not None:
            try:
                menu_type.remove(draw_menu_item)
            except ValueError:
                pass
    
    for space_name, (space_type, handler) in state.draw_handlers.items():
        try:
            space_type.draw_handler_remove(handler, 'WINDOW')
        except Exception:
            pass
    state.draw_handlers.clear()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
