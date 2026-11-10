# stage.py : the 3D plate of "Pip wants the star". Runs in Blender's Python through plate3d.py (never imported by
# scenes.py): python plate3d.py render stage.py --quality proof, then without --quality for the final plate.
# One character, one goal, one turn: Pip cannot reach the star, fails a jump, gets a crate, and reaches it.
# Every time comes from beats.py, so a landing here is on the frame its sound is on in score.py.
#   python plate3d.py run stage.py contact   prints, frame by frame, how far the hand is from the star round the catch
import math
import sys

import beats as B
import stage3d as S3
from mathutils import Vector
from stage3d import clamp, ease_in_out, ease_out, lerp, prog

PIP_X = -0.7
CRATE = 0.7  # the crate's edge in metres: Pip is 1.0
STAND_X = 0.55  # where the crate stops and Pip stands on it
REACH_H = 0.4  # how high the second jump goes
REACH_ARMS = ((34, -10), (170, 6))  # the pose of the arms at the top of that jump
STAR_R, STAR_IN = 0.3, 0.52  # the star's radius, and its valleys as a share of it
# From the middle of the raised hand to the middle of the star resting on it: the hand (a ball of 0.068 m) under the
# star's lower left edge, touching and not inside it, the star far enough right to clear the head and the antenna.
HOLD = Vector((0.07, -0.02, 0.267))
BLINKS = (2.75, 5.5, 6.625, 8.75, 12.875, 14.5, 16.125)
FAR = 9.0  # where the crate waits, out of every shot
END_X = (
    STAND_X + 0.95
)  # the end card looks here, so Pip stands in the left third and the title has the right
HAPPY = (
    B.HOME + 0.25,
    B.START["end"] + 0.3,
)  # the closed happy eyes: from just after the landing, across the cut


def blink(t):
    """A blink is three frames: half shut, shut, half shut. The happy eyes close and open over two frames each."""
    happy = min(prog(t, HAPPY[0], 0.084), 1 - prog(t, HAPPY[1], 0.084))
    return max(happy, *(clamp(1.45 - abs(t - b) / 0.06) for b in BLINKS))


def mix(a, b, k):
    return tuple(lerp(x, y, k) for x, y in zip(a, b))


