# SPDX-License-Identifier: GPL-3.0-or-later
# Timeline In/Out Widgets - Blender 5.0 Extension
# Adds draggable in/out frame handles as overlays in animation editors

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector


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
# Drawing Functions
# -----------------------------------------------------------------------------

def get_view2d_from_region(context):
    """Get the View2D from the current region for coordinate conversion"""
    region = context.region
    # Access view2d through the region
    if hasattr(region, 'view2d'):
        return region.view2d
    return None


def frame_to_region_x(context, frame):
    """Convert a frame number to region x coordinate"""
    region = context.region
    view2d = get_view2d_from_region(context)
    
    if view2d is None:
        # Fallback calculation
        space = context.space_data
        if hasattr(space, 'view_start') and hasattr(space, 'view_end'):
            view_start = space.view_start
            view_end = space.view_end
        else:
            view_start = context.scene.frame_start - 10
            view_end = context.scene.frame_end + 10
        
        if view_end - view_start == 0:
            return 0
        
        normalized = (frame - view_start) / (view_end - view_start)
        return int(normalized * region.width)
    
    # Use view2d for accurate conversion
    x, _ = view2d.view_to_region(frame, 0, clip=False)
    return x


def region_x_to_frame(context, x):
    """Convert region x coordinate to frame number"""
    region = context.region
    view2d = get_view2d_from_region(context)
    
    if view2d is None:
        # Fallback calculation
        space = context.space_data
        if hasattr(space, 'view_start') and hasattr(space, 'view_end'):
            view_start = space.view_start
            view_end = space.view_end
        else:
            view_start = context.scene.frame_start - 10
            view_end = context.scene.frame_end + 10
        
        normalized = x / region.width
        return int(view_start + normalized * (view_end - view_start))
    
    # Use view2d for accurate conversion
    frame, _ = view2d.region_to_view(x, 0)
    return int(frame)


def draw_handle_shape(x, height, color, is_in_handle=True):
    """Draw a handle shape at the given x position"""
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Handle dimensions
    handle_width = 8
    handle_height = min(40, height * 0.4)
    triangle_size = 12
    
    vertices = []
    indices = []
    
    if is_in_handle:
        # In handle: bracket shape pointing right [ with triangle
        # Vertical bar
        vertices.extend([
            (x, 0),
            (x + handle_width, 0),
            (x + handle_width, handle_height),
            (x, handle_height),
        ])
        indices.extend([(0, 1, 2), (0, 2, 3)])
        
        # Top horizontal bar
        vertices.extend([
            (x, handle_height - handle_width),
            (x + handle_width * 2, handle_height - handle_width),
            (x + handle_width * 2, handle_height),
            (x, handle_height),
        ])
        indices.extend([(4, 5, 6), (4, 6, 7)])
        
        # Triangle pointer at top
        mid_y = height - 20
        vertices.extend([
            (x, mid_y - triangle_size),
            (x + triangle_size, mid_y),
            (x, mid_y + triangle_size),
        ])
        indices.append((8, 9, 10))
        
    else:
        # Out handle: bracket shape pointing left ] with triangle
        # Vertical bar
        vertices.extend([
            (x - handle_width, 0),
            (x, 0),
            (x, handle_height),
            (x - handle_width, handle_height),
        ])
        indices.extend([(0, 1, 2), (0, 2, 3)])
        
        # Top horizontal bar
        vertices.extend([
            (x - handle_width * 2, handle_height - handle_width),
            (x, handle_height - handle_width),
            (x, handle_height),
            (x - handle_width * 2, handle_height),
        ])
        indices.extend([(4, 5, 6), (4, 6, 7)])
        
        # Triangle pointer at top
        mid_y = height - 20
        vertices.extend([
            (x, mid_y - triangle_size),
            (x - triangle_size, mid_y),
            (x, mid_y + triangle_size),
        ])
        indices.append((8, 9, 10))
    
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    
    # Draw vertical line spanning full height
    line_vertices = [(x, 0), (x, height)]
    line_batch = batch_for_shader(shader, 'LINES', {"pos": line_vertices})
    line_batch.draw(shader)
    
    gpu.state.blend_set('NONE')


def draw_range_overlay(x_start, x_end, height, color):
    """Draw a semi-transparent overlay for the frame range"""
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    vertices = [
        (x_start, 0),
        (x_end, 0),
        (x_end, height),
        (x_start, height),
    ]
    indices = [(0, 1, 2), (0, 2, 3)]
    
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set('NONE')


