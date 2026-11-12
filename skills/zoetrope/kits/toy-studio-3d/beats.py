# beats.py : the times the 3D stage (stage.py, in Blender's Python) and the 2D pass (scenes.py) share. Plain numbers
# only: both worlds import it, so it imports nothing. Change a time here and the plate, the captions, the cues and
# the score all move together. Every moment is a whole frame at 24 fps (a multiple of 1/24 s).
FPS = 24
SIZE = (1920, 1080)
BPM = 120  # a waltz: three beats to the bar (1.5 s), two bars to a scene
BEAT = 60 / BPM
BAR = 3 * BEAT

# the scenes in order: (name, seconds). Every length is a whole number of beats.
SCENES = [("want", 3.0), ("fail", 3.0), ("idea", 3.0), ("reach", 3.0), ("end", 4.5)]
DUR = sum(d for _, d in SCENES)
START = {}
_t = 0.0
for _name, _d in SCENES:
    START[_name] = _t
    _t += _d

# moments the picture and the sound both hit (seconds from the start of the film)
HOP_LAND = 2.25  # the small eager hop comes down
LAND = 4.25  # the first jump comes down, short of the star
CRATE_IN, CRATE_STOP = 6.875, 7.5  # the crate slides in and stops under the star
IDEA = 7.75  # the antenna lights up
ON_CRATE = 9.875  # the hop onto the crate comes down
TOUCH = 10.875  # the hand meets the star, just under the top of the second jump
HOME = 11.25  # back on the crate, star in hand
BOUNCES = (13.5, 15.0)  # the happy hops of the end card come down on the bar

# how long each jump is off the ground (seconds)
HOP_AIR, JUMP_AIR, CROSS_AIR, REACH_AIR, BOUNCE_AIR = 0.45, 0.9, 0.625, 0.75, 0.375

# captions: (text, first second, last second). The first is on frame 0 (the thumbnail), the last holds to the end,
# and the others hold to the cut that ends their scene.
LINES = [
    ("Pip wants the star.", 0.0, 3.0),
    ("Too high.", 4.5, 6.0),
    ("Idea!", IDEA, 9.0),
    ("Small steps count.", 12.5, DUR),
]
