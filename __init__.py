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

def frame_to_region_x(region, frame):
    """
    Convert a frame number to region x coordinate using View2D.
    This properly accounts for zoom and pan in the timeline view.
    """
    view2d = region.view2d
    
    # view_to_region converts from view coordinates (frames) to region pixels
    # The y value doesn't matter for x conversion, so we use 0
    x, _ = view2d.view_to_region(frame, 0, clip=False)
    
    return x


def region_x_to_frame(region, x):
    """
    Convert region x coordinate to frame number using View2D.
    """
    view2d = region.view2d
    
    # region_to_view converts from region pixels to view coordinates (frames)
    frame, _ = view2d.region_to_view(x, 0)
    
    return int(round(frame))


# -----------------------------------------------------------------------------
# Drawing Functions
# -----------------------------------------------------------------------------

def draw_handle_shape(shader, x, height, color, is_in_handle=True):
    """Draw a handle shape at the given x position"""
    
    # Handle dimensions
    handle_width = 6
    bracket_height = min(50, height * 0.5)
    triangle_size = 10
    
    vertices = []
    indices = []
    idx = 0
    
    # Full height vertical line (thin)
    line_half_width = 1.5
    vertices.extend([
        (x - line_half_width, 0),
        (x + line_half_width, 0),
        (x + line_half_width, height),
        (x - line_half_width, height),
    ])
    indices.extend([(idx, idx+1, idx+2), (idx, idx+2, idx+3)])
    idx += 4
    
    if is_in_handle:
        # IN handle: bracket [ shape at bottom
        # Vertical part of bracket
        vertices.extend([
            (x, 0),
            (x + handle_width, 0),
            (x + handle_width, bracket_height),
            (x, bracket_height),
        ])
        indices.extend([(idx, idx+1, idx+2), (idx, idx+2, idx+3)])
        idx += 4
        
        # Horizontal part of bracket (top)
        vertices.extend([
            (x, bracket_height - handle_width),
            (x + handle_width * 2.5, bracket_height - handle_width),
            (x + handle_width * 2.5, bracket_height),
            (x, bracket_height),
        ])
        indices.extend([(idx, idx+1, idx+2), (idx, idx+2, idx+3)])
        idx += 4
        
        # Triangle arrow at top pointing right
        arrow_y = height - 25
        vertices.extend([
            (x, arrow_y - triangle_size),
            (x + triangle_size, arrow_y),
            (x, arrow_y + triangle_size),
        ])
        indices.append((idx, idx+1, idx+2))
        
    else:
        # OUT handle: bracket ] shape at bottom
        # Vertical part of bracket
        vertices.extend([
            (x - handle_width, 0),
            (x, 0),
            (x, bracket_height),
            (x - handle_width, bracket_height),
        ])
        indices.extend([(idx, idx+1, idx+2), (idx, idx+2, idx+3)])
        idx += 4
        
        # Horizontal part of bracket (top)
        vertices.extend([
            (x - handle_width * 2.5, bracket_height - handle_width),
            (x, bracket_height - handle_width),
            (x, bracket_height),
            (x - handle_width * 2.5, bracket_height),
        ])
        indices.extend([(idx, idx+1, idx+2), (idx, idx+2, idx+3)])
        idx += 4
        
        # Triangle arrow at top pointing left
        arrow_y = height - 25
        vertices.extend([
            (x, arrow_y - triangle_size),
            (x - triangle_size, arrow_y),
            (x, arrow_y + triangle_size),
        ])
        indices.append((idx, idx+1, idx+2))
    
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    
    shader.uniform_float("color", color)
    batch.draw(shader)


def draw_range_overlay(shader, x_start, x_end, height, color):
    """Draw a semi-transparent overlay for the frame range"""
    if x_start >= x_end:
        return
    
    vertices = [
        (x_start, 0),
        (x_end, 0),
        (x_end, height),
        (x_start, height),
    ]
    indices = [(0, 1, 2), (0, 2, 3)]
    
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.uniform_float("color", color)
    batch.draw(shader)


