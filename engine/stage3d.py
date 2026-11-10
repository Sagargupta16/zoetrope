# stage3d.py : the 3D side of a plate. It runs inside Blender's Python (the bpy wheel, started by plate3d.py), never
# in the engine environment: scenes.py must not import it. A stage script builds a small scene with these helpers
# and returns pose(t); run() then renders one image per frame with Cycles on the GPU.
#   stage.py:  import stage3d as S3
#              def build(st):            # st is a Stage: materials, shapes, lights, the camera, a character
#                  ...
#                  return pose           # pose(t) sets every position, scale, colour and the camera for time t
#              if __name__ == "__main__":
#                  S3.run(build, fps=24, dur=10.0, size=(1920, 1080))
# As in scenes.py, the picture is a pure function of t: pose(t) carries nothing over from the frame before, so any
# frame renders alone and a stopped render picks up where it stopped. Units are metres, Z is up, and a character
# faces -Y (toward a camera placed at negative Y).
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

# bpy first: Blender's other modules (bmesh, mathutils, bpy_extras) exist only once it is loaded
import bpy  # isort: skip
import bmesh  # isort: skip
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Quaternion, Vector

# proof: half size and few paths, for the proof sheet and the review; final: what a delivered file is made from.
# 64 paths a pixel and the denoiser: 48, 64 and 160 looked the same on a character close-up, at 2.6, 3.3 and 8.1 s
# a 1080p frame (RTX 4070 Laptop, OptiX, 2026-11-10).
QUALITY = {
    "proof": {"scale": 50, "samples": 32, "noise": 0.06},
    "final": {"scale": 100, "samples": 64, "noise": 0.03},
}
# Principled BSDF settings per surface kind; mat() takes any of these keys again to override one
KINDS = {
    "clay": {"rough": 0.62, "sss": 0.14, "sheen": 0.2},
    "toy": {"rough": 0.34, "sss": 0.07, "coat": 0.3},
    "plastic": {"rough": 0.2, "coat": 0.7},
    "matte": {"rough": 0.95, "spec": 0.15},
    "metal": {"rough": 0.26, "metal": 1.0},
    "eye": {"rough": 0.06, "coat": 1.0},
    "glass": {"rough": 0.03, "trans": 1.0},
}
INPUTS = {
    "rough": "Roughness",
    "metal": "Metallic",
    "spec": "Specular IOR Level",
    "sss": "Subsurface Weight",
    "coat": "Coat Weight",
    "sheen": "Sheen Weight",
    "trans": "Transmission Weight",
}
# the view transform, first one this Blender has: Khronos PBR Neutral keeps a palette's hue and saturation and
# rolls the highlights off softly; AgX (Blender's default) turned the same scene pastel (2026-11-10)
VIEWS = ("Khronos PBR Neutral", "Standard", "AgX")
# A time worked out from a cue (land - 0.78 x length) lands a hair before its phase boundary as often as on it. The
# frame on a boundary belongs to the phase that starts there: four landings of the first build drew their landing
# frame as still in the air, with no squash (third review, 2026-11-10).
EDGE = 1e-9
HIDE = (
    0.001,
    0.001,
    0.001,
)  # a scale that takes a part off screen without unlinking it


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def lerp(a, b, k):
    return a + (b - a) * k


def prog(t, t0, dur):
    """0 to 1 while t runs from t0 to t0 + dur."""
    return clamp((t - t0) / dur) if dur > 0 else float(t >= t0)


def ease_out(k):
    return 1 - (1 - k) ** 3


def ease_in(k):
    return k**3


def ease_in_out(k):
    return 4 * k**3 if k < 0.5 else 1 - (-2 * k + 2) ** 3 / 2


def ease_back(k, s=1.70158):
    return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2


def settle(k, bounces=2.5, decay=5.0):
    """1 at k = 0 swinging to 0 at k = 1: the wobble after a landing, a stop or a tap (follow-through)."""
    return math.cos(k * bounces * 2 * math.pi) * math.exp(-decay * k) * (1 - k)


def squash(amount):
    """Scale (x, y, z) for a squash (amount < 0) or a stretch (amount > 0) that keeps the volume."""
    z = 1 + amount
    side = 1 / math.sqrt(z)
    return (side, side, z)


