"""Shot list of {slug}. Run from the build folder: python -I shots.py   (or: studio.py build <build>)

One prompt per scene. Later blocks override earlier ones; each fix goes into its own dated @plan.block so
`proof/blocks.md` can say which shots a pass touched.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(
    0, str(HERE.parents[1] / "studio")
)  # <batch>/studio, where shotkit.py lives

from shotkit import (  # noqa: E402
    PUNCH,
    Plan,
    clip,
    date,
    end_card,
    label,
    source,
    still,
)

plan = Plan(
    "{slug}", "{look line: palette, grain, realism; it ends every still prompt}"
)

# 0 to 12 s: the hook. Frame 0 shows the subject; three picture changes by 3.5 s.
plan.shot(
    "s01",
    still=still(
        "{one paragraph: subject, setting, light, camera; the checkable feature named}",
        11,
        check=["{feature a reviewer can look for}"],
    ),
    clip=clip("{the motion: what moves, what the camera does, nothing new enters}"),
    captions=False,
    over=[
        {
            "type": "hook",
            "lines": ["{HOOK *WORD*}", "{SECOND LINE}"],
            "y": 380,
            "size": 190,
        },
        label("{what the thing is}"),
        source("Fact from", "{source name}", 2024),
    ],
)
plan.shot(
    "s02",
    cue="L02:0",
    still=still("{second picture}", 12, check=["{feature}"]),
    cam={"from": 1.06, "to": 1.14},
    over=[date("{DATE OR PLACE CHIP}")],
)
plan.shot("s03", cue="L03:0", use="s01", tin=PUNCH)

# The closing shot. The handle and the AI line come from batch.json (`end`); only the big words and the
# send line are this film's. `use` names an earlier picture, which the end card blurs.
plan.shot(
    "end",
    **end_card(
        ["{TWO OR THREE}", "{WORDS}"],
        "{Send this to someone who ...}",
        use="s01",
        cue="L{last line number}:end",
    ),
)


@plan.block("{YYYY-MM-DD} first pass: fixes after the checks")
def first_pass(p):
    # Fixes after `studio.py check` go here, one block per pass; never edit an earlier block.
    pass


plan.write()
