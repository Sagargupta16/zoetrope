# fonts.py : the free fonts the style cards name (SIL Open Font Licence 1.1), cached outside the repo and loaded by
# family name. engine.font(size, "Nunito:800") draws with one, and so does every text helper (bold="Nunito:800");
# FONT_BOLD and FONT_REG in engine.py stay for the rest. 20 of the 33 cards name one of these 14 families.
#   python fonts.py fetch   download what is missing, pinned to one google/fonts commit, each checked by sha256
#   python fonts.py list    each family, its weights and whether its files are cached
import hashlib
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# the cache, one folder for every build; never inside the repo
FONT_DIR = Path(
    os.environ.get("ZOETROPE_FONTS") or Path.home() / ".cache" / "zoetrope" / "fonts"
)
COMMIT = "6c1dbe27dcf7d817d4b62cec033ba77fa8e2a5ec"  # google/fonts main, 2026-10-31
SOURCE = f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl/"

# family: [(google/fonts ofl/ folder, file, weight (None: a variable file, set to any weight in its range), italic,
# bytes, sha256)]. Weights and italics are the ones the cards ask for; add a row (and its sha256) to fetch another.
# Fetched 2026-10-31: 23 files, 6,804,820 bytes, each matching the size and git blob GitHub lists at COMMIT.
FAMILIES = {
    "Poppins": [
        (
            "poppins",
            "Poppins-SemiBold.ttf",
            600,
            False,
            157312,
            "d3bf1bdaf0550e83da9ac0b1d1d9fe6db086835a83aa28578e609a394b9a0286",
        ),
        (
            "poppins",
            "Poppins-Bold.ttf",
            700,
            False,
            155996,
            "983676516167748b74de6f4771fb384c664fd913acb8b471122ecacf5da5ea6c",
        ),
    ],
    "Nunito": [
        (
            "nunito",
            "Nunito[wght].ttf",
            None,
            False,
            276932,
            "bb55a5ca5c2042335b3991af27c4d0705d0ef41cac6164ac737fd8f2a1e85207",
        ),
    ],
    "Archivo Black": [
        (
            "archivoblack",
            "ArchivoBlack-Regular.ttf",
            400,
            False,
            90988,
            "dd9a89a019b4849f66ab75455fe7bdf931311042cbb0f0f97acc061539703180",
        ),
    ],
    "Inter": [
        (
            "inter",
            "Inter[opsz,wght].ttf",
            None,
            False,
            876576,
            "29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031",
        ),
    ],
    "IBM Plex Mono": [
        (
            "ibmplexmono",
            "IBMPlexMono-Regular.ttf",
            400,
            False,
            135580,
            "6a3412f058c7d8dfd9170c41e85ade48e5156ecb89356110ca57a0a27734af46",
        ),
        (
            "ibmplexmono",
            "IBMPlexMono-SemiBold.ttf",
            600,
            False,
            140216,
            "d3c38e55c78f5b0f28009fddba4834ec503278936a5986032424c9bd2d23aa46",
        ),
        (
            "ibmplexmono",
            "IBMPlexMono-Bold.ttf",
            700,
            False,
            137784,
            "ac27abd6450a64dd94467580a02fe6235156d5b92f2926ebbc8e7489df64e0be",
        ),
    ],
    "Cormorant Garamond": [
        (
            "cormorantgaramond",
            "CormorantGaramond[wght].ttf",
            None,
            False,
            1195560,
            "b20b7d9626dd956b2c5e558692ad328b1f19e3275e2782db4fa07670d83f35e0",
        ),
    ],
    "Cormorant": [
        (
            "cormorant",
            "Cormorant[wght].ttf",
            None,
            False,
            572892,
            "8f12cb21f05b61649192eaff13eeeb1b5619bc524feeae672fb916974259a076",
        ),
        (
            "cormorant",
            "Cormorant-Italic[wght].ttf",
            None,
            True,
            350096,
            "2c4e1c43fa126b51a84160815b9264af442c6c531d13bfd3c1723703cd489dd2",
        ),
    ],
    "Barlow Condensed": [
        (
            "barlowcondensed",
            "BarlowCondensed-SemiBold.ttf",
            600,
            False,
            109428,
            "7b619d14bc2327509a9ef32b0890f709626f7ecc9ff61191c2a4314c5499d2d9",
        ),
        (
            "barlowcondensed",
            "BarlowCondensed-Bold.ttf",
            700,
            False,
            109912,
            "e476562ec9c1e16cf16475895b511f08c804f438cc9a9f80a44ea50a0eeb5b65",
        ),
        (
            "barlowcondensed",
            "BarlowCondensed-ExtraBold.ttf",
            800,
            False,
            110296,
            "724c9c25952d5f4a2d87185d9767aa006144c5f0d944dc05bf7d5d603551c260",
        ),
        (
            "barlowcondensed",
            "BarlowCondensed-Black.ttf",
            900,
            False,
            110828,
            "e74b750df582c608f35db467b711b2b60d2217618e85e60b72b42dfd00446cab",
        ),
    ],
    "JetBrains Mono": [
        (
            "jetbrainsmono",
            "JetBrainsMono[wght].ttf",
            None,
            False,
            187208,
            "48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda",
        ),
    ],
    "Sora": [
        (
            "sora",
            "Sora[wght].ttf",
            None,
            False,
            111400,
            "84ff7096ae3ec6c8be47d906d1a0ba4de7f2ce78c615275c77301964a316e16c",
        ),
    ],
    "Caveat": [
        (
            "caveat",
            "Caveat[wght].ttf",
            None,
            False,
            403648,
            "0bdb6b660482d31531b3945849fba5916b3ef8695da7024a9e6b9ee3c4157988",
        ),
    ],
    "Bodoni Moda": [
        (
            "bodonimoda",
            "BodoniModa[opsz,wght].ttf",
            None,
            False,
            162104,
            "550f5e34ee0a828d7941b1fe9bc58b34e5260d3f33a61532e6d0a0114e79a5cf",
        ),
        (
            "bodonimoda",
            "BodoniModa-Italic[opsz,wght].ttf",
            None,
            True,
            176300,
            "dfff1619f8f6871c6372f8855b67211f9a73b4e93d45aca868cd8f46a48622de",
        ),
    ],
    "Fraunces": [
        (
            "fraunces",
            "Fraunces[SOFT,WONK,opsz,wght].ttf",
            None,
            False,
            360440,
            "177ff6c0f14e5550a3c624247cd1189611d4eb65d000b14944c63d967958abbb",
        ),
    ],
    "STIX Two Text": [
        (
            "stixtwotext",
            "STIXTwoText[wght].ttf",
            None,
            False,
            418956,
            "7962b8b7811e6a896c9a91a0bccbb5241047770eb24d4997c5cb5fe21d5c0df2",
        ),
        (
            "stixtwotext",
            "STIXTwoText-Italic[wght].ttf",
            None,
            True,
            454368,
            "88c0e2e316eaff56eddc9e51e4850317e2a1e490bbf758b2dec4793aedba9c74",
        ),
    ],
}


