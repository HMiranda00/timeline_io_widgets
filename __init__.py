# SPDX-License-Identifier: GPL-3.0-or-later
# Timeline In/Out Widgets - Blender 5.0 Extension
# Adds draggable in/out frame handles as overlays in animation editors

import bpy
import gpu
import math
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
# Preferences
# -----------------------------------------------------------------------------

def get_prefs():
    """Get the addon preferences"""
    return bpy.context.preferences.addons[__package__].preferences


def get_editor_settings(context):
    """Get settings for the current editor, with per-editor override support"""
    prefs = get_prefs()
    
    # Map space types to editor settings
    space_type = context.area.type if context.area else None
    editor_map = {
        'DOPESHEET_EDITOR': 'dopesheet',
        'GRAPH_EDITOR': 'graph_editor',
        'NLA_EDITOR': 'nla_editor',
        'SEQUENCE_EDITOR': 'sequencer',
    }
    
    editor_key = editor_map.get(space_type)
    
    if editor_key and prefs.use_per_editor_settings:
        editor_settings = getattr(prefs, editor_key)
        if editor_settings.override:
            return editor_settings
    
    return prefs


class TimelineIOEditorSettings(bpy.types.PropertyGroup):
    """Per-editor override settings"""
    override: bpy.props.BoolProperty(
        name="Override Global Settings",
        description="Use custom settings for this editor",
        default=False
    )
    
    # Position
    bracket_position: bpy.props.EnumProperty(
        name="Bracket Position",
        items=[
            ('TOP', "Top", "Brackets at the top (below header)"),
            ('BOTTOM', "Bottom", "Brackets at the bottom"),
        ],
        default='TOP'
    )
    
    # Dimensions
    bracket_height: bpy.props.IntProperty(
        name="Bracket Height",
        description="Height of the bracket area",
        default=16, min=8, max=100
    )
    bracket_arm_length: bpy.props.IntProperty(
        name="Arm Length",
        description="Horizontal length of bracket arms",
        default=12, min=4, max=50
    )
    bracket_thickness: bpy.props.IntProperty(
        name="Bracket Thickness",
        description="Thickness of bracket lines",
        default=3, min=1, max=10
    )
    line_thickness: bpy.props.IntProperty(
        name="Line Thickness",
        description="Thickness of vertical lines and indicator",
        default=1, min=1, max=5
    )
    
    # Round corners
    use_round_corners: bpy.props.BoolProperty(
        name="Round Corners",
        description="Use rounded corners on brackets (high radius creates C-shape)",
        default=False
    )
    corner_radius: bpy.props.IntProperty(
        name="Corner Radius",
        description="Radius of rounded corners - high values create C-shaped brackets",
        default=3, min=1, max=50
    )
    
    # Colors
    in_color: bpy.props.FloatVectorProperty(
        name="In Point Color",
        subtype='COLOR_GAMMA',
        size=4,
        default=(0.3, 0.9, 0.4, 0.9),
        min=0.0, max=1.0
    )
    out_color: bpy.props.FloatVectorProperty(
        name="Out Point Color",
        subtype='COLOR_GAMMA',
        size=4,
        default=(1.0, 0.35, 0.3, 0.9),
        min=0.0, max=1.0
    )
    range_color: bpy.props.FloatVectorProperty(
        name="Range Overlay Color",
        subtype='COLOR_GAMMA',
        size=4,
        default=(0.4, 0.55, 0.8, 0.15),
        min=0.0, max=1.0
    )


class TimelineIOPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    
    # Global enable
    enabled: bpy.props.BoolProperty(
        name="Enable Widgets",
        description="Show In/Out frame widgets",
        default=True
    )
    
    # Per-editor settings toggle
    use_per_editor_settings: bpy.props.BoolProperty(
        name="Per-Editor Settings",
        description="Allow different settings for each editor type",
        default=False
    )
    
    # === Global Settings ===
    
    # Position
    bracket_position: bpy.props.EnumProperty(
        name="Bracket Position",
        items=[
            ('TOP', "Top", "Brackets at the top (below header)"),
            ('BOTTOM', "Bottom", "Brackets at the bottom"),
        ],
        default='TOP'
    )
    
    # Dimensions
    bracket_height: bpy.props.IntProperty(
        name="Bracket Height",
        description="Height of the bracket area",
        default=16, min=8, max=100
    )
    bracket_arm_length: bpy.props.IntProperty(
        name="Arm Length",
        description="Horizontal length of bracket arms",
        default=12, min=4, max=50
    )
    bracket_thickness: bpy.props.IntProperty(
        name="Bracket Thickness",
        description="Thickness of bracket lines",
        default=3, min=1, max=10
    )
    line_thickness: bpy.props.IntProperty(
        name="Line Thickness",
        description="Thickness of vertical lines and indicator",
        default=1, min=1, max=5
    )
    
    # Round corners
    use_round_corners: bpy.props.BoolProperty(
        name="Round Corners",
        description="Use rounded corners on brackets (high radius creates C-shape)",
        default=False
    )
    corner_radius: bpy.props.IntProperty(
        name="Corner Radius",
        description="Radius of rounded corners - high values create C-shaped brackets",
        default=3, min=1, max=50
    )
    
    # Colors
    in_color: bpy.props.FloatVectorProperty(
        name="In Point Color",
        subtype='COLOR_GAMMA',
        size=4,
        default=(0.3, 0.9, 0.4, 0.9),
        min=0.0, max=1.0
    )
    out_color: bpy.props.FloatVectorProperty(
        name="Out Point Color",
        subtype='COLOR_GAMMA',
        size=4,
        default=(1.0, 0.35, 0.3, 0.9),
        min=0.0, max=1.0
    )
    range_color: bpy.props.FloatVectorProperty(
        name="Range Overlay Color",
        subtype='COLOR_GAMMA',
        size=4,
        default=(0.4, 0.55, 0.8, 0.15),
        min=0.0, max=1.0
    )
    
    # Per-editor settings
    dopesheet: bpy.props.PointerProperty(type=TimelineIOEditorSettings)
    graph_editor: bpy.props.PointerProperty(type=TimelineIOEditorSettings)
    nla_editor: bpy.props.PointerProperty(type=TimelineIOEditorSettings)
    sequencer: bpy.props.PointerProperty(type=TimelineIOEditorSettings)
    
    def draw(self, context):
        layout = self.layout
        
        # Main toggle
        layout.prop(self, "enabled", text="Enable In/Out Widgets")
        
        if not self.enabled:
            return
        
        layout.separator()
        
        # Global settings
        box = layout.box()
        box.label(text="Global Settings", icon='PREFERENCES')
        
        # Position
        row = box.row()
        row.prop(self, "bracket_position", expand=True)
        
        # Dimensions
        col = box.column(align=True)
        col.prop(self, "bracket_height")
        col.prop(self, "bracket_arm_length")
        
        row = box.row(align=True)
        row.prop(self, "bracket_thickness")
        row.prop(self, "line_thickness")
        
        # Round corners
        box.separator()
        row = box.row()
        row.prop(self, "use_round_corners")
        sub = row.row()
        sub.enabled = self.use_round_corners
        sub.prop(self, "corner_radius")
        
        # Colors
        box.separator()
        box.label(text="Colors:")
        row = box.row()
        row.prop(self, "in_color", text="In")
        row.prop(self, "out_color", text="Out")
        box.prop(self, "range_color", text="Range")
        
        # Per-editor settings
        layout.separator()
        layout.prop(self, "use_per_editor_settings")
        
        if self.use_per_editor_settings:
            self.draw_editor_settings(layout, "Dope Sheet", self.dopesheet)
            self.draw_editor_settings(layout, "Graph Editor", self.graph_editor)
            self.draw_editor_settings(layout, "NLA Editor", self.nla_editor)
            self.draw_editor_settings(layout, "Sequencer", self.sequencer)
    
    def draw_editor_settings(self, layout, name, settings):
        box = layout.box()
        row = box.row()
        row.prop(settings, "override", text=name)
        
        if settings.override:
            col = box.column()
            col.prop(settings, "bracket_position")
            
            row = col.row(align=True)
            row.prop(settings, "bracket_height")
            row.prop(settings, "bracket_arm_length")
            
            row = col.row(align=True)
            row.prop(settings, "bracket_thickness")
            row.prop(settings, "line_thickness")
            
            row = col.row()
            row.prop(settings, "use_round_corners")
            sub = row.row()
            sub.enabled = settings.use_round_corners
            sub.prop(settings, "corner_radius")
            
            row = col.row()
            row.prop(settings, "in_color", text="In")
            row.prop(settings, "out_color", text="Out")
            col.prop(settings, "range_color", text="Range")


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
# Drawing Functions
# -----------------------------------------------------------------------------

