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
    """
    Convert a frame number to region x coordinate using View2D.
    """
    region = context.region
    
    # Access view2d - this is the correct way in Blender
    view2d = region.view2d
    
    # view_to_region converts view coords (frame, value) to pixel coords
    x, _ = view2d.view_to_region(float(frame), 0.0, clip=False)
    
    return x


def region_x_to_frame(context, x):
    """
    Convert region x coordinate to frame number using View2D.
    """
    region = context.region
    view2d = region.view2d
    
    # region_to_view converts pixel coords to view coords (frame, value)
    frame, _ = view2d.region_to_view(float(x), 0.0)
    
    return int(round(frame))


# -----------------------------------------------------------------------------
# Drawing Functions
# -----------------------------------------------------------------------------

def draw_vertical_line(shader, x, height, color, width=2):
    """Draw a vertical line"""
    half_w = width / 2
    vertices = [
        (x - half_w, 0),
        (x + half_w, 0),
        (x + half_w, height),
        (x - half_w, height),
    ]
    indices = [(0, 1, 2), (0, 2, 3)]
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.uniform_float("color", color)
    batch.draw(shader)


def draw_bracket(shader, x, height, color, is_left=True):
    """Draw a bracket shape [ or ]"""
    bracket_h = min(60, height * 0.4)
    bar_w = 6
    arm_len = 20
    
    vertices = []
    indices = []
    
    if is_left:
        # [ shape - vertical bar on left, arms extend right
        # Vertical bar
        vertices.extend([
            (x, 0), (x + bar_w, 0),
            (x + bar_w, bracket_h), (x, bracket_h),
        ])
        indices.extend([(0, 1, 2), (0, 2, 3)])
        
        # Top arm
        vertices.extend([
            (x, bracket_h - bar_w), (x + arm_len, bracket_h - bar_w),
            (x + arm_len, bracket_h), (x, bracket_h),
        ])
        indices.extend([(4, 5, 6), (4, 6, 7)])
        
        # Bottom arm  
        vertices.extend([
            (x, 0), (x + arm_len, 0),
            (x + arm_len, bar_w), (x, bar_w),
        ])
        indices.extend([(8, 9, 10), (8, 10, 11)])
    else:
        # ] shape - vertical bar on right, arms extend left
        # Vertical bar
        vertices.extend([
            (x - bar_w, 0), (x, 0),
            (x, bracket_h), (x - bar_w, bracket_h),
        ])
        indices.extend([(0, 1, 2), (0, 2, 3)])
        
        # Top arm
        vertices.extend([
            (x - arm_len, bracket_h - bar_w), (x, bracket_h - bar_w),
            (x, bracket_h), (x - arm_len, bracket_h),
        ])
        indices.extend([(4, 5, 6), (4, 6, 7)])
        
        # Bottom arm
        vertices.extend([
            (x - arm_len, 0), (x, 0),
            (x, bar_w), (x - arm_len, bar_w),
        ])
        indices.extend([(8, 9, 10), (8, 10, 11)])
    
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.uniform_float("color", color)
    batch.draw(shader)


def draw_triangle(shader, x, y, size, color, pointing_right=True):
    """Draw a triangle arrow"""
    if pointing_right:
        vertices = [
            (x, y - size),
            (x + size, y),
            (x, y + size),
        ]
    else:
        vertices = [
            (x, y - size),
            (x - size, y),
            (x, y + size),
        ]
    
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices})
    shader.uniform_float("color", color)
    batch.draw(shader)


def draw_label(x, y, text):
    """Draw a text label with background"""
    import blf
    
    font_id = 0
    blf.size(font_id, 12)
    
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
    shader.uniform_float("color", (0.0, 0.0, 0.0, 0.8))
    bg_batch.draw(shader)
    
    # Text
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, text)


def draw_timeline_widgets():
    """Main draw callback for timeline widgets"""
    if not state.enabled:
        return
    
    # Get context - we need to get it fresh each draw call
    context = bpy.context
    
    if context is None:
        return
    
    region = context.region
    if region is None:
        return
    
    # Make sure we have a scene
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
        # If conversion fails, skip drawing
        print(f"Timeline IO Widgets: Error converting coordinates: {e}")
        return
    
    # Check if handles are visible (with margin)
    margin = 100
    if in_x > width + margin and out_x > width + margin:
        return
    if in_x < -margin and out_x < -margin:
        return
    
    # Colors
    in_color_base = (0.2, 0.9, 0.3, 0.85)
    in_color_hover = (0.3, 1.0, 0.4, 1.0)
    in_color_drag = (0.5, 1.0, 0.55, 1.0)
    
    out_color_base = (1.0, 0.25, 0.2, 0.85)
    out_color_hover = (1.0, 0.4, 0.35, 1.0)
    out_color_drag = (1.0, 0.6, 0.55, 1.0)
    
    range_color = (0.5, 0.7, 1.0, 0.06)
    
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
    
    # Setup GPU state for drawing
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    
    # Draw range overlay
    if in_x < out_x:
        range_verts = [
            (in_x, 0), (out_x, 0),
            (out_x, height), (in_x, height),
        ]
        range_batch = batch_for_shader(shader, 'TRIS', {"pos": range_verts},
                                        indices=[(0, 1, 2), (0, 2, 3)])
        shader.uniform_float("color", range_color)
        range_batch.draw(shader)
    
    # Draw IN handle (green)
    draw_vertical_line(shader, in_x, height, in_color, width=3)
    draw_bracket(shader, in_x, height, in_color, is_left=True)
    draw_triangle(shader, in_x + 5, height - 30, 10, in_color, pointing_right=True)
    
    # Draw OUT handle (red)
    draw_vertical_line(shader, out_x, height, out_color, width=3)
    draw_bracket(shader, out_x, height, out_color, is_left=False)
    draw_triangle(shader, out_x - 5, height - 30, 10, out_color, pointing_right=False)
    
    gpu.state.blend_set('NONE')
    
    # Draw labels when hovering or dragging
    if state.hover_in or state.is_dragging_in:
        label_x = in_x + 15
        draw_label(label_x, height - 55, f"IN: {scene.frame_start}")
    
    if state.hover_out or state.is_dragging_out:
        # Position label to the left of handle
        import blf
        text = f"OUT: {scene.frame_end}"
        blf.size(0, 12)
        text_w, _ = blf.dimensions(0, text)
        label_x = out_x - text_w - 15
        draw_label(label_x, height - 55, text)


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
        
        # Get handle positions
        try:
            in_x = frame_to_region_x(context, scene.frame_start)
            out_x = frame_to_region_x(context, scene.frame_end)
        except Exception:
            return {'PASS_THROUGH'}
        
        # Check which handle was clicked (25 pixel threshold)
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
    
    # Add draw handlers
    for space_name in ANIMATION_SPACES:
        space_type = getattr(bpy.types, space_name, None)
        if space_type is not None:
            # Use a wrapper that doesn't require arguments
            handler = space_type.draw_handler_add(
                draw_timeline_widgets, (), 'WINDOW', 'POST_PIXEL'
            )
            state.draw_handlers[space_name] = (space_type, handler)
    
    # Add menu items
    for menu_name in VIEW_MENUS:
        menu_type = getattr(bpy.types, menu_name, None)
        if menu_type is not None:
            menu_type.append(draw_menu_item)
    
    # Setup keymaps
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
        except Exception:
            pass
    state.draw_handlers.clear()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