def hop(k, height=1.0, crouch=0.22, stretch=0.22, push=0.4):
    """(z, squash amount) through one jump, k 0 to 1: down into the crouch (anticipation), a push that opens the
    crouch into the stretch while the feet are still on the ground (the last `push` share of the anticipation),
    stretch off the ground, round at the top, stretch again coming down, squash on landing and settle. A crouch of
    0.3 flattens a face for two frames."""
    if k <= 0 or k >= 1:
        return 0.0, 0.0
    if k < 0.18 - EDGE:
        u = k / 0.18
        if u < 1 - push:  # anticipation
            return 0.0, -crouch * math.sin(u / (1 - push) * math.pi / 2)
        # the push: without it the body went from its deepest crouch to full stretch in the frame it left the
        # ground, and the head moved 102 to 133 px at once (two reviews, 2026-11-10)
        return 0.0, lerp(-crouch, stretch, ease_in_out((u - (1 - push)) / push))
    if k < 0.78 - EDGE:  # in the air
        a = max(0.0, (k - 0.18) / 0.6)
        return height * 4 * a * (1 - a), stretch * abs(2 * a - 1) ** 1.5
    return 0.0, -crouch * 0.9 * settle(max(0.0, k - 0.78) / 0.22, 1.5, 3.0)  # landing


def jump(t, land, air=0.7, height=1.0, crouch=0.22, stretch=0.22):
    """hop() by the clock: (z, squash amount) at time t for a jump that is off the ground for air seconds and comes
    down at land. Give land a cue's time and the feet meet the ground on that cue's frame, squashed; the crouch
    starts 0.3 x air before the takeoff and the settle runs 0.37 x air after the landing. A hop under half a second
    in the air spends more of its short crouch on the push, or it leaves the ground in one frame."""
    length = air / 0.6
    return hop(
        (t - (land - 0.78 * length)) / length,
        height,
        crouch,
        stretch,
        0.4 if air >= 0.5 else 0.6,
    )


def rgb(color):
    """'#rrggbb' as the linear RGBA Blender shades with."""
    h = color.lstrip("#")
    c = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    return (
        *(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c),
        1.0,
    )


def aim(obj, target, roll=0.0):
    """Turn a camera or a light to face a point (both look down their own -Z)."""
    q = (Vector(target) - obj.location).to_track_quat("-Z", "Y")
    obj.rotation_euler = (q @ Quaternion((0, 0, 1), roll)).to_euler()


def bend(tube, points):
    """Move a tube made by Stage.tube through new points (the same count)."""
    for p, co in zip(tube.data.splines[0].points, points):
        p.co = (*co, 1.0)


def arc(a, b, sag, n=5, axis=2):
    """n points from a to b, the middle pushed by sag along one axis: a smile, a closed eye, a slack cable."""
    out = []
    for k in range(n):
        u = k / (n - 1)
        p = [lerp(a[i], b[i], u) for i in range(3)]
        p[axis] += sag * 4 * u * (1 - u)
        out.append(tuple(p))
    return out


def star(points=5, r=0.5, inner=0.5):
    """The outline of a star for Stage.slab: [(x, z), ...] from the top point round, inner the valley radius as
    a share of r."""
    out = []
    for k in range(points * 2):
        a, d = math.pi * k / points, r if k % 2 == 0 else r * inner
        out.append((d * math.sin(a), d * math.cos(a)))
    return out