def draw_frame_label(x, y, frame, is_in=True):
    """Draw frame number label"""
    import blf
    
    font_id = 0
    label = "IN" if is_in else "OUT"
    text = f"{label}: {frame}"
    
    blf.size(font_id, 12)
    
    # Get text dimensions
    text_width, text_height = blf.dimensions(font_id, text)
    
    # Position: offset from handle
    padding = 8
    if is_in:
        text_x = x + padding
    else:
        text_x = x - text_width - padding
    
    # Draw background
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    bg_padding = 4
    bg_verts = [
        (text_x - bg_padding, y - bg_padding),
        (text_x + text_width + bg_padding, y - bg_padding),
        (text_x + text_width + bg_padding, y + text_height + bg_padding),
        (text_x - bg_padding, y + text_height + bg_padding),
    ]
    bg_indices = [(0, 1, 2), (0, 2, 3)]
    bg_batch = batch_for_shader(shader, 'TRIS', {"pos": bg_verts}, indices=bg_indices)
    
    shader.bind()
    shader.uniform_float("color", (0.1, 0.1, 0.1, 0.85))
    bg_batch.draw(shader)
    
    # Draw text
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.position(font_id, text_x, y, 0)
    blf.draw(font_id, text)


def draw_timeline_widgets(context):
    """Main draw callback for timeline widgets"""
    if not state.enabled:
        return
    
    # Verify we're in the right context
    if context.area is None or context.region is None:
        return
    
    # Only draw in WINDOW region (not channels sidebar)
    if context.region.type != 'WINDOW':
        return
    
    scene = context.scene
    region = context.region
    height = region.height
    
    # Get frame positions in region coordinates using View2D
    try:
        in_x = frame_to_region_x(region, scene.frame_start)
        out_x = frame_to_region_x(region, scene.frame_end)
    except Exception:
        # Fallback if view2d is not available
        return
    
    # Skip if handles would be outside visible region
    # (with some margin to allow partial visibility)
    margin = 50
    if in_x < -margin and out_x < -margin:
        return
    if in_x > region.width + margin and out_x > region.width + margin:
        return
    
    # Colors
    in_color_normal = (0.2, 0.85, 0.35, 0.8)     # Green
    in_color_hover = (0.3, 1.0, 0.45, 0.95)      # Bright green
    in_color_drag = (0.5, 1.0, 0.6, 1.0)         # Very bright green
    
    out_color_normal = (0.95, 0.25, 0.2, 0.8)    # Red
    out_color_hover = (1.0, 0.4, 0.35, 0.95)     # Bright red
    out_color_drag = (1.0, 0.6, 0.55, 1.0)       # Very bright red
    
    range_color = (0.4, 0.6, 0.9, 0.08)          # Light blue tint
    
    # Setup GPU state
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    
    # Draw range overlay between in and out
    draw_range_overlay(shader, in_x, out_x, height, range_color)
    
    # Choose colors based on state
    if state.is_dragging_in:
        in_color = in_color_drag
    elif state.hover_in:
        in_color = in_color_hover
    else:
        in_color = in_color_normal
    
    if state.is_dragging_out:
        out_color = out_color_drag
    elif state.hover_out:
        out_color = out_color_hover
    else:
        out_color = out_color_normal
    
    # Draw handles
    draw_handle_shape(shader, in_x, height, in_color, is_in_handle=True)
    draw_handle_shape(shader, out_x, height, out_color, is_in_handle=False)
    
    gpu.state.blend_set('NONE')
    
    # Draw labels when hovering or dragging
    if state.hover_in or state.is_dragging_in:
        draw_frame_label(in_x, height - 45, scene.frame_start, is_in=True)
    
    if state.hover_out or state.is_dragging_out:
        draw_frame_label(out_x, height - 45, scene.frame_end, is_in=False)


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
        return context.area is not None and context.region is not None
    
    def invoke(self, context, event):
        scene = context.scene
        region = context.region
        
        if region.type != 'WINDOW':
            return {'PASS_THROUGH'}
        
        mouse_x = event.mouse_region_x
        
        # Get handle positions
        try:
            in_x = frame_to_region_x(region, scene.frame_start)
            out_x = frame_to_region_x(region, scene.frame_end)
        except Exception:
            return {'PASS_THROUGH'}
        
        # Determine which handle to drag (20 pixel threshold)
        hit_threshold = 20
        
        dist_to_in = abs(mouse_x - in_x)
        dist_to_out = abs(mouse_x - out_x)
        
        if dist_to_in < hit_threshold and dist_to_in <= dist_to_out:
            self.handle_type = "in"
            self.initial_frame = scene.frame_start
            state.is_dragging_in = True
        elif dist_to_out < hit_threshold:
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
        region = context.region
        
        if event.type == 'MOUSEMOVE':
            try:
                new_frame = region_x_to_frame(region, event.mouse_region_x)
            except Exception:
                return {'RUNNING_MODAL'}
            
            if self.handle_type == "in":
                # Clamp: in frame can't exceed out frame
                new_frame = max(0, min(new_frame, scene.frame_end - 1))
                scene.frame_start = new_frame
            else:
                # Clamp: out frame can't go below in frame
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
            # Cancel: restore original frame
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
        
        # Redraw all areas
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        
        status = "enabled" if state.enabled else "disabled"
        self.report({'INFO'}, f"In/Out widgets {status}")
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Keymap and Event Handler
# -----------------------------------------------------------------------------