def draw_frame_label(x, y, frame, is_in=True):
    """Draw frame number label"""
    import blf
    
    font_id = 0
    text = f"{'IN' if is_in else 'OUT'}: {frame}"
    
    blf.size(font_id, 11)
    blf.color(font_id, 1.0, 1.0, 1.0, 0.9)
    
    # Get text dimensions for background
    text_width, text_height = blf.dimensions(font_id, text)
    
    # Offset based on handle type
    if is_in:
        text_x = x + 15
    else:
        text_x = x - text_width - 15
    
    blf.position(font_id, text_x, y, 0)
    blf.draw(font_id, text)


def draw_timeline_widgets(context):
    """Main draw callback for timeline widgets"""
    if not state.enabled:
        return
    
    scene = context.scene
    region = context.region
    
    if region is None:
        return
    
    height = region.height
    
    # Get frame positions in region coordinates
    in_x = frame_to_region_x(context, scene.frame_start)
    out_x = frame_to_region_x(context, scene.frame_end)
    
    # Colors
    in_color_normal = (0.2, 0.8, 0.3, 0.7)      # Green
    in_color_hover = (0.3, 1.0, 0.4, 0.9)       # Bright green
    in_color_drag = (0.5, 1.0, 0.6, 1.0)        # Very bright green
    
    out_color_normal = (0.9, 0.3, 0.2, 0.7)     # Red
    out_color_hover = (1.0, 0.4, 0.3, 0.9)      # Bright red
    out_color_drag = (1.0, 0.6, 0.5, 1.0)       # Very bright red
    
    range_color = (0.5, 0.7, 1.0, 0.05)         # Light blue tint
    
    # Draw range overlay between in and out
    if in_x < out_x:
        draw_range_overlay(in_x, out_x, height, range_color)
    
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
    draw_handle_shape(in_x, height, in_color, is_in_handle=True)
    draw_handle_shape(out_x, height, out_color, is_in_handle=False)
    
    # Draw labels when hovering or dragging
    if state.hover_in or state.is_dragging_in:
        draw_frame_label(in_x, height - 50, scene.frame_start, is_in=True)
    
    if state.hover_out or state.is_dragging_out:
        draw_frame_label(out_x, height - 50, scene.frame_end, is_in=False)


# -----------------------------------------------------------------------------
# Modal Operator for Interaction
# -----------------------------------------------------------------------------

class TIMELINE_OT_drag_io_handles(bpy.types.Operator):
    """Drag the in/out frame handles"""
    bl_idname = "timeline.drag_io_handles"
    bl_label = "Drag In/Out Handles"
    bl_options = {'INTERNAL'}
    
    handle_type: bpy.props.StringProperty(default="")  # "in" or "out"
    initial_frame: bpy.props.IntProperty()
    initial_mouse_x: bpy.props.IntProperty()
    
    def invoke(self, context, event):
        scene = context.scene
        
        # Determine which handle is being dragged based on click position
        in_x = frame_to_region_x(context, scene.frame_start)
        out_x = frame_to_region_x(context, scene.frame_end)
        
        mouse_x = event.mouse_region_x
        
        # Check if clicking on in handle (within 20 pixels)
        if abs(mouse_x - in_x) < 20:
            self.handle_type = "in"
            self.initial_frame = scene.frame_start
            state.is_dragging_in = True
        # Check if clicking on out handle
        elif abs(mouse_x - out_x) < 20:
            self.handle_type = "out"
            self.initial_frame = scene.frame_end
            state.is_dragging_out = True
        else:
            return {'PASS_THROUGH'}
        
        self.initial_mouse_x = mouse_x
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        scene = context.scene
        
        if event.type == 'MOUSEMOVE':
            new_frame = region_x_to_frame(context, event.mouse_region_x)
            
            if self.handle_type == "in":
                # Ensure in frame doesn't exceed out frame
                new_frame = min(new_frame, scene.frame_end - 1)
                new_frame = max(new_frame, 0)
                scene.frame_start = new_frame
            else:
                # Ensure out frame doesn't go below in frame
                new_frame = max(new_frame, scene.frame_start + 1)
                scene.frame_end = new_frame
            
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            state.is_dragging_in = False
            state.is_dragging_out = False
            context.area.tag_redraw()
            return {'FINISHED'}
        
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            # Restore original frame
            if self.handle_type == "in":
                scene.frame_start = self.initial_frame
            else:
                scene.frame_end = self.initial_frame
            
            state.is_dragging_in = False
            state.is_dragging_out = False
            context.area.tag_redraw()
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}


