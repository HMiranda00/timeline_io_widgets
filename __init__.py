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

# Thickness settings
LINE_WIDTH = 1           # Thin vertical lines
BRACKET_WIDTH = 3        # Bracket thickness

# Height of the timeline header (where frame numbers are displayed)
HEADER_HEIGHT = 18

# Bracket dimensions (positioned just below the header)
BRACKET_HEIGHT = 16      # Small bracket height (+15%)
BRACKET_ARM_LENGTH = 12  # Horizontal arm length (+15%)

# Indicator dot size (small mark over the numbers)
INDICATOR_SIZE = 4


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
    - Small indicator dot in the header (over the numbers)
    - Thin vertical line from header to brackets
    - Bracket shape just below the header
    """
    line_w = LINE_WIDTH
    bracket_w = BRACKET_WIDTH
    half_line = line_w / 2
    half_bracket = bracket_w / 2
    
    # Area boundaries
    header_bottom = region_height - HEADER_HEIGHT
    bracket_top = header_bottom
    bracket_bottom = header_bottom - BRACKET_HEIGHT
    
    # 1. Draw small indicator dot in header area (over the numbers)
    indicator_y = region_height - INDICATOR_SIZE - 2  # Near top of header
    draw_rect(shader, 
              x - half_line, 
              indicator_y,
              line_w, 
              INDICATOR_SIZE, 
              color)
    
    # 2. Draw thin vertical line (from below header to bottom of view)
    draw_rect(shader,
              x - half_line,
              0,
              line_w,
              bracket_bottom,
              color)
    
    # 3. Draw bracket just below header
    if is_in_handle:
        # "[" shape - vertical bar + arms extending right
        # Vertical bar of bracket
        draw_rect(shader, x - half_bracket, bracket_bottom, bracket_w, BRACKET_HEIGHT, color)
        
        # Top arm (horizontal, extending right)
        draw_rect(shader, 
                  x - half_bracket, 
                  bracket_top - bracket_w, 
                  BRACKET_ARM_LENGTH, 
                  bracket_w, 
                  color)
        
        # Bottom arm (horizontal, extending right)
        draw_rect(shader, 
                  x - half_bracket, 
                  bracket_bottom, 
                  BRACKET_ARM_LENGTH, 
                  bracket_w, 
                  color)
    else:
        # "]" shape - vertical bar + arms extending left
        # Vertical bar of bracket
        draw_rect(shader, x - half_bracket, bracket_bottom, bracket_w, BRACKET_HEIGHT, color)
        
        # Top arm (horizontal, extending left)
        draw_rect(shader, 
                  x - BRACKET_ARM_LENGTH + half_bracket, 
                  bracket_top - bracket_w, 
                  BRACKET_ARM_LENGTH, 
                  bracket_w, 
                  color)
        
        # Bottom arm (horizontal, extending left)
        draw_rect(shader, 
                  x - BRACKET_ARM_LENGTH + half_bracket, 
                  bracket_bottom, 
                  BRACKET_ARM_LENGTH, 
                  bracket_w, 
                  color)


def draw_range_overlay(shader, in_x, out_x, region_height, color):
    """Draw the highlighted range area between the brackets (just below header)"""
    if in_x >= out_x:
        return
    
    header_bottom = region_height - HEADER_HEIGHT
    bracket_top = header_bottom
    bracket_bottom = header_bottom - BRACKET_HEIGHT
    
    # Draw overlay inside the bracket area
    overlay_padding = BRACKET_WIDTH
    draw_rect(shader, 
              in_x + overlay_padding,
              bracket_bottom + overlay_padding, 
              out_x - in_x - overlay_padding * 2,
              BRACKET_HEIGHT - overlay_padding * 2, 
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
    
    # Draw labels when hovering or dragging (below the brackets)
    label_y = height - HEADER_HEIGHT - BRACKET_HEIGHT - 18
    
    if state.hover_in or state.is_dragging_in:
        label_x = in_x + 8
        draw_label(label_x, label_y, f"IN: {scene.frame_start}")
    
    if state.hover_out or state.is_dragging_out:
        import blf
        text = f"OUT: {scene.frame_end}"
        blf.size(0, 11)
        text_w, _ = blf.dimensions(0, text)
        label_x = out_x - text_w - 8
        draw_label(label_x, label_y, text)


# -----------------------------------------------------------------------------
# Operators
# -----------------------------------------------------------------------------

# Hit detection threshold for handles
HANDLE_HIT_THRESHOLD = 25


def check_handle_hover(context, mouse_x):
    """Check if mouse is hovering over a handle and return which one"""
    if not state.enabled:
        return None
    
    scene = context.scene
    try:
        in_x = frame_to_region_x(context, scene.frame_start)
        out_x = frame_to_region_x(context, scene.frame_end)
    except Exception:
        return None
    
    dist_in = abs(mouse_x - in_x)
    dist_out = abs(mouse_x - out_x)
    
    if dist_in < HANDLE_HIT_THRESHOLD and dist_in <= dist_out:
        return "in"
    elif dist_out < HANDLE_HIT_THRESHOLD:
        return "out"
    return None


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
        
        handle = check_handle_hover(context, mouse_x)
        
        if handle == "in":
            self.handle_type = "in"
            self.initial_frame = scene.frame_start
            state.is_dragging_in = True
        elif handle == "out":
            self.handle_type = "out"
            self.initial_frame = scene.frame_end
            state.is_dragging_out = True
        else:
            return {'PASS_THROUGH'}
        
        # Set cursor to indicate horizontal movement
        context.window.cursor_modal_set('SCROLL_X')
        
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
            context.window.cursor_modal_restore()
            state.is_dragging_in = False
            state.is_dragging_out = False
            context.area.tag_redraw()
            return {'FINISHED'}
        
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            if self.handle_type == "in":
                scene.frame_start = self.initial_frame
            else:
                scene.frame_end = self.initial_frame
            
            context.window.cursor_modal_restore()
            state.is_dragging_in = False
            state.is_dragging_out = False
            context.area.tag_redraw()
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}


class TIMELINE_OT_hover_cursor(bpy.types.Operator):
    """Update cursor when hovering over handles"""
    bl_idname = "timeline.hover_cursor"
    bl_label = "IO Handles Hover Check"
    bl_options = {'INTERNAL'}
    
    def invoke(self, context, event):
        if not state.enabled or context.region is None:
            return {'PASS_THROUGH'}
        
        # Get mouse position from event (relative to region)
        mouse_x = event.mouse_region_x
        mouse_y = event.mouse_region_y
        
        # Check if mouse is in our region
        if not (0 <= mouse_x <= context.region.width and 
                0 <= mouse_y <= context.region.height):
            # Reset hover state when outside
            if state.hover_in or state.hover_out:
                state.hover_in = False
                state.hover_out = False
                context.window.cursor_set('DEFAULT')
                context.area.tag_redraw()
            return {'PASS_THROUGH'}
        
        handle = check_handle_hover(context, mouse_x)
        
        # Update hover state
        old_hover_in = state.hover_in
        old_hover_out = state.hover_out
        
        state.hover_in = (handle == "in")
        state.hover_out = (handle == "out")
        
        # Change cursor based on hover
        if handle is not None:
            context.window.cursor_set('SCROLL_X')
        else:
            context.window.cursor_set('DEFAULT')
        
        # Redraw if hover state changed
        if old_hover_in != state.hover_in or old_hover_out != state.hover_out:
            context.area.tag_redraw()
        
        return {'PASS_THROUGH'}


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
hover_operators = {}  # Track hover operators per area

classes = (
    TIMELINE_OT_drag_io_handle,
    TIMELINE_OT_hover_cursor,
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
        # Dopesheet
        km = kc.keymaps.new(name='Dopesheet', space_type='DOPESHEET_EDITOR')
        kmi = km.keymap_items.new(TIMELINE_OT_drag_io_handle.bl_idname, 
                                   'LEFTMOUSE', 'PRESS')
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(TIMELINE_OT_hover_cursor.bl_idname,
                                   'MOUSEMOVE', 'ANY')
        addon_keymaps.append((km, kmi))
        
        # Graph Editor
        km = kc.keymaps.new(name='Graph Editor', space_type='GRAPH_EDITOR')
        kmi = km.keymap_items.new(TIMELINE_OT_drag_io_handle.bl_idname,
                                   'LEFTMOUSE', 'PRESS')
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(TIMELINE_OT_hover_cursor.bl_idname,
                                   'MOUSEMOVE', 'ANY')
        addon_keymaps.append((km, kmi))
        
        # NLA Editor
        km = kc.keymaps.new(name='NLA Editor', space_type='NLA_EDITOR')
        kmi = km.keymap_items.new(TIMELINE_OT_drag_io_handle.bl_idname,
                                   'LEFTMOUSE', 'PRESS')
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(TIMELINE_OT_hover_cursor.bl_idname,
                                   'MOUSEMOVE', 'ANY')
        addon_keymaps.append((km, kmi))
        
        # Sequencer
        km = kc.keymaps.new(name='Sequencer', space_type='SEQUENCE_EDITOR')
        kmi = km.keymap_items.new(TIMELINE_OT_drag_io_handle.bl_idname,
                                   'LEFTMOUSE', 'PRESS')
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(TIMELINE_OT_hover_cursor.bl_idname,
                                   'MOUSEMOVE', 'ANY')
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