addon_keymaps = []


def update_hover_state(region, mouse_x, scene):
    """Update hover state based on mouse position"""
    try:
        in_x = frame_to_region_x(region, scene.frame_start)
        out_x = frame_to_region_x(region, scene.frame_end)
    except Exception:
        return False
    
    hit_threshold = 20
    
    old_hover_in = state.hover_in
    old_hover_out = state.hover_out
    
    dist_to_in = abs(mouse_x - in_x)
    dist_to_out = abs(mouse_x - out_x)
    
    state.hover_in = dist_to_in < hit_threshold and dist_to_in <= dist_to_out
    state.hover_out = dist_to_out < hit_threshold and not state.hover_in
    
    return old_hover_in != state.hover_in or old_hover_out != state.hover_out


# -----------------------------------------------------------------------------
# UI Menu Integration
# -----------------------------------------------------------------------------

def draw_menu_item(self, context):
    """Add toggle to View menu"""
    layout = self.layout
    layout.separator()
    icon = 'CHECKBOX_HLT' if state.enabled else 'CHECKBOX_DEHLT'
    layout.operator(TIMELINE_OT_toggle_io_widgets.bl_idname, 
                   text="In/Out Frame Handles", icon=icon)


# -----------------------------------------------------------------------------
# Draw Handler Manager
# -----------------------------------------------------------------------------

# Space types for animation editors
ANIMATION_SPACES = [
    'SpaceDopeSheetEditor',
    'SpaceGraphEditor', 
    'SpaceNLA',
    'SpaceSequenceEditor',
]

# View menus for each editor
VIEW_MENUS = [
    'DOPESHEET_MT_view',
    'GRAPH_MT_view',
    'NLA_MT_view',
    'SEQUENCER_MT_view',
]


classes = (
    TIMELINE_OT_drag_io_handle,
    TIMELINE_OT_toggle_io_widgets,
)


def register():
    # Register classes
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add draw handlers for each animation editor
    for space_name in ANIMATION_SPACES:
        space_type = getattr(bpy.types, space_name, None)
        if space_type is not None:
            handler = space_type.draw_handler_add(
                draw_timeline_widgets, (), 'WINDOW', 'POST_PIXEL'
            )
            state.draw_handlers[space_name] = (space_type, handler)
    
    # Add menu items to View menus
    for menu_name in VIEW_MENUS:
        menu_type = getattr(bpy.types, menu_name, None)
        if menu_type is not None:
            menu_type.append(draw_menu_item)
    
    # Setup keymap for dragging handles
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # Add to each animation editor keymap
        editor_keymaps = [
            'Dopesheet',
            'Graph Editor', 
            'NLA Editor',
            'Sequencer',
        ]
        for km_name in editor_keymaps:
            try:
                km = kc.keymaps.new(name=km_name, space_type='EMPTY')
                kmi = km.keymap_items.new(
                    TIMELINE_OT_drag_io_handle.bl_idname,
                    type='LEFTMOUSE',
                    value='PRESS'
                )
                addon_keymaps.append((km, kmi))
            except Exception:
                pass


def unregister():
    # Remove keymaps
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    addon_keymaps.clear()
    
    # Remove menu items
    for menu_name in VIEW_MENUS:
        menu_type = getattr(bpy.types, menu_name, None)
        if menu_type is not None:
            try:
                menu_type.remove(draw_menu_item)
            except ValueError:
                pass
    
    # Remove draw handlers
    for space_name, (space_type, handler) in state.draw_handlers.items():
        try:
            space_type.draw_handler_remove(handler, 'WINDOW')
        except ValueError:
            pass
    state.draw_handlers.clear()
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