def build(st):
    st.backdrop("#9fb4ff")
    st.sky("#e4e9ff", 0.3)
    st.studio(look=(0.1, 0, 1.0))
    # soft hills far behind, out of focus: depth without anything to read
    for i, (x, y, r, c) in enumerate(
        (
            (-5.2, 7.5, 2.6, "#8fa5f7"),
            (3.4, 9.5, 3.4, "#b9c6ff"),
            (7.4, 6.6, 2.1, "#c7b9ff"),
        )
    ):
        st.ball(f"hill{i}", r, (x, y, -r * 0.35), st.mat(f"hill{i}", c, "matte"))
    pip = st.buddy("pip", "#ff6b4a", at=(PIP_X, 0.0), accent="#2b2850")
    lit = st.mat(
        "idea", "#ffd66b", "toy", glow=0.1
    )  # the antenna's tip is a small lamp
    pip.bulb.data.materials[0] = lit
    crate = st.box(
        "crate",
        (CRATE, CRATE, CRATE),
        (FAR, 0, CRATE / 2),
        st.mat("crate", "#2fc4a8", "toy"),
        r=0.07,
    )
    # The star hangs exactly where the raised hand will be at the top of the second jump, read from the rig in that
    # pose. So the hand meets it on the catch frame and not before, and the star does not move when it is caught.
    # Placed by hand-worked numbers it was wrong twice: the head went through it, then the hand did.
    pip.pose(at=(STAND_X, 0.0), z=CRATE + REACH_H, turn=0.0, arms=REACH_ARMS)
    home = S3.where(pip.hands[1]) + HOLD
    pip.pose()
    gold = st.mat("star", "#ffc21f", "toy", glow=0.15)
    star = st.slab("star", S3.star(5, STAR_R, STAR_IN), 0.16, home, gold, r=0.04)
    shine = st.glow("shine", home, 14.0)
    bulb = lit.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    star_glow = gold.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    st.track("pip", pip.head)
    st.track("star", star)

    def pose(t):
        p = {
            "at": (PIP_X, 0.0),
            "z": 0.0,
            "turn": 16.0,
            "lean": 0.0,
            "tilt": 0.0,
            "squash_by": 0.0,
            "look": (0.75, 0.85),
            "blink": blink(t),
            "smile": 0.45,
            "gasp": 0.0,
            "arms": [(12, 0), (12, 0)],
            "feet": [(0.0, 0.0), (0.0, 0.0)],
            "antenna": 0.0,
        }
        # the star bobs, but holds still for the last fifth of a second before the catch: it is at home when the
        # hand comes up
        still = 1 - prog(t, B.TOUCH - 0.8, 0.6)
        star_at = home + Vector((0, 0, 0.04 * still * math.sin(2 * math.pi * t / 3.0)))
        star_turn, glow, crate_x, idea = (
            22 * math.sin(2 * math.pi * (t - B.TOUCH) / 4.5),
            0.15,
            FAR,
            0.1,
        )
        held = False  # the star is in the hand from the catch on
        focus = None  # the camera focuses on Pip's head unless a scene says where
        rock = 0.0  # the crate tipping as it stops, 1 to 0

        if (
            t < B.START["fail"]
        ):  # want: Pip looks up at the star, reaches, and hops because reaching is not enough
            # the arm is down again before the cut, so the next shot does not start on a different pose
            reach = ease_out(prog(t, 0.4, 0.5)) * (1 - ease_in_out(prog(t, 2.4, 0.5)))
            p["arms"][1] = (lerp(12, 165, reach), 10 * reach)
            z, sq = S3.jump(
                t, B.HOP_LAND, B.HOP_AIR, height=0.2, crouch=0.16, stretch=0.1
            )
            tiptoe = math.sin(math.pi * prog(t, 0.55, 0.8))
            p["z"], p["squash_by"] = z, sq + 0.07 * tiptoe
            k = ease_in_out(prog(t, 0.0, 3.0))
            cam = {
                "at": (lerp(0.42, 0.3, k), lerp(-5.9, -5.45, k), 1.1),
                "look": (0.14, 0, 1.3),
            }
            cam.update(lens=40, fstop=2.8)

        elif (
            t < B.START["idea"]
        ):  # fail: a real jump, a real miss, and the slump after it
            # both arms go up (from this side the far one is hidden by the body), and the jump stays well under the
            # star: at 0.8 m the head came level with it and "Too high." was not true
            z, sq = S3.jump(t, B.LAND, B.JUMP_AIR, height=0.5, crouch=0.2)
            reach = ease_out(prog(t, 3.2, 0.25)) * (
                1 - ease_in_out(prog(t, B.LAND - 0.05, 0.45))
            )
            sad = ease_in_out(prog(t, B.LAND + 0.35, 0.6))
            p["arms"] = [
                (lerp(12, 170, reach), 8 * reach),
                (lerp(12, 170, reach), 8 * reach),
            ]
            p["z"], p["squash_by"], p["lean"] = z, sq - 0.06 * sad, 7 * sad
            p["look"] = mix(
                (0.6, 0.9), (0.12, -0.8), ease_in_out(prog(t, B.LAND + 0.08, 0.5))
            )
            p["smile"] = lerp(0.5, -0.75, sad)
            p["turn"] = lerp(
                16, -16, sad
            )  # the slump turns to the camera, so the face is read
            p["antenna"] = S3.settle(prog(t, B.LAND, 1.0)) if t >= B.LAND else 0.0
            lift = 0.07 * clamp(z / 0.2)
            p["feet"] = [(0.0, lift), (0.0, lift)]
            k = prog(t, 3.0, 3.0)
            # low and close, tilting up a little with the jump: the star looks a long way up
            cam = {
                "at": (lerp(-2.0, -1.85, k), -4.9, 0.42),
                "look": (0.22, 0, 1.2 + 0.25 * z),
            }
            cam.update(lens=38, fstop=4.0)

        elif (
            t < B.START["reach"]
        ):  # idea: a sound off screen, a crate, and the antenna lights up
            heard = ease_in_out(prog(t, B.CRATE_IN - 0.1, 0.25))
            # the gasp gives way straight to the smile: ended earlier, the frown under it showed for three frames
            glad = ease_in_out(prog(t, B.IDEA - 0.3, 0.25))
            up = ease_in_out(prog(t, 8.3, 0.35))
            p["lean"], p["squash_by"] = 7 * (1 - heard), -0.06 * (1 - heard)
            p["turn"] = lerp(-16, 16, heard)
            p["look"] = mix(mix((0.12, -0.8), (0.95, 0.05), heard), (0.7, 0.85), up)
            p["smile"] = lerp(-0.75, 0.95, glad)
            p["gasp"] = clamp(prog(t, B.CRATE_IN + 0.1, 0.12)) * (
                1 - prog(t, B.IDEA - 0.17, 0.12)
            )
            z, sq = S3.jump(
                t, B.CRATE_IN + 0.375, 0.2, height=0.06, crouch=0.05, stretch=0.06
            )
            pump = math.sin(math.pi * prog(t, B.IDEA + 0.05, 0.7))
            p["z"], p["squash_by"] = z, p["squash_by"] + sq + 0.05 * pump
            p["arms"][1] = (lerp(12, 150, pump), 14 * pump)
            p["antenna"] = S3.settle(prog(t, B.IDEA, 0.9)) * 0.7 if t >= B.IDEA else 0.0
            idea = 0.1 + 9.0 * math.exp(-(t - B.IDEA) * 1.6) if t >= B.IDEA else 0.1
            # the crate arrives still moving (at half its starting speed) and stops dead, then rocks: eased to a
            # gentle stop, the picture was still two frames before the thud (Q902 NOTE on the second build)
            slide = prog(t, B.CRATE_IN, B.CRATE_STOP - B.CRATE_IN)
            crate_x = lerp(4.4, STAND_X, (slide - 0.25 * slide * slide) / 0.75)
            rock = (
                S3.settle(prog(t, B.CRATE_STOP, 0.45), 1.5, 3.0)
                if t >= B.CRATE_STOP
                else 0.0
            )
            # the camera has pulled back before the crate comes in, so the slide is seen and not only its stop
            k = ease_in_out(prog(t, B.CRATE_IN - 0.5, 0.75))
            cam = {"at": mix((0.1, -3.6, 0.85), (0.25, -5.0, 0.95), k)}
            cam.update(
                look=mix((-0.6, 0, 0.74), (-0.12, 0, 0.72), k), lens=60, fstop=2.2
            )

        elif (
            t < B.START["end"]
        ):  # reach: up onto the crate, one more jump, and the hand meets the star
            crate_x = STAND_X
            z1, sq1 = S3.jump(t, B.ON_CRATE, B.CROSS_AIR, height=0.5, crouch=0.18)
            air = clamp((t - (B.ON_CRATE - B.CROSS_AIR)) / B.CROSS_AIR)
            # little stretch on this one: stretched, the hand got to the star's height three frames early
            z2, sq2 = S3.jump(
                t, B.HOME, B.REACH_AIR, height=REACH_H, crouch=0.2, stretch=0.1
            )
            p["at"] = (lerp(PIP_X, STAND_X, air), 0.0)
            p["z"] = CRATE * air + z1 + z2
            p["squash_by"] = sq1 + sq2
            p["turn"] = (
                16 + 30 * math.sin(math.pi * air) - 16 * ease_in_out(prog(t, 10.0, 0.4))
            )
            reach = ease_out(prog(t, 10.3, 0.3))
            p["arms"] = [
                mix((12, 0), REACH_ARMS[0], reach),
                mix((12, 0), REACH_ARMS[1], reach),
            ]
            held = t >= B.TOUCH
            caught = prog(t, B.TOUCH, 0.125)
            p["look"] = mix((0.35, 0.95), (0.0, 0.2), prog(t, B.HOME, 0.3))
            p["smile"] = lerp(0.7, 1.0, caught)
            p["antenna"] = (
                0.6 * S3.settle(prog(t, B.HOME, 0.85)) if t >= B.HOME else 0.0
            )
            lift = 0.07 * clamp((z1 + z2) / 0.2)
            p["feet"] = [(0.0, lift), (0.0, lift)]
            if held:
                # it flashes once: enough to see, not enough to wash its gold to white
                glow = 0.15 + 2.0 * math.exp(-(t - B.TOUCH) * 6.0)
            # the camera follows Pip across and then up and in; the star is whole in the frame from the first frame
            rise = ease_in_out(prog(t, 10.3, 0.7))
            cam = {"at": (lerp(1.0, 1.45, air), -5.7, 1.2 + 0.15 * rise)}
            cam.update(
                look=(lerp(-0.2, 0.55, air), 0, 1.22 + 0.36 * rise),
                lens=lerp(40, 45, rise),
                fstop=3.2,
            )

        else:  # end: the star held high in one hand, the other arm cheering, a happy bounce on every bar
            crate_x = STAND_X
            z, sq = 0.0, 0.0
            for b in B.BOUNCES:
                zb, sb = S3.jump(
                    t, b, B.BOUNCE_AIR, height=0.1, crouch=0.1, stretch=0.06
                )
                z, sq = z + zb, sq + sb
            p["at"], p["z"], p["squash_by"], p["turn"] = (
                (STAND_X, 0.0),
                CRATE + z,
                sq,
                0.0,
            )
            p["tilt"] = 4 * math.sin(2 * math.pi * (t - 12.0) / 3.0)
            # the same pose as the last frame of the reach, then the free arm comes up to cheer and waves on the bar
            cheer = ease_in_out(prog(t, 12.2, 0.5))
            wave = 14 * math.sin(2 * math.pi * (t - 12.0) / 1.5) * cheer
            p["arms"] = [
                (
                    lerp(REACH_ARMS[0][0], 150, cheer) + wave,
                    REACH_ARMS[0][1] * (1 - cheer),
                ),
                REACH_ARMS[1],
            ]
            p["look"], p["smile"] = (0.0, 0.2), 1.0
            held = True
            glow = 0.2 + 0.25 * math.sin(math.pi * (t - 12.0) / 1.5) ** 2
            k = ease_in_out(prog(t, 12.0, 4.5))
            cam = {
                "at": (END_X - 0.2, lerp(-5.4, -6.4, k), lerp(1.35, 1.6, k)),
                "look": (END_X, 0, 1.55),
            }
            cam.update(lens=50, fstop=2.4)
            focus = (Vector(cam["at"]) - Vector((STAND_X, 0.0, 1.45))).length

        # breathing: nothing alive is ever still
        p["squash_by"] += 0.012 * math.sin(2 * math.pi * t / 2.4)
        p["arms"], p["feet"] = tuple(p["arms"]), tuple(p["feet"])
        pip.pose(**p)
        if held:
            star_at = S3.where(pip.hands[1]) + HOLD
            star_turn *= 1 - 0.7 * prog(t, B.TOUCH, 0.25)
        star.location, star.rotation_euler = star_at, (0, 0, math.radians(star_turn))
        # under the star, not in front of it: it warms whoever comes near and leaves the star its own gold
        shine.location = star_at + Vector((0, -0.08, -0.36))
        shine.data.energy = 14.0 * (1 + 2 * glow)
        star_glow.default_value, bulb.default_value = glow, idea
        crate.location.x, crate.rotation_euler = (
            crate_x,
            (0, math.radians(-5 * rock), 0),
        )
        head = Vector((p["at"][0], 0.0, p["z"] + 0.7))
        st.camera(**cam, focus=focus or (Vector(cam["at"]) - head).length)

    pose.hand, pose.star, pose.body = pip.hands[1], star, pip.body
    return pose