HEADER_HEIGHT = 18  # Height of timeline header (constant)


def generate_arc_vertices(cx, cy, radius, start_angle, end_angle, segments=8):
    """Generate vertices for an arc"""
    vertices = []
    for i in range(segments + 1):
        t = i / segments
        angle = start_angle + t * (end_angle - start_angle)
        vx = cx + radius * math.cos(angle)
        vy = cy + radius * math.sin(angle)
        vertices.append((vx, vy))
    return vertices


def generate_bracket_vertices(x, y, width, height, thickness, radius, is_left=True, segments=8):
    """
    Generate vertices for a bracket shape "[" or "]" as a single continuous form.
    With high radius, the bracket becomes a "C" shape.
    
    For "[" bracket (is_left=True):
    - x, y is the inner corner position
    - Arms extend to the right
    - The vertical bar is on the left
    
    For "]" bracket (is_left=False):
    - x, y is the inner corner position  
    - Arms extend to the left
    - The vertical bar is on the right
    """
    vertices = []
    
    # Clamp radius to reasonable values
    max_radius = min(height / 2, width, thickness * 2)
    radius = min(radius, max_radius)
    
    if is_left:
        # "[" bracket - vertical bar on left, arms extend right
        # Outer edge (left side of vertical bar)
        outer_x = x - thickness
        inner_x = x
        arm_end_x = x + width - thickness
        
        bottom_y = y
        top_y = y + height
        
        # Start from bottom-left outer corner, go clockwise
        
        # Bottom-left outer corner (can be rounded)
        if radius > 0:
            arc = generate_arc_vertices(outer_x + radius, bottom_y + radius, 
                                        radius, math.pi, 1.5 * math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((outer_x, bottom_y))
        
        # Bottom arm - outer edge (bottom of bottom arm)
        vertices.append((arm_end_x, bottom_y))
        
        # Bottom arm - right end (can be rounded)
        if radius > 0:
            arc = generate_arc_vertices(arm_end_x, bottom_y + thickness - radius,
                                        radius, -0.5 * math.pi, 0, segments)
            vertices.extend(arc)
            arc = generate_arc_vertices(arm_end_x, bottom_y + thickness - radius,
                                        radius, 0, 0.5 * math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((arm_end_x + thickness, bottom_y))
            vertices.append((arm_end_x + thickness, bottom_y + thickness))
        
        # Bottom arm - inner edge (top of bottom arm)
        vertices.append((arm_end_x, bottom_y + thickness))
        
        # Inner corner - bottom (the curve that can make it a "C")
        if radius > 0:
            arc = generate_arc_vertices(inner_x + radius, bottom_y + thickness + radius,
                                        radius, 1.5 * math.pi, math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((inner_x, bottom_y + thickness))
        
        # Inner vertical edge
        inner_bottom = bottom_y + thickness + radius
        inner_top = top_y - thickness - radius
        
        if inner_top > inner_bottom:
            vertices.append((inner_x, inner_top))
        
        # Inner corner - top (the curve that can make it a "C")
        if radius > 0:
            arc = generate_arc_vertices(inner_x + radius, top_y - thickness - radius,
                                        radius, math.pi, 0.5 * math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((inner_x, top_y - thickness))
        
        # Top arm - inner edge (bottom of top arm)
        vertices.append((arm_end_x, top_y - thickness))
        
        # Top arm - right end (can be rounded)
        if radius > 0:
            arc = generate_arc_vertices(arm_end_x, top_y - thickness + radius,
                                        radius, -0.5 * math.pi, 0, segments)
            vertices.extend(arc)
            arc = generate_arc_vertices(arm_end_x, top_y - thickness + radius,
                                        radius, 0, 0.5 * math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((arm_end_x + thickness, top_y - thickness))
            vertices.append((arm_end_x + thickness, top_y))
        
        # Top arm - outer edge (top of top arm)
        vertices.append((arm_end_x, top_y))
        
        # Top-left outer corner (can be rounded)
        if radius > 0:
            arc = generate_arc_vertices(outer_x + radius, top_y - radius,
                                        radius, 0.5 * math.pi, math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((outer_x, top_y))
        
        # Back to start (left edge)
        # vertices.append((outer_x, bottom_y))  # Close the loop
        
    else:
        # "]" bracket - vertical bar on right, arms extend left
        outer_x = x + thickness
        inner_x = x
        arm_end_x = x - width + thickness
        
        bottom_y = y
        top_y = y + height
        
        # Start from bottom-right outer corner, go counter-clockwise
        
        # Bottom-right outer corner
        if radius > 0:
            arc = generate_arc_vertices(outer_x - radius, bottom_y + radius,
                                        radius, 1.5 * math.pi, 2 * math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((outer_x, bottom_y))
        
        # Right edge going up
        if radius > 0:
            arc = generate_arc_vertices(outer_x - radius, top_y - radius,
                                        radius, 0, 0.5 * math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((outer_x, top_y))
        
        # Top arm - outer edge
        vertices.append((arm_end_x, top_y))
        
        # Top arm - left end
        if radius > 0:
            arc = generate_arc_vertices(arm_end_x, top_y - thickness + radius,
                                        radius, 0.5 * math.pi, math.pi, segments)
            vertices.extend(arc)
            arc = generate_arc_vertices(arm_end_x, top_y - thickness + radius,
                                        radius, math.pi, 1.5 * math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((arm_end_x - thickness, top_y))
            vertices.append((arm_end_x - thickness, top_y - thickness))
        
        # Top arm - inner edge
        vertices.append((arm_end_x, top_y - thickness))
        
        # Inner corner - top
        if radius > 0:
            arc = generate_arc_vertices(inner_x - radius, top_y - thickness - radius,
                                        radius, 0.5 * math.pi, 0, segments)
            vertices.extend(arc)
        else:
            vertices.append((inner_x, top_y - thickness))
        
        # Inner vertical edge
        inner_top = top_y - thickness - radius
        inner_bottom = bottom_y + thickness + radius
        
        if inner_top > inner_bottom:
            vertices.append((inner_x, inner_bottom))
        
        # Inner corner - bottom
        if radius > 0:
            arc = generate_arc_vertices(inner_x - radius, bottom_y + thickness + radius,
                                        radius, 0, -0.5 * math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((inner_x, bottom_y + thickness))
        
        # Bottom arm - inner edge
        vertices.append((arm_end_x, bottom_y + thickness))
        
        # Bottom arm - left end
        if radius > 0:
            arc = generate_arc_vertices(arm_end_x, bottom_y + thickness - radius,
                                        radius, 0.5 * math.pi, math.pi, segments)
            vertices.extend(arc)
            arc = generate_arc_vertices(arm_end_x, bottom_y + thickness - radius,
                                        radius, math.pi, 1.5 * math.pi, segments)
            vertices.extend(arc)
        else:
            vertices.append((arm_end_x - thickness, bottom_y + thickness))
            vertices.append((arm_end_x - thickness, bottom_y))
        
        # Bottom arm - outer edge
        vertices.append((arm_end_x, bottom_y))
    
    # Generate indices using triangle fan from centroid
    if len(vertices) < 3:
        return [], []
    
    # Calculate centroid
    cx = sum(v[0] for v in vertices) / len(vertices)
    cy = sum(v[1] for v in vertices) / len(vertices)
    
    # Insert centroid at beginning
    vertices.insert(0, (cx, cy))
    
    # Create triangle fan
    indices = []
    num_verts = len(vertices)
    for i in range(1, num_verts - 1):
        indices.append((0, i, i + 1))
    indices.append((0, num_verts - 1, 1))
    
    return vertices, indices


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


def draw_bracket(shader, x, y, width, height, thickness, color, radius=0, is_left=True):
    """Draw a bracket shape with optional rounded corners"""
    vertices, indices = generate_bracket_vertices(x, y, width, height, thickness, radius, is_left)
    
    if vertices and indices:
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
        shader.uniform_float("color", color)
        batch.draw(shader)


def draw_handle(shader, x, region_height, color, settings, is_in_handle=True):
    """Draw a complete handle with bracket and lines"""
    line_w = settings.line_thickness
    bracket_w = settings.bracket_thickness
    bracket_h = settings.bracket_height
    arm_len = settings.bracket_arm_length
    half_line = line_w / 2
    
    use_rounded = settings.use_round_corners
    radius = settings.corner_radius if use_rounded else 0
    
    # Determine bracket position
    if settings.bracket_position == 'TOP':
        header_bottom = region_height - HEADER_HEIGHT
        bracket_top = header_bottom
        bracket_bottom = header_bottom - bracket_h
        line_bottom = 0
        line_top = bracket_bottom
    else:  # BOTTOM
        bracket_bottom = 0
        bracket_top = bracket_h
        line_bottom = bracket_top
        line_top = region_height - HEADER_HEIGHT
    
    # 1. Draw small indicator in header area
    indicator_size = max(line_w, 4)
    indicator_y = region_height - indicator_size - 2
    draw_rect(shader, x - half_line, indicator_y, line_w, indicator_size, color)
    
    # 2. Draw main vertical line
    draw_rect(shader, x - half_line, line_bottom, line_w, line_top - line_bottom, color)
    
    # 3. Draw bracket as a single unified shape
    if is_in_handle:
        # "[" bracket - positioned so inner edge is at x
        bracket_x = x  # Inner edge position
        draw_bracket(shader, bracket_x, bracket_bottom, arm_len + bracket_w, bracket_h, 
                    bracket_w, color, radius, is_left=True)
    else:
        # "]" bracket - positioned so inner edge is at x
        bracket_x = x  # Inner edge position
        draw_bracket(shader, bracket_x, bracket_bottom, arm_len + bracket_w, bracket_h,
                    bracket_w, color, radius, is_left=False)


def draw_rounded_rect(shader, x, y, width, height, color, radius=0, segments=6):
    """Draw a filled rectangle with optional rounded corners"""
    if radius <= 0 or radius * 2 > min(width, height):
        draw_rect(shader, x, y, width, height, color)
        return
    
    vertices = []
    
    # Generate corners
    corners = [
        (x + radius, y + radius, math.pi, 1.5 * math.pi),
        (x + width - radius, y + radius, 1.5 * math.pi, 2 * math.pi),
        (x + width - radius, y + height - radius, 0, 0.5 * math.pi),
        (x + radius, y + height - radius, 0.5 * math.pi, math.pi),
    ]
    
    for cx, cy, start_angle, end_angle in corners:
        arc = generate_arc_vertices(cx, cy, radius, start_angle, end_angle, segments)
        vertices.extend(arc)
    
    # Triangle fan from center
    cx = x + width / 2
    cy = y + height / 2
    vertices.insert(0, (cx, cy))
    
    indices = []
    num_verts = len(vertices)
    for i in range(1, num_verts - 1):
        indices.append((0, i, i + 1))
    indices.append((0, num_verts - 1, 1))
    
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.uniform_float("color", color)
    batch.draw(shader)


def draw_range_overlay(shader, in_x, out_x, region_height, color, settings):
    """Draw the highlighted range area between brackets"""
    if in_x >= out_x:
        return
    
    bracket_h = settings.bracket_height
    bracket_w = settings.bracket_thickness
    
    if settings.bracket_position == 'TOP':
        header_bottom = region_height - HEADER_HEIGHT
        bracket_bottom = header_bottom - bracket_h
    else:
        bracket_bottom = 0
    
    padding = bracket_w
    use_rounded = settings.use_round_corners
    radius = settings.corner_radius if use_rounded else 0
    
    draw_rounded_rect(shader,
                      in_x + padding,
                      bracket_bottom + padding,
                      out_x - in_x - padding * 2,
                      bracket_h - padding * 2,
                      color,
                      radius=radius)


def draw_label(x, y, text):
    """Draw a text label with background"""
    import blf
    
    font_id = 0
    blf.size(font_id, 11)
    
    text_w, text_h = blf.dimensions(font_id, text)
    padding = 4
    
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
    
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, text)


def brighten_color(color, factor=0.15):
    """Brighten a color for hover/drag states"""
    return tuple(min(1.0, c + factor) for c in color[:3]) + (min(1.0, color[3] + 0.1),)


def draw_timeline_widgets():
    """Main draw callback for timeline widgets"""
    context = bpy.context
    
    if context is None:
        return
    
    try:
        prefs = get_prefs()
        if not prefs.enabled:
            return
    except Exception:
        return
    
    if not state.enabled:
        return
    
    region = context.region
    if region is None:
        return
    
    scene = context.scene
    if scene is None:
        return
    
    # Get settings (global or per-editor)
    try:
        settings = get_editor_settings(context)
    except Exception:
        return
    
    height = region.height
    width = region.width
    
    # Convert frame positions to region coordinates
    try:
        in_x = frame_to_region_x(context, scene.frame_start)
        out_x = frame_to_region_x(context, scene.frame_end)
    except Exception:
        return
    
    # Check visibility
    margin = 100
    if in_x > width + margin and out_x > width + margin:
        return
    if in_x < -margin and out_x < -margin:
        return
    
    # Get colors from settings
    in_color_base = tuple(settings.in_color)
    out_color_base = tuple(settings.out_color)
    range_color = tuple(settings.range_color)
    
    # Apply hover/drag brightness
    if state.is_dragging_in:
        in_color = brighten_color(in_color_base, 0.2)
    elif state.hover_in:
        in_color = brighten_color(in_color_base, 0.1)
    else:
        in_color = in_color_base
    
    if state.is_dragging_out:
        out_color = brighten_color(out_color_base, 0.2)
    elif state.hover_out:
        out_color = brighten_color(out_color_base, 0.1)
    else:
        out_color = out_color_base
    
    # Setup GPU state
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    
    # Draw range overlay
    draw_range_overlay(shader, in_x, out_x, height, range_color, settings)
    
    # Draw handles
    draw_handle(shader, in_x, height, in_color, settings, is_in_handle=True)
    draw_handle(shader, out_x, height, out_color, settings, is_in_handle=False)
    
    gpu.state.blend_set('NONE')
    
    # Draw labels when hovering or dragging
    bracket_h = settings.bracket_height
    if settings.bracket_position == 'TOP':
        label_y = height - HEADER_HEIGHT - bracket_h - 18
    else:
        label_y = bracket_h + 8
    
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

HANDLE_HIT_THRESHOLD = 25


def check_handle_hover(context, mouse_x):
    """Check if mouse is hovering over a handle"""
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
        
        mouse_x = event.mouse_region_x
        mouse_y = event.mouse_region_y
        
        if not (0 <= mouse_x <= context.region.width and
                0 <= mouse_y <= context.region.height):
            if state.hover_in or state.hover_out:
                state.hover_in = False
                state.hover_out = False
                context.window.cursor_set('DEFAULT')
                context.area.tag_redraw()
            return {'PASS_THROUGH'}
        
        handle = check_handle_hover(context, mouse_x)
        
        old_hover_in = state.hover_in
        old_hover_out = state.hover_out
        
        state.hover_in = (handle == "in")
        state.hover_out = (handle == "out")
        
        if handle is not None:
            context.window.cursor_set('SCROLL_X')
        else:
            context.window.cursor_set('DEFAULT')
        
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

classes = (
    TimelineIOEditorSettings,
    TimelineIOPreferences,
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