class Stage:
    """One Blender scene set up for a plate: Cycles on the GPU, a film-like view transform, and helpers that each
    add one thing and return its object, so pose(t) can move it."""

    def __init__(self, fps, dur, size, quality="final"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.fps, self.dur, self.size, self.quality = fps, dur, tuple(size), quality
        self.scene = sc = bpy.context.scene
        self.tracks, self.cam, self.wall = {}, None, None
        q = QUALITY[quality]
        sc.render.engine = "CYCLES"
        sc.render.resolution_x, sc.render.resolution_y = self.size
        sc.render.resolution_percentage = q["scale"]
        sc.render.fps = fps
        sc.render.use_persistent_data = (
            True  # keep the kernel and the unchanged geometry between frames
        )
        self.device = self._gpu()
        cy = sc.cycles
        cy.samples, cy.use_adaptive_sampling, cy.adaptive_threshold = (
            q["samples"],
            True,
            q["noise"],
        )
        cy.use_denoising, cy.denoiser = True, "OPENIMAGEDENOISE"
        if hasattr(cy, "denoising_use_gpu"):
            cy.denoising_use_gpu = self.device != "CPU"
        # one noise pattern for every frame: a still corner then holds still instead of boiling
        cy.seed, cy.use_animated_seed = 7, False
        (
            cy.max_bounces,
            cy.diffuse_bounces,
            cy.glossy_bounces,
            cy.transmission_bounces,
        ) = 6, 3, 3, 6
        cy.sample_clamp_indirect, cy.caustics_reflective, cy.caustics_refractive = (
            8.0,
            False,
            False,
        )
        vs = sc.view_settings
        for view in VIEWS:
            try:
                vs.view_transform = view
                break
            except TypeError:
                continue
        self.view = vs.view_transform
        self.world = bpy.data.worlds.new("world")
        sc.world = self.world
        if not self.world.node_tree:
            self.world.use_nodes = True
        self.sky("#dfeaff", 0.3)

    def _gpu(self):
        """Turn on the first GPU backend this machine has; OptiX before CUDA (faster on RTX cards)."""
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                prefs.compute_device_type = kind
            except TypeError:
                continue
            prefs.refresh_devices()
            if any(d.type == kind for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == kind
                self.scene.cycles.device = "GPU"
                return kind
        self.scene.cycles.device = "CPU"
        return "CPU"

    # -- surfaces --------------------------------------------------------------------------------------------
    def mat(self, name, color, kind="toy", glow=0.0, **over):
        """A material: kind is a row of KINDS (clay, toy, plastic, matte, metal, eye, glass); glow lights it from
        inside (emission strength); any KINDS key again overrides one value (rough=0.5)."""
        m = bpy.data.materials.new(name)
        if not m.node_tree:
            m.use_nodes = True
        bsdf = m.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = rgb(color)
        use = {**KINDS[kind], **over}
        for key, v in use.items():
            bsdf.inputs[INPUTS[key]].default_value = v
        if "sss" in use:
            # soft light a few centimetres into the surface, redder as it goes deeper (the look of skin or wax)
            bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.3)
            bsdf.inputs["Subsurface Scale"].default_value = 0.06
        if glow:
            bsdf.inputs["Emission Color"].default_value = rgb(color)
            bsdf.inputs["Emission Strength"].default_value = glow
        return m

    def sky(self, color, strength=0.3):
        """The light that comes from everywhere: one soft colour that fills the shadows."""
        bg = self.world.node_tree.nodes["Background"]
        bg.inputs[0].default_value = rgb(color)
        bg.inputs[1].default_value = strength

    # -- shapes ----------------------------------------------------------------------------------------------
    def _add(self, name, data, at, mat, parent):
        ob = bpy.data.objects.new(name, data)
        self.scene.collection.objects.link(ob)
        ob.location = at
        if mat is not None and data is not None:
            data.materials.append(mat)
        if parent is not None:
            ob.parent = parent
        return ob

    def _mesh(self, name, fill, at, mat, parent):
        me, bm = bpy.data.meshes.new(name), bmesh.new()
        fill(bm)
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        return self._add(name, me, at, mat, parent)

    def empty(self, name, at=(0, 0, 0), parent=None):
        """A point with no shape: a pivot to parent things to, or something for the camera to look at."""
        return self._add(name, None, at, None, parent)

    def ball(self, name, r=0.5, at=(0, 0, 0), mat=None, parent=None, scale=(1, 1, 1)):
        ob = self._mesh(
            name,
            lambda bm: bmesh.ops.create_uvsphere(
                bm, u_segments=64, v_segments=32, radius=r
            ),
            at,
            mat,
            parent,
        )
        ob.scale = scale
        return ob

    def pill(self, name, r=0.2, length=0.6, at=(0, 0, 0), mat=None, parent=None):
        """A capsule standing on Z: a ball of radius r pulled apart by length."""

        def fill(bm):
            bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=r)
            for v in bm.verts:
                v.co.z += length / 2 if v.co.z > 0 else -length / 2

        return self._mesh(name, fill, at, mat, parent)

    def box(self, name, size=(1, 1, 1), at=(0, 0, 0), mat=None, parent=None, r=0.08):
        """A box with rounded edges of radius r, the edge that catches a highlight on a toy."""

        def fill(bm):
            bmesh.ops.create_cube(bm, size=1.0)
            for v in bm.verts:
                v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))

        ob = self._mesh(name, fill, at, mat, parent)
        self._round(ob, r)
        return ob

    def cyl(
        self,
        name,
        r=0.5,
        h=1.0,
        at=(0, 0, 0),
        mat=None,
        parent=None,
        top=None,
        edge=0.03,
    ):
        """A cylinder on Z; top is the upper radius (0 for a cone); edge rounds the rims."""
        r2 = r if top is None else max(top, 1e-4)
        ob = self._mesh(
            name,
            lambda bm: bmesh.ops.create_cone(
                bm, cap_ends=True, segments=64, radius1=r, radius2=r2, depth=h
            ),
            at,
            mat,
            parent,
        )
        self._round(ob, edge)
        return ob

    def ring(self, name, r=0.5, tube=0.1, at=(0, 0, 0), mat=None, parent=None):
        """A torus lying flat in XY."""
        nu, nv = 64, 24

        def fill(bm):
            vs = []
            for i in range(nu):
                u = 2 * math.pi * i / nu
                row = []
                for j in range(nv):
                    v = 2 * math.pi * j / nv
                    d = r + tube * math.cos(v)
                    row.append(
                        bm.verts.new(
                            (d * math.cos(u), d * math.sin(u), tube * math.sin(v))
                        )
                    )
                vs.append(row)
            for i in range(nu):
                for j in range(nv):
                    a, b = (i + 1) % nu, (j + 1) % nv
                    bm.faces.new((vs[i][j], vs[a][j], vs[a][b], vs[i][b]))

        return self._mesh(name, fill, at, mat, parent)

    def slab(
        self, name, outline, depth=0.2, at=(0, 0, 0), mat=None, parent=None, r=0.03
    ):
        """A flat shape with thickness, standing up to face -Y: outline is [(x, z), ...] round its edge (star(),
        an arrow, a bar of a chart, a speech bubble); r rounds the edges."""

        def fill(bm):
            front = [bm.verts.new((x, -depth / 2, z)) for x, z in outline]
            back = [bm.verts.new((x, depth / 2, z)) for x, z in outline]
            bm.faces.new(front)
            bm.faces.new(back)
            for i in range(len(outline)):
                j = (i + 1) % len(outline)
                bm.faces.new((front[i], back[i], back[j], front[j]))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

        ob = self._mesh(name, fill, at, mat, parent)
        self._round(ob, r)
        return ob

    def _round(self, ob, r):
        if r <= 0:
            return
        bev = ob.modifiers.new("round", "BEVEL")
        bev.width, bev.segments, bev.limit_method, bev.angle_limit = (
            r,
            8,
            "ANGLE",
            math.radians(40),
        )
        ob.modifiers.new(
            "normals", "WEIGHTED_NORMAL"
        )  # flat faces stay flat beside the rounded edge

    def tube(self, name, points, r=0.04, mat=None, parent=None):
        """A round rope through the points (a limb, an antenna, a smile, a cable). Move it later with
        bend(tube, points): the same count of points."""
        cu = bpy.data.curves.new(name, "CURVE")
        cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = (
            "3D",
            r,
            8,
            True,
        )
        cu.resolution_u = 16
        sp = cu.splines.new("NURBS")
        sp.points.add(len(points) - 1)
        sp.use_endpoint_u, sp.order_u = True, min(3, len(points))
        ob = self._add(name, cu, (0, 0, 0), mat, parent)
        bend(ob, points)
        return ob

    def text(
        self,
        name,
        s,
        size=1.0,
        depth=0.2,
        at=(0, 0, 0),
        mat=None,
        parent=None,
        font=None,
        edge=0.02,
    ):
        """Solid type standing up to face -Y, centred on at. font is a .ttf or .otf path (a static file: a
        variable font opens at its lightest weight); without one Blender's own face is used. Words in a plate
        are scenery to the text gates: report them in text_items(t) too when the viewer must read them."""
        cu = bpy.data.curves.new(name, "FONT")
        cu.body, cu.size, cu.extrude, cu.bevel_depth, cu.bevel_resolution = (
            s,
            size,
            depth / 2,
            edge,
            4,
        )
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        if font:
            cu.font = bpy.data.fonts.load(str(font))
        ob = self._add(name, cu, at, mat, parent)
        ob.rotation_euler = (math.pi / 2, 0, 0)
        return ob

    def backdrop(
        self,
        color="#f2ead8",
        width=60.0,
        depth=14.0,
        height=24.0,
        curve=5.0,
        kind="matte",
    ):
        """A studio sweep: a floor that curves up into a wall behind the action, so there is no horizon line and
        the ground takes soft shadows and bounced colour."""
        self.wall = depth
        prof = [(-depth * 2.5, 0.0), (depth - curve, 0.0)]
        for k in range(1, 17):
            a = math.pi / 2 * k / 16
            prof.append(
                (depth - curve + curve * math.sin(a), curve - curve * math.cos(a))
            )
        prof.append((depth, height))

        def fill(bm):
            rows = [
                [bm.verts.new((x, y, z)) for (y, z) in prof]
                for x in (-width / 2, width / 2)
            ]
            for k in range(len(prof) - 1):
                bm.faces.new((rows[0][k], rows[1][k], rows[1][k + 1], rows[0][k + 1]))

        return self._mesh(
            "backdrop", fill, (0, 0, 0), self.mat("backdrop", color, kind), None
        )

    # -- light and camera --------------------------------------------------------------------------------------
    def lamp(self, name, at, look=(0, 0, 0.8), size=3.0, power=800.0, color="#ffffff"):
        """A soft box: a square area light of size metres. Bigger is softer; power is in watts."""
        li = bpy.data.lights.new(name, "AREA")
        li.shape, li.size, li.energy, li.color = "SQUARE", size, power, rgb(color)[:3]
        ob = self._add(name, li, at, None, None)
        aim(ob, look)
        return ob

    def glow(self, name, at, power=40.0, color="#ffd66b", r=0.1, parent=None):
        """A small round light, for the inside of something that shines: it lights whatever comes near it."""
        li = bpy.data.lights.new(name, "POINT")
        li.energy, li.color, li.shadow_soft_size = power, rgb(color)[:3], r
        return self._add(name, li, at, None, parent)

    def studio(
        self,
        look=(0, 0, 0.8),
        key=1100.0,
        warm="#fff1dc",
        cool="#cfe0ff",
        side=1,
        wash=2.5,
    ):
        """The lights of a toy photograph: a warm key high on one side (2.2 m across: soft, but the shadow keeps a
        shape), a weak cool fill from the other side, a rim from behind that draws a bright edge round the subject,
        and a wash on the backdrop's wall so the background stays a clean colour (wash times the key's power; it
        needs backdrop() first; 0 for none). side=-1 mirrors the rig."""
        lights = [
            self.lamp("key", (-4.2 * side, -4.6, 5.2), look, 2.2, key, warm),
            self.lamp("fill", (5.0 * side, -3.6, 2.2), look, 6.0, key * 0.18, cool),
            self.lamp("rim", (2.6 * side, 5.2, 4.4), look, 2.5, key, cool),
        ]
        if wash and self.wall:
            # five across, high and far back, aimed up the wall: they light the background evenly, whatever side
            # the camera looks from, and leave the key's shadows on the floor
            for i, x in enumerate((-20.0, -10.0, 0.0, 10.0, 20.0)):
                lamp = self.lamp(
                    f"wash{i}",
                    (x, self.wall * 0.45, 12.0),
                    (x, self.wall, 5.0),
                    8.0,
                    key * wash * 0.7,
                )
                lamp.data.spread = math.radians(100)
                lights.append(lamp)
        return tuple(lights)

    def camera(
        self, at=(0, -7.5, 1.6), look=(0, 0, 0.9), lens=55.0, fstop=None, focus=None
    ):
        """The camera: lens in mm (35 wide, 50 normal, 85 a close portrait). fstop turns on depth of field
        (2.0 very shallow, 5.6 mild), focused at focus metres or, by default, on the point it looks at."""
        if self.cam is None:
            self.cam = self._add(
                "camera", bpy.data.cameras.new("camera"), at, None, None
            )
            self.scene.camera = self.cam
        cam = self.cam
        cam.location, cam.data.lens = at, lens
        aim(cam, look)
        cam.data.dof.use_dof = fstop is not None
        if fstop is not None:
            cam.data.dof.aperture_fstop = fstop
            cam.data.dof.focus_distance = focus or (Vector(look) - Vector(at)).length
        return cam

    def track(self, name, target):
        """Record where an object (or a fixed point) is on screen in every frame, for plate3d.Plate.at(name, t):
        a caption, an arrow or a counter drawn in scenes.py can then follow something in the 3D picture."""
        self.tracks[name] = {"target": target, "xy": {}}

    def sample_tracks(self, frame):
        bpy.context.view_layer.update()
        w, h = self.size
        for tr in self.tracks.values():
            tg = tr["target"]
            p = (
                tg.matrix_world.translation
                if hasattr(tg, "matrix_world")
                else Vector(tg)
            )
            v = world_to_camera_view(self.scene, self.cam, p)
            tr["xy"][frame] = (
                round(v.x * w, 2),
                round((1 - v.y) * h, 2),
                round(v.z, 4),
            )

    # -- characters --------------------------------------------------------------------------------------------
    def buddy(
        self, name, color="#ff7a59", h=1.0, at=(0.0, 0.0), accent=None, kind="toy"
    ):
        """The house character: a round body with big eyes, short limbs and an antenna, about h metres tall
        (1.25 h with the antenna). Returns a Buddy; move it in pose(t) with buddy.pose(...)."""
        return Buddy(self, name, color, h, at, accent or color, kind)


