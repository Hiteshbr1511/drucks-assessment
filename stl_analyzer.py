"""
Drucks Technical Assessment
Author: [Your Name]
Date: April 2025
Tasks: 1 (Volume), 2 (Bounding Box + Layer Count), 3 (Print Time Estimate)

AI Tool used: Claude (Anthropic) - full conversation submitted as PDF
"""

import struct   # reads binary files - built into Python, no install needed
import math     # math functions - built into Python
import sys      # command line arguments - built into Python


# =============================================================================
# STEP A: PARSE THE STL FILE
# =============================================================================
# An STL file describes a 3D shape as a list of triangles.
# Each triangle has 3 corners (vertices), each corner is a point (x, y, z).
#
# STL comes in 2 formats:
#   BINARY: compact bytes (most common, what we'll likely get)
#   ASCII:  human readable text
#
# We auto-detect which one it is.
# =============================================================================

def parse_stl(filepath):
    """
    Opens the STL file and returns a list of triangles.
    Each triangle = ( (x1,y1,z1), (x2,y2,z2), (x3,y3,z3) )
    """
    with open(filepath, 'rb') as f:
        first5 = f.read(5)

    # ASCII files start with the word "solid"
    if first5 == b'solid':
        try:
            return _parse_ascii(filepath)
        except:
            return _parse_binary(filepath)
    else:
        return _parse_binary(filepath)


def _parse_binary(filepath):
    """
    Binary STL layout:
      80 bytes  = header (we skip it, it's just a label)
       4 bytes  = number of triangles (stored as uint32)
      
      Then for EACH triangle (50 bytes per triangle):
        12 bytes = normal vector  (3 floats) -- we ignore this
        12 bytes = vertex 1       (3 floats: x, y, z)
        12 bytes = vertex 2       (3 floats: x, y, z)
        12 bytes = vertex 3       (3 floats: x, y, z)
         2 bytes = attribute      -- we ignore this
    
    struct.unpack explanation:
      '<'  = little-endian (byte order standard for STL files)
      'I'  = unsigned 32-bit integer
      'f'  = 32-bit float
      'fff'= three floats = one (x, y, z) point
    """
    triangles = []

    with open(filepath, 'rb') as f:
        f.read(80)  # skip header

        # read how many triangles are in the file
        count_bytes = f.read(4)
        num_triangles = struct.unpack('<I', count_bytes)[0]

        print(f"[Parser] Binary STL | Triangles: {num_triangles:,}")

        for _ in range(num_triangles):
            f.read(12)  # skip normal vector (we don't need it)

            # read 3 vertices
            v1 = struct.unpack('<fff', f.read(12))
            v2 = struct.unpack('<fff', f.read(12))
            v3 = struct.unpack('<fff', f.read(12))

            f.read(2)   # skip attribute bytes

            triangles.append((v1, v2, v3))

    return triangles