def _sha256(p):
    with open(p, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def cached(row):
    """True when the row's file is in FONT_DIR with its pinned size and sha256."""
    p = FONT_DIR / row[1]
    return p.is_file() and p.stat().st_size == row[4] and _sha256(p) == row[5]


def parse(spec):
    """(family, weight, italic) from "Family", "Family:700", "Family:italic" or "Family:400:italic"."""
    family, *rest = [s.strip() for s in spec.split(":")]
    weight, italic = 400, False
    for part in rest:
        if part.lower() == "italic":
            italic = True
        elif part.isdigit():
            weight = int(part)
        else:
            raise ValueError(
                f"font {spec!r}: write Family, Family:700 or Family:400:italic"
            )
    if family not in FAMILIES:
        raise ValueError(
            f"font {spec!r}: no family {family!r}; fonts.py has {', '.join(FAMILIES)}"
        )
    return family, weight, italic


def pick(family, weight, italic):
    """The manifest row that draws family at weight: its static file of exactly that weight, or its variable file.
    Never a near miss: a weight or italic the cache does not hold raises, so a card's type is never swapped
    silently (Pillow's silent 10 px default once made every headline tiny)."""
    rows = [r for r in FAMILIES[family] if r[3] == italic]
    for r in rows:
        if r[2] is None or r[2] == weight:
            return r
    have = ", ".join(f"{r[2]}{' italic' if r[3] else ''}" for r in FAMILIES[family])
    raise ValueError(
        f"{family} {weight}{' italic' if italic else ''} is not cached (fonts.py holds {have}); "
        "add its file to FAMILIES or pick a held weight"
    )


def load(spec, size, ss=1):
    """ImageFont for spec ("Nunito:800") at size px. A variable file is set to the weight, and its optical size to
    size / ss within the axis range (opsz is the type size in points, read here as output px); other axes stay at
    their defaults. Raises when the file is missing (run `python fonts.py fetch`) or the weight is out of range."""
    from PIL import ImageFont

    family, weight, italic = parse(spec)
    row = pick(family, weight, italic)
    p = FONT_DIR / row[1]
    if not p.is_file():
        raise FileNotFoundError(
            f"{p} is missing: run `python fonts.py fetch` once (6.8 MB, OFL)"
        )
    f = ImageFont.truetype(str(p), int(size))
    if row[2] is None:
        values = []
        for axis in f.get_variation_axes():
            name = (
                axis["name"].decode()
                if isinstance(axis["name"], bytes)
                else axis["name"]
            )
            lo, hi = axis["minimum"], axis["maximum"]
            if name == "Weight":
                if not lo <= weight <= hi:
                    raise ValueError(f"{family} weights run {lo} to {hi}, not {weight}")
                values.append(weight)
            elif name.lower().startswith("optical"):
                values.append(min(max(size / ss, lo), hi))
            else:
                values.append(
                    axis["default"]
                )  # Fraunces' Softness and Wonky, for example
        f.set_variation_by_axes(values)
    return f


def fetch():
    """Download every manifest file that is missing or wrong into FONT_DIR, each kept only when its size and sha256
    match. Returns the number of files that failed."""
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    rows = [r for fam in FAMILIES.values() for r in fam]
    bad = 0
    for r in rows:
        if cached(r):
            continue
        folder, name, _, _, size, sha = r
        data = urllib.request.urlopen(
            SOURCE + f"{folder}/{urllib.parse.quote(name)}", timeout=60
        ).read()
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha:
            print(
                f"FAIL {name}: {len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()[:12]}; want {size}, {sha[:12]}"
            )
            bad += 1
            continue
        part = FONT_DIR / f"{name}.part"
        part.write_bytes(data)
        part.replace(FONT_DIR / name)
        print(f"ok   {name} {size} bytes")
    held = sum(cached(r) for r in rows)
    print(f"FONTS: {held} of {len(rows)} files cached in {FONT_DIR}")
    return bad


def main(argv):
    if argv[:1] == ["fetch"]:
        return 1 if fetch() else 0
    if argv[:1] in ([], ["list"]):
        for family, rows in FAMILIES.items():
            styles = ", ".join(
                f"{'any weight' if r[2] is None else r[2]}{' italic' if r[3] else ''}{'' if cached(r) else ' (missing)'}"
                for r in rows
            )
            print(f"{family:<19} {styles}")
        return 0
    print("usage: python fonts.py [list|fetch]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