class Buddy:
    """A small character for pantomime. Everything it does comes from pose(): where it stands, how high it is off
    the ground, squash and stretch, a lean, where the eyes look, a blink, the mouth, both arms and both feet."""

    BODY = (
        0.36,
        0.92,
        1.22,
        0.56,
    )  # radius, depth and height factors of the body ball, height of its centre

    def __init__(self, st, name, color, h, at, accent, kind):
        self.st, self.h = st, h
        r, fy, fz, cz = self.BODY
        skin = st.mat(f"{name}_skin", color, kind)
        white = st.mat(f"{name}_white", "#fbfbf6", "eye")
        dark = st.mat(f"{name}_dark", "#191622", "eye")
        limb = st.mat(f"{name}_limb", accent, kind)
        blush = st.mat(f"{name}_blush", "#ff8fa3", "clay", rough=0.8)
        glint = st.mat(f"{name}_glint", "#ffffff", "eye", glow=3.0)
        self.home = (at[0], at[1])
        self.root = st.empty(f"{name}_root", (at[0], at[1], 0.0))
        # everything above the feet hangs from the torso, which carries the squash, the lean and the tilt
        self.torso = st.empty(f"{name}_torso", parent=self.root)
        self.body = st.ball(
            f"{name}_body", r * h, (0, 0, cz * h), skin, self.torso, (1, fy, fz)
        )
        self.eyes, self.lids = [], []
        for sx in (-1, 1):
            x, z = 0.128 * h * sx, 0.69 * h
            eye = st.empty(
                f"{name}_eye{sx}", (x, self.skin(x, z) + 0.031 * h, z), self.torso
            )
            st.ball(
                f"{name}_white{sx}", 0.108 * h, (0, 0, 0), white, eye, (1, 0.55, 1.08)
            )
            pivot = st.empty(f"{name}_gaze{sx}", (0, 0.04 * h, 0), eye)
            st.ball(
                f"{name}_pupil{sx}",
                0.058 * h,
                (0, -0.094 * h, 0),
                dark,
                pivot,
                (1, 0.35, 1.05),
            )
            st.ball(
                f"{name}_glint{sx}",
                0.016 * h,
                (-0.022 * h, -0.118 * h, 0.026 * h),
                glint,
                pivot,
            )
            ends = ((x - 0.075 * h, 0, z), (x + 0.075 * h, 0, z))
            lid = st.tube(
                f"{name}_lid{sx}",
                self.on_skin(arc(*ends, 0.045 * h)),
                0.013 * h,
                dark,
                self.torso,
            )
            bx, bz = 0.205 * h * sx, 0.555 * h
            cheek = st.ball(
                f"{name}_blush{sx}",
                0.05 * h,
                (bx, self.skin(bx, bz), bz),
                blush,
                self.torso,
                (1, 0.25, 0.6),
            )
            cheek.rotation_euler = (
                0,
                0,
                0.62 * sx,
            )  # lie along the body, which turns away to the side here
            self.eyes.append((eye, pivot))
            self.lids.append((lid, ends))
        self.lips = ((-0.07 * h, 0, 0.5 * h), (0.07 * h, 0, 0.5 * h))
        self.mouth = st.tube(
            f"{name}_mouth",
            self.on_skin(arc(*self.lips, 0.0)),
            0.012 * h,
            dark,
            self.torso,
        )
        self.gasp = st.ball(
            f"{name}_gasp",
            0.05 * h,
            (0, self.skin(0, 0.5 * h, 0.004 * h), 0.5 * h),
            dark,
            self.torso,
        )
        top = (cz + r * fz) * h
        self.stalk = st.tube(
            f"{name}_stalk", [(0, 0, top)] * 3, 0.014 * h, limb, self.torso
        )
        self.bulb = st.ball(
            f"{name}_bulb",
            0.05 * h,
            (0, 0, top),
            st.mat(f"{name}_bulb", accent, kind, glow=0.6),
            self.torso,
        )
        self.arms, self.hands, self.legs, self.feet = [], [], [], []
        for sx in (-1, 1):
            self.arms.append(
                st.tube(f"{name}_arm{sx}", [(0, 0, 0)] * 3, 0.036 * h, limb, self.torso)
            )
            self.hands.append(
                st.ball(f"{name}_hand{sx}", 0.068 * h, (0, 0, 0), limb, self.torso)
            )
            self.legs.append(
                st.tube(f"{name}_leg{sx}", [(0, 0, 0)] * 3, 0.04 * h, limb, self.root)
            )
            self.feet.append(
                st.ball(
                    f"{name}_foot{sx}",
                    0.085 * h,
                    (0, 0, 0),
                    limb,
                    self.root,
                    (1.0, 1.5, 0.62),
                )
            )
        self.head = st.empty(
            f"{name}_head", (0, 0, 0.72 * h), self.torso
        )  # something to track or look at
        self.pose()

    def skin(self, x, z, out=0.0):
        """y of the body's front surface at (x, z) in the torso's space, pushed out by out."""
        r, fy, fz, cz = self.BODY
        k = 1 - (x / (r * self.h)) ** 2 - ((z - cz * self.h) / (r * fz * self.h)) ** 2
        return -r * fy * self.h * math.sqrt(max(k, 0.0)) - out

    def on_skin(self, points, out=None):
        """The points laid on the front of the body: a mouth or a closed eye follows its curve."""
        out = 0.004 * self.h if out is None else out
        return [(x, self.skin(x, z, out), z) for x, _, z in points]

    def pose(
        self,
        at=None,
        z=0.0,
        turn=0.0,
        lean=0.0,
        tilt=0.0,
        squash_by=0.0,
        look=(0.0, 0.0),
        blink=0.0,
        smile=0.6,
        gasp=0.0,
        arms=((12, 0), (12, 0)),
        feet=((0, 0), (0, 0)),
        antenna=0.0,
    ):
        """Sides are the camera's, for a character facing it: +x is screen right. at: (x, y) on the floor (None: where it was made); z:
        height of the feet off it; turn, lean, tilt: degrees (turn > 0 turns it to screen right, lean > 0 bows
        toward the camera, tilt > 0 tips it to screen right); squash_by: -0.3 a squash to 0.3 a stretch; look:
        (-1 screen left to 1 right, -1 down to 1 up); blink: 0 open to 1 shut (at 1 the eye is an arc, the
        happy closed eye); smile: -1 a frown to 1 a wide smile; gasp: 0 to 1 an open mouth; arms: (raise,
        swing) degrees per arm, the screen-left arm then the screen-right one: raise 0 hangs, 90 points
        sideways, 170 is up; swing > 0 is toward the camera; feet: (forward, lift) metres per foot, in the
        same order; antenna: sideways lag of the antenna bulb, -1 to 1 (follow-through after a stop or a
        landing)."""
        h = self.h
        # None is where it was made to stand, never where the last frame left it: pose() carries nothing over
        self.root.location.x, self.root.location.y = self.home if at is None else at
        self.root.location.z = z
        self.root.rotation_euler = (0, 0, math.radians(turn))
        self.torso.rotation_euler = (math.radians(lean), math.radians(tilt), 0)
        sq = squash(squash_by)
        self.torso.scale = sq
        shut = blink >= 0.85
        for (eye, pivot), (lid, ends) in zip(self.eyes, self.lids):
            eye.scale = HIDE if shut else (1, 1, max(0.08, 1 - blink))
            pivot.rotation_euler = (
                math.radians(-22 * look[1]),
                0,
                math.radians(26 * look[0]),
            )
            lid.scale = (1, 1, 1) if shut else HIDE
            bend(lid, self.on_skin(arc(*ends, 0.045 * h * (1 if smile >= 0 else -1))))
        bend(self.mouth, self.on_skin(arc(*self.lips, -0.05 * h * smile)))
        # the open mouth and the mouth line are never both on screen: for one frame each way the first build showed
        # the line with a dot on it
        agape = gasp > 0.2
        self.mouth.scale = HIDE if agape else (1, 1, 1)
        g = gasp if agape else 0.001
        self.gasp.scale = (g, 0.3 * g, g * 1.25)
        top, sway = (self.BODY[3] + self.BODY[0] * self.BODY[2]) * h, 0.1 * h * antenna
        bend(
            self.stalk,
            [
                (0, 0, top - 0.02 * h),
                (sway * 0.35, 0, top + 0.09 * h),
                (sway, 0, top + 0.18 * h),
            ],
        )
        self.bulb.location = (sway * 1.1, 0, top + 0.2 * h)
        for i, sx in enumerate((-1, 1)):
            up, fwd = math.radians(arms[i][0]), math.radians(arms[i][1])
            sh = Vector((0.325 * h * sx, 0.0, 0.6 * h))
            d = Vector(
                (
                    math.sin(up) * sx,
                    -math.cos(up) * math.sin(fwd),
                    -math.cos(up) * math.cos(fwd),
                )
            )
            hand = sh + d * 0.3 * h
            elbow = sh + d * 0.16 * h + Vector((0.035 * h * sx, 0, -0.02 * h))
            bend(self.arms[i], [tuple(sh), tuple(elbow), tuple(hand)])
            self.hands[i].location = hand
            # the feet stand on the floor under the root, so the hip is the torso's point after the squash
            hip = Vector((0.13 * h * sx * sq[0], 0.0, 0.2 * h * sq[2]))
            foot = Vector(
                (0.14 * h * sx, -feet[i][0] - 0.02 * h, 0.052 * h + feet[i][1])
            )
            knee = (hip + foot) / 2 + Vector((0, -0.03 * h, 0))
            bend(self.legs[i], [tuple(hip), tuple(knee), tuple(foot)])
            self.feet[i].location = foot


