# Drucks Technical Assessment - Write-up

Candidate: Hitesh BR
Date:10 April 2025
AI Tool Used: Claude (Anthropic) - full conversation submitted as PDF

---

## Task 1: Volume Computation

### Method: Signed Tetrahedra Decomposition

For every triangle on the mesh, I connect its 3 vertices to the origin (0,0,0).
This forms a tetrahedron. Its signed volume is:V = (v1 · (v2 × v3)) / 6

- `v2 × v3` = cross product → vector perpendicular to the triangle
- `v1 · (...)` = dot product → measures depth in that direction
- `/ 6` = tetrahedron volume formula

Outward-facing triangles → positive volume.
Inward-facing triangles → negative volume.
Summing all = exact volume of closed mesh.

### Results

| Metric | Value |
|--------|-------|
| Triangles | 373,632 |
| Volume (my code) | 406,550.65 mm³ |
| Volume (OrcaSlicer) | 406,547 mm³ |
| Difference | 3.65 mm³ (0.0009%) |

### Why the Small Difference
- Floating point rounding across 373,632 triangles
- OrcaSlicer may do minor mesh cleanup before measuring

---

## Task 2: Bounding Box and Layer Count

### Results

| Axis | Min (mm) | Max (mm) | Extent (mm) |
|------|----------|----------|-------------|
| X | -6.953 | 282.610 | 289.563 |
| Y | -62.764 | 46.267 | 109.030 |
| Z | -6.377 | 109.869 | 116.247 |

- **Model height:** 116.247 mm
- **Layer count:** floor(116.247 / 0.2) = **581 layers**
- **OrcaSlicer confirms:** 581 layers ✅

### Print Orientation

Rotating the shoe changes layer count:

| Orientation | Height (mm) | Layers |
|-------------|-------------|--------|
| Current (upright) | 116.247 | 581 |
| Rotated to X | 289.563 | 1,447 |
| Rotated to Y | 109.030 | 545 |

Current orientation (sole down) is natural for printing — minimizes
overhangs and support material on critical surfaces.

---

## Task 3: Print Time Estimation

### Formula: For each layer i (0 to 580):
z_i = min_Z + (i + 0.5) × 0.2
perimeter_i = cross-section outline length at z_i

total_path = Σ perimeter_i
print_time = total_path / 60 mm/s

Perimeter at each layer is computed by finding where triangle edges
intersect the horizontal plane, then summing segment lengths.

### Results

| Metric | My Code | OrcaSlicer |
|--------|---------|------------|
| Total path | 408,750.87 mm | - |
| Print time | **113.5 min (1.89 hrs)** | **341 min (5.68 hrs)** |

### Why My Estimate is Lower Than OrcaSlicer

| Factor I missed | Impact |
|-----------------|--------|
| **Travel moves** (nozzle moving without printing) | +20 min (OrcaSlicer shows 20m7s travel) |
| **Acceleration/deceleration** at corners | Significantly slows real printing vs constant 60mm/s |
| **Overhang walls** printed at slower speed | OrcaSlicer shows 39m58s for overhang walls |
| **Z-hop** between layers | Small time per layer × 581 layers adds up |
| **Retraction** moves | Nozzle pulls back filament at seams |
| **Brim** printing | OrcaSlicer added 2m9s for brim |
| **Start/end sequences** | Prepare time: 39s |

The biggest factor is **acceleration**. Real printers cannot maintain
60 mm/s constantly — they slow down at every corner and curve. A shoe
has many curves, so actual speed averages much lower than 60 mm/s.

OrcaSlicer models all these physical constraints. My formula only
counts pure extrusion path length at constant speed.

---

## Task 4: OrcaSlicer Codebase Navigation

### Search Strategy

Cloned the repository and used `findstr` (Windows) to search for `layer_height` across key source files:

```bash
git clone https://github.com/SoftFever/OrcaSlicer.git
cd OrcaSlicer
findstr /n "layer_height" src\libslic3r\PrintConfig.cpp
findstr /n "layer_height" src\libslic3r\Slicing.cpp
findstr /n "layer_height" src\libslic3r\Print.cpp
findstr /n "generate_object_layers" src\libslic3r\Slicing.cpp

layer_height Call Chain (with line numbers)
Step 1: User Setting Definition

File: src/libslic3r/PrintConfig.cpp
Line 698: def = this->add("layer_height", coFloat);
Line 7019: def = this->add("initial_layer_height", coFloat);
This is where OrcaSlicer registers layer_height as a config option
that the user can set in the UI. Type is coFloat (a float value).
Step 2: Validation

File: src/libslic3r/PrintConfig.cpp
Lines 9616-9620: Validates that layer_height is > 0 and is a
valid multiple of the scaling factor
File: src/libslic3r/Print.cpp
Lines 1581-1583: Checks layer_height does not exceed nozzle diameter
Step 3: Slicing Parameters Created

File: src/libslic3r/Slicing.cpp
Line 81: params.layer_height = object_config.layer_height.value;
This reads the user's layer_height setting into a SlicingParameters
struct that the slicer uses internally
Lines 93-115: Min/max layer heights are computed from nozzle config
Step 4: Z Positions Generated

File: src/libslic3r/Slicing.cpp
Line 742: std::vector<coordf_t> generate_object_layers(...)
This is the KEY function where layer Z positions are computed
It uses slicing_params.layer_height to step through Z:
Line 756: First layer Z = slicing_params.first_object_layer_height
Lines 766-792: Each subsequent layer adds height (derived from
layer_height profile) to get the next Z position
Height is clamped between min_layer_height and max_layer_height
Step 5: Called from Print.cpp

File: src/libslic3r/Print.cpp
Line 1296: generate_object_layers(print_object.slicing_parameters(), layer_height_profile(...))
This is where generate_object_layers is actually called during
the slicing process, connecting config → Z positions
Summary in plain English:

The user sets layer_height = 0.2 in the UI. This value is registered
in PrintConfig.cpp (line 698) as a float config option. When slicing
begins, Print.cpp reads it and creates SlicingParameters via
Slicing.cpp (line 81), storing it as params.layer_height. The
function generate_object_layers() (Slicing.cpp, line 742) then
uses this value to compute a list of Z positions — starting at
first_object_layer_height and stepping upward by layer_height
each time. These Z values are then passed to the mesh slicer which
cuts the triangles at each height to produce cross-section contours.

# layer_height Call Chain
UI (user sets 0.2mm)
    ↓
src/libslic3r/PrintConfig.cpp
    → layer_height defined as FloatOrPercent, default 0.2
    ↓
src/libslic3r/Print.cpp
    → PrintObject::slice() reads config().layer_height
    ↓
src/libslic3r/Slicing.cpp
    → generate_object_layers()
    → z_next = z_current + layer_height  ← Z positions computed here
    ↓
src/libslic3r/TriangleMeshSlicer.cpp
    → slice() cuts mesh at each Z value
    → builds closed contours from triangle-plane intersections

How I found this: Started with grep for "layer_height" in src/,
found PrintConfig.cpp as definition, traced usage into Print.cpp,
then found Slicing.cpp where Z positions are generated, and finally
TriangleMeshSlicer.cpp where geometry is cut.

What I Would Improve

Improvement	Why
Order_segments_into_closed_loops	More accurate perimeter
Model_acceleration/jerk	Better time estimate
Mesh_validation	Catch errors before computing
Handle_multi-contour_layers	Support complex cross-sections
Auto-orientation	Find optimal print direction

    Final Results

Metric	        My_Code	       OrcaSlicer    	Match

Volume	       406,550.65 mm³	  406,547 mm³	  0.0009% diff ✅
Bounding_Box	 Exact	          Exact          	✅
Layer_Count	   581	            581	          Exact ✅
Print_Time	   113.5 min	      341 min	      Explained above