class TIMELINE_OT_hover_check(bpy.types.Operator):
    """Check for hover state on handles (runs continuously)"""
    bl_idname = "timeline.hover_check"
    bl_label = "Check Handle Hover"
    bl_options = {'INTERNAL'}
    
    _timer = None
    
    def modal(self, context, event):
        if not state.enabled:
            return {'PASS_THROUGH'}
        
        if context.area is None:
            return {'PASS_THROUGH'}
        
        # Only process in animation editors
        if context.area.type not in {'DOPESHEET_EDITOR', 'GRAPH_EDITOR', 'NLA_EDITOR', 
                                      'SEQUENCE_EDITOR', 'TIMELINE'}:
            return {'PASS_THROUGH'}
        
        if event.type == 'MOUSEMOVE':
            scene = context.scene
            mouse_x = event.mouse_region_x
            
            in_x = frame_to_region_x(context, scene.frame_start)
            out_x = frame_to_region_x(context, scene.frame_end)
            
            old_hover_in = state.hover_in
            old_hover_out = state.hover_out
            
            state.hover_in = abs(mouse_x - in_x) < 20
            state.hover_out = abs(mouse_x - out_x) < 20
            
            # Redraw if hover state changed
            if old_hover_in != state.hover_in or old_hover_out != state.hover_out:
                context.area.tag_redraw()
            
            # Change cursor when hovering
            if state.hover_in or state.hover_out:
                context.window.cursor_set('MOVE_X')
            else:
                context.window.cursor_set('DEFAULT')
        
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if state.hover_in or state.hover_out:
                bpy.ops.timeline.drag_io_handles('INVOKE_DEFAULT')
                return {'RUNNING_MODAL'}
        
        return {'PASS_THROUGH'}
    
    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


# -----------------------------------------------------------------------------
# Toggle Operator
# -----------------------------------------------------------------------------

class TIMELINE_OT_toggle_io_widgets(bpy.types.Operator):
    """Toggle the In/Out frame widgets visibility"""
    bl_idname = "timeline.toggle_io_widgets"
    bl_label = "Toggle In/Out Widgets"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        state.enabled = not state.enabled
        
        # Redraw all animation areas
        for area in context.screen.areas:
            if area.type in {'DOPESHEET_EDITOR', 'GRAPH_EDITOR', 'NLA_EDITOR', 
                            'SEQUENCE_EDITOR', 'TIMELINE'}:
                area.tag_redraw()
        
        status = "enabled" if state.enabled else "disabled"
        self.report({'INFO'}, f"In/Out widgets {status}")
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# UI Menu Integration
# -----------------------------------------------------------------------------

def draw_menu_item(self, context):
    """Add toggle to View menu"""
    layout = self.layout
    layout.separator()
    layout.operator(
        TIMELINE_OT_toggle_io_widgets.bl_idname,
        text="In/Out Frame Handles",
        icon='CHECKBOX_HLT' if state.enabled else 'CHECKBOX_DEHLT'
    )


# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

# Editor types and their corresponding space types for draw handlers
ANIMATION_EDITORS = {
    'DOPESHEET_EDITOR': 'SpaceDopeSheetEditor',
    'GRAPH_EDITOR': 'SpaceGraphEditor',
    'NLA_EDITOR': 'SpaceNLA',
    'SEQUENCE_EDITOR': 'SpaceSequenceEditor',
}

# View menus to add our toggle to
VIEW_MENUS = [
    'DOPESHEET_MT_view',
    'GRAPH_MT_view',
    'NLA_MT_view',
    'SEQUENCER_MT_view',
]

classes = (
    TIMELINE_OT_drag_io_handles,
    TIMELINE_OT_hover_check,
    TIMELINE_OT_toggle_io_widgets,
)


def register():
    # Register classes
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add draw handlers for each animation editor
    for editor_type, space_name in ANIMATION_EDITORS.items():
        space_type = getattr(bpy.types, space_name, None)
        if space_type is not None:
            handler = space_type.draw_handler_add(
                draw_timeline_widgets, (), 'WINDOW', 'POST_PIXEL'
            )
            state.draw_handlers[editor_type] = (space_type, handler)
    
    # Add menu items
    for menu_name in VIEW_MENUS:
        menu_type = getattr(bpy.types, menu_name, None)
        if menu_type is not None:
            menu_type.append(draw_menu_item)
    
    # Register keymap for hover detection
    # This runs the hover check operator when entering animation editors
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        for editor_type in ANIMATION_EDITORS.keys():
            km = wm.keyconfigs.addon.keymaps.new(name='Window', space_type='EMPTY')
            kmi = km.keymap_items.new(
                TIMELINE_OT_hover_check.bl_idname,
                type='MOUSEMOVE',
                value='ANY'
            )


def unregister():
    # Remove draw handlers
    for editor_type, (space_type, handler) in state.draw_handlers.items():
        try:
            space_type.draw_handler_remove(handler, 'WINDOW')
        except ValueError:
            pass
    state.draw_handlers.clear()
    
    # Remove menu items
    for menu_name in VIEW_MENUS:
        menu_type = getattr(bpy.types, menu_name, None)
        if menu_type is not None:
            try:
                menu_type.remove(draw_menu_item)
            except ValueError:
                pass
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