def contact(fps=B.FPS):
    """How far the hand is from the star round the catch, frame by frame, measured on the rig with no render: the gap
    from the hand's surface to the star's outline (negative: the hand is inside it) and how far the star moved since
    the frame before. The catch is right when the gap is positive before B.TOUCH, about nil from it on, and the star
    does not jump on the catch frame."""
    st = S3.Stage(fps, B.DUR, B.SIZE, "proof")
    pose = build(st)
    outline = S3.star(5, STAR_R, STAR_IN)
    f0, last, worst = round((B.TOUCH - 0.5) * fps), None, 0.0
    for f in range(f0, round((B.HOME + 0.25) * fps) + 1):
        pose(f / fps)
        hand, star = S3.where(pose.hand), S3.where(pose.star)
        turn = math.cos(
            pose.star.rotation_euler.z
        )  # the star turns about its upright: its outline narrows
        px, pz = (hand.x - star.x) / max(turn, 1e-6), hand.z - star.z
        gap = min(
            _to_edge(px, pz, outline[i], outline[(i + 1) % len(outline)])
            for i in range(len(outline))
        )
        gap = (-gap if _inside(px, pz, outline) else gap) - 0.068
        moved = 0.0 if last is None else (star - last).length
        last = star
        when = (
            "catch"
            if f == round(B.TOUCH * fps)
            else "held"
            if f > round(B.TOUCH * fps)
            else ""
        )
        worst = min(worst, gap)
        print(
            f"CONTACT f{f} {f / fps:6.3f} s  gap {gap * 100:6.1f} cm  star moved {moved * 100:5.1f} cm  {when}"
        )
    print(
        f"CONTACT deepest the hand goes into the star: {max(0.0, -worst) * 100:.1f} cm"
    )


def _to_edge(x, z, a, b):
    """Distance from (x, z) to the segment a-b."""
    ax, az, bx, bz = *a, *b
    k = clamp(
        ((x - ax) * (bx - ax) + (z - az) * (bz - az))
        / ((bx - ax) ** 2 + (bz - az) ** 2)
    )
    return math.hypot(x - ax - k * (bx - ax), z - az - k * (bz - az))


def _inside(x, z, poly):
    """Whether (x, z) is inside the outline (crossing count)."""
    n, c = len(poly), False
    for i in range(n):
        (ax, az), (bx, bz) = poly[i], poly[(i + 1) % n]
        if (az > z) != (bz > z) and x < ax + (z - az) * (bx - ax) / (bz - az):
            c = not c
    return c


if __name__ == "__main__":
    if "contact" in sys.argv:
        contact()
    else:
        S3.run(build, fps=B.FPS, dur=B.DUR, size=B.SIZE)