def where(obj):
    """Where an object is in the world right now, after everything pose(t) has set so far: the hand a prop is
    held in, the head a light follows."""
    bpy.context.view_layer.update()
    return obj.matrix_world.translation.copy()


def walk(phase, stride=0.16, lift=0.07):
    """Feet, arm swing and bob for a walk, phase in turns (1 = two steps): ((left foot, right foot), arms, bob).
    Move the character forward by 2 * stride per turn so the planted foot does not slide."""
    a = 2 * math.pi * phase
    feet = tuple(
        (stride * math.sin(a + o), lift * max(0.0, math.cos(a + o)))
        for o in (0.0, math.pi)
    )
    arms = ((14, -32 * math.sin(a)), (14, 32 * math.sin(a)))
    return feet, arms, 0.03 * abs(math.sin(a))


def run(build, fps=24, dur=10.0, size=(1920, 1080), argv=None):
    """Render the plate: build(stage) returns pose(t), and every frame asked for is posed, rendered and saved as
    f_<frame>.jpg in --out, with plate.json beside them (what was rendered, how long it took, the tracks)."""
    if argv is None:
        argv = sys.argv[1:]
        argv = argv[argv.index("--") + 1 :] if "--" in argv else argv
    ap = argparse.ArgumentParser(
        description="render a 3D plate (started by plate3d.py)"
    )
    ap.add_argument("--out", default="plates/main")
    ap.add_argument("--quality", choices=sorted(QUALITY), default="final")
    ap.add_argument("--frames", help="first-last, both included (default: every frame)")
    ap.add_argument(
        "--stills", help="comma-separated times in seconds: render only these frames"
    )
    ap.add_argument(
        "--key",
        default="",
        help="plate3d's hash of the stage source, written to plate.json",
    )
    a = ap.parse_args(argv)
    out = Path(
        a.out
    ).resolve()  # Blender reads a relative path from the drive root, not from here
    out.mkdir(parents=True, exist_ok=True)
    st = Stage(fps, dur, size, a.quality)
    pose = build(st)
    if st.cam is None:
        st.camera()
    n = max(1, round(dur * fps))
    if a.stills:
        todo = sorted(
            {
                min(n - 1, max(0, math.floor(float(s) * fps + 0.5 + 1e-9)))
                for s in a.stills.split(",")
            }
        )
    elif a.frames:
        f0, f1 = (int(v) for v in a.frames.split("-"))
        todo = list(range(max(0, f0), min(n - 1, f1) + 1))
    else:
        todo = list(range(n))
    im = st.scene.render.image_settings
    im.file_format, im.quality, im.color_mode = "JPEG", 96, "RGB"
    t0, made = time.perf_counter(), 0
    if st.tracks:  # the tracks cover every frame, rendered or not: posing is cheap
        for f in range(n):
            pose(f / fps)
            st.sample_tracks(f)
    for i, f in enumerate(todo):
        path = out / f"f_{f:06d}.jpg"
        if path.exists():
            continue
        pose(f / fps)
        # rendered beside its place and moved in when whole: a render killed mid-frame then leaves no f_ file that
        # a resume would take for a finished one
        part = out / f"part_{f:06d}.jpg"
        st.scene.render.filepath = str(part)
        t1 = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        os.replace(part, path)
        made += 1
        print(
            f"plate {i + 1}/{len(todo)} frame {f} {time.perf_counter() - t1:.2f} s",
            flush=True,
        )
    secs = time.perf_counter() - t0
    scale = QUALITY[a.quality]["scale"] / 100
    have = len(list(out.glob("f_*.jpg")))
    meta = {
        "key": a.key,
        "quality": a.quality,
        "fps": fps,
        "frames": n,
        "have": have,
        "size": list(size),
        "rendered": [round(size[0] * scale), round(size[1] * scale)],
        "samples": QUALITY[a.quality]["samples"],
        "device": st.device,
        "view": st.view,
        "blender": bpy.app.version_string,
        "seconds": round(secs, 1),
        "per_frame": round(secs / made, 2) if made else None,
        "tracks": {k: [v["xy"][f] for f in range(n)] for k, v in st.tracks.items()},
    }
    (out / "plate.json").write_text(json.dumps(meta), encoding="utf-8")
    print(
        f"PLATE {out.as_posix()}: {have} of {n} frames, {a.quality}, {st.device}, {secs:.1f} s",
        flush=True,
    )
    return 0