def _parse_ascii(filepath):
    """
    ASCII STL looks like:
        solid myshoe
          facet normal 0 0 1
            outer loop
              vertex 1.0 2.0 3.0
              vertex 4.0 5.0 6.0
              vertex 7.0 8.0 9.0
            endloop
          endfacet
        endsolid myshoe
    
    We just look for lines starting with 'vertex' and grab x, y, z.
    Every 3 vertices = 1 triangle.
    """
    triangles = []
    verts = []

    with open(filepath, 'r', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if line.startswith('vertex'):
                parts = line.split()
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                verts.append((x, y, z))
                if len(verts) == 3:
                    triangles.append(tuple(verts))
                    verts = []

    print(f"[Parser] ASCII STL | Triangles: {len(triangles):,}")
    return triangles


# =============================================================================
# TASK 1: VOLUME - Signed Tetrahedra Method
# =============================================================================
#
# HOW IT WORKS (understand this for the interview call):
#
# Imagine you pick a point - let's use the ORIGIN (0, 0, 0).
# For every triangle on the mesh surface, connect all 3 corners
# to the origin. This forms a TETRAHEDRON (4-sided pyramid).
#
# The signed volume of that tetrahedron is:
#
#   V = (v1 · (v2 × v3)) / 6
#
#   v2 × v3  = cross product  → vector perpendicular to the triangle
#   v1 · ... = dot product    → scalar measuring depth/projection
#   ÷ 6      = tetrahedron volume formula (1/3 base × height, simplified)
#
# WHY "SIGNED"?
# Triangles pointing OUTWARD → positive volume
# Triangles pointing INWARD  → negative volume
#
# When you ADD all signed volumes of a closed mesh:
#   - Tetrahedra inside the shape ADD UP
#   - Tetrahedra outside CANCEL OUT
#   - Result = exact volume of the mesh
#
# Only works for CLOSED (watertight) meshes with no holes.
# =============================================================================

def _tet_signed_volume(v1, v2, v3):
    """
    Computes signed volume of tetrahedron: origin + triangle (v1, v2, v3)
    
    Formula: V = (v1 · (v2 × v3)) / 6
    
    Step 1: Cross product v2 × v3
      cx = v2.y*v3.z - v2.z*v3.y
      cy = v2.z*v3.x - v2.x*v3.z
      cz = v2.x*v3.y - v2.y*v3.x
    
    Step 2: Dot product v1 · (cx, cy, cz)
      dot = v1.x*cx + v1.y*cy + v1.z*cz
    
    Step 3: Divide by 6
    """
    # cross product: v2 × v3
    cx = v2[1]*v3[2] - v2[2]*v3[1]
    cy = v2[2]*v3[0] - v2[0]*v3[2]
    cz = v2[0]*v3[1] - v2[1]*v3[0]

    # dot product: v1 · cross
    dot = v1[0]*cx + v1[1]*cy + v1[2]*cz

    return dot / 6.0


def compute_volume(triangles):
    """
    Sums signed tetrahedron volumes for ALL triangles.
    Takes abs() at the end because sign depends on mesh winding order.
    """
    total = 0.0
    for (v1, v2, v3) in triangles:
        total += _tet_signed_volume(v1, v2, v3)
    return abs(total)


# =============================================================================
# TASK 2: BOUNDING BOX + LAYER COUNT
# =============================================================================
#
# BOUNDING BOX:
# Scan every vertex. Track the smallest and largest x, y, z values.
# This gives a rectangular box that wraps the entire model.
#
# LAYER COUNT:
# Slicers cut the model into horizontal slices from bottom to top.
# Number of slices = floor(total_height / layer_height)
# floor() = round DOWN (we don't print partial top layers)
# =============================================================================

def compute_bounding_box(triangles):
    """
    Finds min/max X, Y, Z across all vertices.
    Returns: (min_x, min_y, min_z, max_x, max_y, max_z)
    """
    min_x = min_y = min_z =  float('inf')   # start at +infinity, shrink down
    max_x = max_y = max_z =  float('-inf')  # start at -infinity, grow up

    for (v1, v2, v3) in triangles:
        for (x, y, z) in (v1, v2, v3):
            if x < min_x: min_x = x
            if y < min_y: min_y = y
            if z < min_z: min_z = z
            if x > max_x: max_x = x
            if y > max_y: max_y = y
            if z > max_z: max_z = z

    return min_x, min_y, min_z, max_x, max_y, max_z


def compute_layer_count(min_z, max_z, layer_height=0.2):
    """
    height = max_z - min_z
    layers = floor(height / layer_height)
    
    math.floor() rounds DOWN.
    Example: 123.7mm / 0.2mm = 618.5 → 618 complete layers
    """
    height = max_z - min_z
    layers = math.floor(height / layer_height)
    return height, layers


# =============================================================================
# TASK 3: PRINT TIME ESTIMATION
# =============================================================================
#
# SETTINGS GIVEN:
#   Print speed:  60 mm/s
#   Layer height: 0.2 mm
#   Walls only, no infill (hollow shell)
#   1 perimeter wall
#
# APPROACH:
# The nozzle traces the OUTLINE (perimeter) of the shoe at each layer.
# 
# For each layer Z height:
#   1. Find which triangles cross that Z plane
#   2. Compute where each triangle edge intersects the plane → gives (x,y) points
#   3. Each triangle gives a small line segment in the cross-section
#   4. Sum all segment lengths = perimeter of that layer
#
# Total path = sum of all layer perimeters
# Print time = total path / print speed
#
# LIMITATIONS (be honest about these):
#   - Ignores travel moves (nozzle moving without printing)
#   - Ignores acceleration/deceleration
#   - Ignores layer start/end overhead
#   - May over-count at edges where triangles share a point on the plane
# =============================================================================

def _edge_plane_intersect(v1, v2, z_plane):
    """
    Finds where a 3D edge (v1 to v2) intersects a horizontal plane at z=z_plane.
    
    If both vertices are on the same side of the plane → no intersection → None
    
    Otherwise, use LINEAR INTERPOLATION:
      t = how far along the edge the intersection is (0=at v1, 1=at v2)
      t = (z_plane - v1.z) / (v2.z - v1.z)
      
      intersection x = v1.x + t * (v2.x - v1.x)
      intersection y = v1.y + t * (v2.y - v1.y)
    """
    z1, z2 = v1[2], v2[2]

    # Same side check
    if (z1 < z_plane and z2 < z_plane) or (z1 > z_plane and z2 > z_plane):
        return None

    # Avoid divide by zero (edge is horizontal, parallel to plane)
    if abs(z2 - z1) < 1e-10:
        return None

    t = (z_plane - z1) / (z2 - z1)
    x = v1[0] + t * (v2[0] - v1[0])
    y = v1[1] + t * (v2[1] - v1[1])
    return (x, y)


def _layer_perimeter(triangles, z_plane):
    """
    Slices the mesh at z_plane.
    Returns total length of all cross-section segments.
    
    Each triangle contributes at most ONE segment (2 intersection points).
    We compute the length of that segment using Pythagorean theorem:
      length = sqrt( (x2-x1)² + (y2-y1)² )
    """
    total_length = 0.0

    for (v1, v2, v3) in triangles:
        pts = []
        for (a, b) in [(v1,v2), (v2,v3), (v3,v1)]:
            pt = _edge_plane_intersect(a, b, z_plane)
            if pt is not None:
                # avoid duplicate points
                if not any(abs(pt[0]-p[0])<1e-6 and abs(pt[1]-p[1])<1e-6 for p in pts):
                    pts.append(pt)

        if len(pts) == 2:
            dx = pts[1][0] - pts[0][0]
            dy = pts[1][1] - pts[0][1]
            total_length += math.sqrt(dx*dx + dy*dy)

    return total_length


def compute_print_time(triangles, min_z, max_z,
                       layer_height=0.2, print_speed=60.0):
    """
    Estimates print time by summing perimeters at every layer.
    
    Formula:
      total_path = Σ perimeter(z_i)   for all layers i
      print_time = total_path / print_speed
    
    z_i = min_z + (i + 0.5) * layer_height   ← center of layer i
    """
    num_layers = math.floor((max_z - min_z) / layer_height)
    print(f"\n[Task 3] Slicing {num_layers} layers... (this takes a minute)")

    total_path = 0.0

    for i in range(num_layers):
        z = min_z + (i + 0.5) * layer_height
        total_path += _layer_perimeter(triangles, z)

        # show progress every 50 layers
        if (i + 1) % 50 == 0:
            pct = (i + 1) / num_layers * 100
            print(f"         {i+1}/{num_layers} layers done ({pct:.0f}%)")

    t_seconds = total_path / print_speed
    t_minutes = t_seconds / 60.0
    t_hours   = t_minutes / 60.0

    return total_path, t_seconds, t_minutes, t_hours


# =============================================================================
# MAIN - Run all tasks and print results
# Usage: python stl_analyzer.py DrucksShoe.stl
# =============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python stl_analyzer.py <stl_file>")
        print("Example: python stl_analyzer.py DrucksShoe.stl")
        sys.exit(1)

    filepath = sys.argv[1]

    print(f"\n{'='*55}")
    print(f"  Drucks Assessment - STL Analyzer")
    print(f"  File: {filepath}")
    print(f"{'='*55}\n")

    # --- Parse ---
    print("[Step 1] Reading STL file...")
    triangles = parse_stl(filepath)
    print(f"         Loaded {len(triangles):,} triangles\n")

    # --- Task 1 ---
    print("[Task 1] Computing volume...")
    volume    = compute_volume(triangles)
    volume_cm = volume / 1000.0
    print(f"         Volume = {volume:,.2f} mm³  ({volume_cm:.3f} cm³)\n")

    # --- Task 2 ---
    print("[Task 2] Computing bounding box...")
    min_x, min_y, min_z, max_x, max_y, max_z = compute_bounding_box(triangles)
    height, layers = compute_layer_count(min_z, max_z, 0.2)

    print(f"         X: {min_x:.3f}  →  {max_x:.3f}  mm  (width  {max_x-min_x:.3f} mm)")
    print(f"         Y: {min_y:.3f}  →  {max_y:.3f}  mm  (depth  {max_y-min_y:.3f} mm)")
    print(f"         Z: {min_z:.3f}  →  {max_z:.3f}  mm  (height {height:.3f} mm)")
    print(f"         Layer count at 0.2mm: {layers}\n")

    # --- Task 3 ---
    path, t_sec, t_min, t_hr = compute_print_time(
        triangles, min_z, max_z, 0.2, 60.0
    )

    # --- Final Summary ---
    print(f"\n{'='*55}")
    print(f"  FINAL RESULTS")
    print(f"{'='*55}")
    print(f"  Volume:            {volume:>14,.2f} mm³")
    print(f"  Bbox X:            {min_x:.3f} → {max_x:.3f} mm")
    print(f"  Bbox Y:            {min_y:.3f} → {max_y:.3f} mm")
    print(f"  Bbox Z:            {min_z:.3f} → {max_z:.3f} mm")
    print(f"  Model Height:      {height:>14.3f} mm")
    print(f"  Layer Count:       {layers:>14d}")
    print(f"  Total Path:        {path:>14,.2f} mm")
    print(f"  Est. Print Time:   {t_min:>14.1f} min  ({t_hr:.2f} hrs)")
    print(f"{'='*55}\n")
    print("  Compare volume + time with OrcaSlicer for Task verification.")
    print("  See writeup.md for full analysis.\n")


if __name__ == "__main__":
    main()