# sampler.py : recorded instruments for the score (CC0: Versilian Studios' VSCO 2 CE and VCSL), played from numpy
# as mono float arrays at synth.SR, ready for synth.place beside the synth kit. 14 instruments, each fetched on
# demand (pinned commits, every file checked by size and sha256) into a cache outside the repo and decoded there
# once, so a build calls ffmpeg only the first time. references/instruments.md has the table and the credits line.
#   python sampler.py list              each instrument: family, kind, playable range, layers, MB, cached or not
#   python sampler.py fetch [names]     download and decode what is missing (all 14 when no name is given)
#   python sampler.py missing           what is not cached yet (exit 1 when anything is)
#   python sampler.py demo out.wav      an 8-bar phrase at 100 BPM on five instruments, mastered to -14 LUFS
import hashlib
import math
import os
import subprocess
import sys
import urllib.parse
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from functools import cache, lru_cache
from pathlib import Path

import contract as C
import numpy as np
import synth as S

SR = S.SR
# the cache, one folder for every build; never inside the repo. Originals keep their library paths; each decoded
# copy (mono float32 at SR) sits beside its original as <name>.<sha256[:12]>.npy
CACHE = Path(
    os.environ.get("ZOETROPE_INSTRUMENTS")
    or Path.home() / ".cache" / "zoetrope" / "instruments"
)
# both repos carry CC0 1.0 in their LICENSE file at these commits (read 2026-11-10)
LIBS = {
    "vsco": {
        "folder": "VSCO-2-CE",
        "repo": "sgossner/VSCO-2-CE",
        "commit": "440300901dfe9275fd84e0b7763af1f8443ae62e",  # master, 2020-08-05
        "title": "VSCO 2: Community Edition",
        "by": "Versilian Studios (Sam Gossner, Simon Dalzell)",
        # its README.md links the homepage; its Readme.txt asks for credit with that link (a request: CC0 needs none)
        "home": "https://versilian-studios.com/vsco-community/",
    },
    "vcsl": {
        "folder": "VCSL",
        "repo": "sgossner/VCSL",
        "commit": "c1ea7bcc3c7309650ab0da9d15c9cd1fbc4a4c7e",  # master, 2026-01-14
        "title": "Versilian Community Sample Library",
        "by": "Versilian Studios",
        "home": "https://github.com/sgossner/VCSL",
    },
}

# A note plays from the sample nearest its pitch, resampled at most MAX_SHIFT semitones, and at most EDGE semitones
# past the lowest or highest sample. Every gap between samples is 7 semitones or less (3.5 at most from the nearest),
# except the horn's C4 to D5, so the horn has no F4 to A#4; note() raises outside what spans() lists.
MAX_SHIFT, EDGE = 4.0, 2.0
VEL_CURVE = 1.6  # a sound's peak is vel ** VEL_CURVE (vel 1 peaks at full scale, 0.8 at -3.1 dB, 0.5 at -9.6 dB)
PRE = 0.002  # seconds kept before the measured onset, faded in, so the attack is whole and still starts at 0
# the tail is cut after the last 5 ms block within this many dB of the loudest
FLOOR = -60.0
XF = 0.15  # seconds of every crossfade: a sustain's loop return and its splice into the recorded release
SEEK = 0.1  # the recorded release may start at most this long after dur (the splice looks back this far for a match)
REL = 0.2  # a sustain stopped during its attack fades out over this long instead
TAPER = 0.05  # the resampler rolls off the top 5 % of the kept band (a raised cosine), so attacks do not ring

# kind: decay (struck or plucked, rings out, damped at dur with time constant damp), sustain (held for dur, looped
# from its steady part when dur outlasts the recording, then the recorded release) or hit (unpitched, by variant)
INSTRUMENTS = {
    "glockenspiel": {
        "family": "mallets",
        "kind": "decay",
        "damp": 0.10,
        "use": "sparkle, reveal dings, bright top-line melody",
    },
    "marimba": {
        "family": "mallets",
        "kind": "decay",
        "damp": 0.06,
        "use": "warm wooden ostinato and bass for friendly explainers",
    },
    "harp": {
        "family": "plucked strings",
        "kind": "decay",
        "damp": 0.10,
        "use": "arpeggios, glissando-like runs, soft openings",
    },
    "pizz": {
        "family": "strings",
        "kind": "decay",
        "damp": 0.05,
        "use": "playful pizzicato line; cellos under G3, violins from G3",
    },
    "timpani": {
        "family": "percussion",
        "kind": "decay",
        "damp": 0.15,
        "use": "tuned booms on downbeats and reveals (five drums, E2 to G#3)",
    },
    "violins": {
        "family": "strings",
        "kind": "sustain",
        "use": "section pad and long melody (vibrato); place by align='pad'",
    },
    "cellos": {
        "family": "strings",
        "kind": "sustain",
        "use": "warm low pad and held bass (vibrato); place by align='pad'",
    },
    "flute": {
        "family": "woodwinds",
        "kind": "sustain",
        "use": "light melody over a pad (vibrato)",
    },
    "horn": {
        "family": "brass",
        "kind": "sustain",
        "use": "warm brass pad and swells in the low and middle register",
    },
    "bass_drum": {
        "family": "percussion",
        "kind": "hit",
        "use": "orchestral boom under a hit or a cut",
    },
    "snare": {
        "family": "percussion",
        "kind": "hit",
        "use": "concert snare accents; roll under a build",
    },
    "cymbal": {
        "family": "percussion",
        "kind": "hit",
        "use": "suspended cymbal hit; swell2 and swell4 crescendos into a reveal",
    },
    "triangle": {
        "family": "percussion",
        "kind": "hit",
        "use": "bright accent on a payoff; mute for a short tick",
    },
    "tambourine": {
        "family": "percussion",
        "kind": "hit",
        "use": "upbeat pulse: hit on 2 and 4, shake on the offbeats",
    },
}

# (instrument, key, cents, layer, rr, library, path, bytes, sha256). key is the sounding root (MIDI) of a pitched
# sample, or the variant of an unpitched one; cents is how far the recording measured from that root (frame-wise FFT
# peak with parabolic interpolation, median over its loud frames, 2026-11-10; the five timpani drums sit near quarter
# tones); layer counts up from the softest dynamic; rr numbers the round robins of one key and layer. Fetched
# 2026-11-10: 210 files, 232,796,254 bytes, each file's git blob sha1 equal to the tree entry at its commit.
FILES = (
    ("glockenspiel", 79, 8.4, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_soft_G4_01.wav", 706962, "cd92f9402c28d3e951dc8d575ce61f0a550b7e316cb6427b1b455ac3aab09000"),
    ("glockenspiel", 79, 8.2, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_medium_G4_01.wav", 1271310, "6c4649b13e24fa01e4634edad8fe8edf18aef33facc5d49fe53097b376bac4da"),
    ("glockenspiel", 79, 7.8, 3, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_loud_G4_01.wav", 1323482, "be0bf94731720c0094276fea5646e75ff3a8a646b3c828258e9aaab6a8ef6c49"),
    ("glockenspiel", 84, 12.3, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_soft_C5_02.wav", 709206, "4fa149e6f224557df5fab98ad660a8f192bc6fbf2556077dd1089509bf4424e2"),
    ("glockenspiel", 84, 11.8, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_medium_C5_01.wav", 1271310, "635f898e0bcb6975b96b18efd9c896f6f1b97ff12174a339ada4814e49675660"),
    ("glockenspiel", 84, 11.7, 3, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_loud_C5_01.wav", 1323482, "b28baea01b6028e061e5cc978fca70f9062af6a59d155b0fe55e54ec89f42c07"),
    ("glockenspiel", 91, 12.1, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_soft_G5_01.wav", 706962, "73f6a6de89291d0292b303d641444de5e6e1561881f09f6cf20d77f245f7bec3"),
    ("glockenspiel", 91, 11.9, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_medium_G5_01.wav", 1226714, "7045c0ef7260e2f1ad11a64406cf7575ed898d1207a91104d33d78caefac63e4"),
    ("glockenspiel", 91, 11.8, 3, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_loud_G5_01.wav", 1323482, "8aaf97481ef2582c14ef0382ec54c17c1b0a2f901a42976c332bac20fadd74a2"),
    ("glockenspiel", 96, 15.5, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_soft_C6_01.wav", 706962, "e0fdb3a134ee828530c654db7f94b04f94272984938875b0d5535ec40c658324"),
    ("glockenspiel", 96, 15.4, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_medium_C6_01.wav", 1271310, "e942cbf502cf6731df2925945fe3234c876cb63f047d91007b6929887f9e4904"),
    ("glockenspiel", 96, 15.0, 3, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_loud_C6_01.wav", 1323482, "7ca228de549d54770f90bb125e23edcd1dc06cec2b9e1f452661720262f0ecd0"),
    ("glockenspiel", 103, 15.8, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_soft_G6_01.wav", 585962, "b4407b60c2dff43a3a80fe5231beed95caad4d9b8f3f9cdbd80a27642207f35d"),
    ("glockenspiel", 103, 15.7, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_medium_G6_01.wav", 843122, "a2ba94e59119cd5272c1161fc8b8fbfb94c7b44de45a9a6cc5973b1c332103af"),
    ("glockenspiel", 104, 15.6, 3, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_loud_G#6_01.wav", 931630, "7649dda2c67decfcf7a8b98b5225c1b2693a191713d4bb83d4e0afa8b88e51c6"),
    ("glockenspiel", 108, 24.5, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_soft_C7_03.wav", 706962, "68d823a0deffef138d4ed583bd027b9932643a630064274e73d67a644385be4c"),
    ("glockenspiel", 108, 24.2, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_medium_C7_01.wav", 492418, "b2ecbe0e60c983bbfaa49a1f45f8a11559f7dba27b8c8a032eb2cb7366a36910"),
    ("glockenspiel", 108, 24.1, 3, 1, "vcsl", "Idiophones/Struck Idiophones/Glockenspiel/glock_loud_C7_01.wav", 464710, "d9410b4cd52c1b5eb458098d9f8e7685d6dc12d512ee32db378f19d04f2b1f4b"),
    ("marimba", 41, 2.2, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_F1_soft_01.wav", 796046, "eadaeb8bd491b3161197478119be60771e0e1d8620d4848e39595976f9c9c998"),
    ("marimba", 41, 0.1, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_F1_loud_01.wav", 972392, "c5cb5ce59540b0a23628a919e90153a6cee9bb35325b056e0710c12b64f0b193"),
    ("marimba", 48, 2.3, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_C2_soft_01.wav", 1697402, "5fd3c75ab7eafebc24a693793e2c4404922dfad37d8dd9bf80e8ca483500ed80"),
    ("marimba", 48, 1.5, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_C2_loud_01.wav", 2236004, "bfad3b0e57d04c31e6079aba11fb0a6c5c84627fd4bc46e4e0923663586c460c"),
    ("marimba", 55, 0.2, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_G2_soft_01.wav", 1699184, "bb41b6fce6b5cf73086480754f83a4b33ae61a7e6f19c7e7ee3b01d0171e7f63"),
    ("marimba", 55, -0.5, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_G2_loud_01.wav", 1855448, "3bd173f56481e537c3489a94d1e4dd59c304f9f98679c7c90890fc9f5795c25d"),
    ("marimba", 59, 2.9, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_B2_soft_01.wav", 1406594, "10e4a47853920c93423fd72f224e46bf1bce60319d5e7ae501d1b8431ec7d78a"),
    ("marimba", 59, 2.5, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_B2_loud_01.wav", 1585778, "a329138008daae1c03652822d7079c0e1e9941071b8c22195e1985f0c685fdeb"),
    ("marimba", 65, -0.1, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_F3_soft_01.wav", 1455272, "6eb7ccf5fa10b1bdaf10f0cc7a50d8c42ef086636a9e88c6527fb3af58e5ee1f"),
    ("marimba", 65, -0.2, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_F3_loud_01.wav", 1589876, "379e749add43b12959fae06cc272f1871899cc05460faf41ead77b93e5d01843"),
    ("marimba", 72, 4.6, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_C4_soft_01.wav", 915446, "4d03d005166e8b366e6a983b7a4a89e0847e1d58a6d34dda35ddf74289cace94"),
    ("marimba", 72, 4.5, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_C4_loud_01.wav", 1016564, "4af539d47a452d7fad26e171b1c8adcca272cee97191f040d192680462c880b8"),
    ("marimba", 79, -2.3, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_G4_soft_01.wav", 860570, "d3e23f018b091a60d91c3c93b38b605d02a9e26c7cf5830ffb866cfe84130cd0"),
    ("marimba", 79, -2.4, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_G4_loud_01.wav", 800102, "36f39f9f24789001add2b4c440defb7641178b0e8449c5cb7f1960bccaf0aaaf"),
    ("marimba", 83, 0.1, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_B4_soft_01.wav", 492602, "278f5123442162e7946fa68a48ed650e3838b1ddcd3e2173d3ea69f30079c534"),
    ("marimba", 83, -0.1, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_B4_loud_01.wav", 694454, "d04aed26222822d14435fa61b88cdcce95606a5e94bb5e7167d266875343a39c"),
    ("marimba", 89, -2.1, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_F5_soft_01.wav", 373694, "f98ea1bd715aee0091ec8eaf61c9fc3c96440f403e9d32ec33f194fb70d9938c"),
    ("marimba", 89, -2.3, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_F5_loud_01.wav", 551306, "a434c15978b2ea4b8921feeb3fd1f177447324d06c177801e0e46c12a97abc86"),
    ("marimba", 96, -2.9, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_C6_soft_01.wav", 663584, "55d5793308bb10feaf3c1e341c0e4e4dbf8ce7fbea805e118b55177389ec3a09"),
    ("marimba", 96, 0.1, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_C6_loud_01.wav", 472142, "2e42b1b6f6923f32e3daadc12b063e94d15af20fa410ddcb267eb906fd6e0e89"),
    ("harp", 38, -9.3, 1, 1, "vsco", "Strings/Harp/KSHarp_D2_mf.wav", 1741118, "b9cbdc08e43fc0b28ac70246df991cb390f5cbd7f31519b3cc7f70d283b70566"),
    ("harp", 41, -8.1, 1, 1, "vsco", "Strings/Harp/KSHarp_F2_mf.wav", 3086590, "d5c0fb42c176af334fd6f6d1b97858556619c51e177efb5b0c6c23bc19ce6dad"),
    ("harp", 45, -6.2, 1, 1, "vsco", "Strings/Harp/KSHarp_A2_mf.wav", 2007670, "1df9f4d138ca3931fcb458bcdf01304cadf2e5f4eef67bbc17b0e42c0e60fce6"),
    ("harp", 48, -3.0, 1, 1, "vsco", "Strings/Harp/KSHarp_C3_mf.wav", 1586172, "e5d232771704e140959819de8cf2a3e0ba49d021ca77354c42664ce4fce6d9f3"),
    ("harp", 52, -5.5, 1, 1, "vsco", "Strings/Harp/KSHarp_E3_mf.wav", 2461138, "aafa9d41ec0f77da8f2891055af8b3f9557e0ba1f1df93d53ae6e1fda07afae5"),
    ("harp", 55, -8.6, 1, 1, "vsco", "Strings/Harp/KSHarp_G3_mf.wav", 1806874, "62600eb1b37bc2829ca65351f7ca7e506c9ae472abd5bea0765a8b8fa7df2772"),
    ("harp", 59, -12.5, 1, 1, "vsco", "Strings/Harp/KSHarp_B3_mf.wav", 1981130, "f6f71be8c640822ef48a448b245585659acdfcc7ed5774e10f37be2fc02fcab4"),
    ("harp", 62, -12.5, 1, 1, "vsco", "Strings/Harp/KSHarp_D4_mf.wav", 1921690, "ebfde8aab4411019e37e3426f4dd88d6a52a38c2d0261d7f10ec63d8ff584dc7"),
    ("harp", 65, -0.9, 1, 1, "vsco", "Strings/Harp/KSHarp_F4_mf.wav", 1913498, "db27ebbb37334c10e06f2ae63f4d9ff555e4d11704fcc6f0bcf503863867e577"),
    ("harp", 69, -9.5, 1, 1, "vsco", "Strings/Harp/KSHarp_A4_mf.wav", 2143618, "3665f3975cad4a33f46784aa4f896f4b4319ba2b7831e892d975bc38c9f09f23"),
    ("harp", 72, -10.6, 1, 1, "vsco", "Strings/Harp/KSHarp_C5_mf.wav", 1237142, "7c8b862f6fd3f1442ed87537af976d84bda8c05a5b4900e8907d570b5202a517"),
    ("harp", 76, -10.4, 1, 1, "vsco", "Strings/Harp/KSHarp_E5_mf.wav", 1171586, "95dd9ddb0bd15bee7687906e00f25aafcaa43020cc9501f0e8b6cabf0e9a53ec"),
    ("harp", 79, -5.5, 1, 1, "vsco", "Strings/Harp/KSHarp_G5_mf.wav", 1049778, "f2004dfc617997fbabc6f849add2af06f4f859361c44a8fca0f993dc7f999540"),
    ("harp", 83, -8.0, 1, 1, "vsco", "Strings/Harp/KSHarp_B5_mf.wav", 779058, "f2757b674c6b7301bed52e17a1ae3e3d34d628b3f7edc5773ebb25798d2541f7"),
    ("harp", 86, -7.8, 1, 1, "vsco", "Strings/Harp/KSHarp_D6_mf.wav", 687750, "b040b61fb279efa1a9b9c60dcbd8626a37f57ffb30f3b50747a2123ee4db5bd2"),
    ("harp", 89, -5.9, 1, 1, "vsco", "Strings/Harp/KSHarp_F6_mf.wav", 413126, "7cf4c012542df737be39900af262fdd980681956e734f43af106718184f34213"),
    ("harp", 93, -18.9, 1, 1, "vsco", "Strings/Harp/KSHarp_A6_mf.wav", 636870, "4605355d22fae6f58190bf0d033d2ebdd745d63e2e43204d6f41ad27e4f09af0"),
    ("harp", 95, -10.6, 1, 1, "vsco", "Strings/Harp/KSHarp_B6_mf.wav", 483966, "720e56b99f84d4ef1b9bc8cd3c217170320f523edb68488af3da76d2217e16f7"),
    ("harp", 98, -8.4, 1, 1, "vsco", "Strings/Harp/KSHarp_D7_f.wav", 396134, "87ca6f45c5c242d9cd595911278290a4abdba587f71ed263acb1650236fcd4a7"),
    ("harp", 101, -30.5, 1, 1, "vsco", "Strings/Harp/KSHarp_F7_f.wav", 332482, "638b40d6c6c674257daa89b0b1e5108973ccbf13d7cc282e21266d3fb71500c5"),
    ("pizz", 36, 5.2, 1, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_C1_v1_RR1.wav", 829634, "9032689650e38cb7a967616d15f3434bd52865637200e785bf89c3a1a88b29ce"),
    ("pizz", 36, -4.9, 2, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_C1_v2_RR1.wav", 981176, "eb757d0688c447d609e9583c3943b9b51f5dee3c8b309ef6e03cac0c36910f15"),
    ("pizz", 40, -4.3, 1, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_E1_v1_RR1.wav", 842720, "9fed783345f57619ccc7ac1eff282c4e5ec6ff30b7b935ee96da204efb6b6c59"),
    ("pizz", 40, -4.5, 2, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_E1_v2_RR1.wav", 826130, "e5dc2a92063c0d2262336239a227e686c4977b6f8aaf65a2dda13c71ffe982df"),
    ("pizz", 43, -2.4, 1, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_G1_v1_RR1.wav", 852008, "4bfeddd80e7dd07d71f627d16b7458231c6b14118b8b8b3fe039ba8b73d88236"),
    ("pizz", 43, 1.1, 2, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_G1_v2_RR1.wav", 884180, "a12366cff3dd68c4a1622bd504161caa9ed18d23f9d03ed413936a0829188cf1"),
    ("pizz", 47, -9.6, 1, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_B1_v1_RR1.wav", 890366, "33bbfc9664e8536e8931fba5c53ab4e06abeb6f75fc3b6186bcdb159d6000604"),
    ("pizz", 47, -3.7, 2, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_B1_v2_RR1.wav", 1058144, "d5898f41739b4929530aa7d4a3f1660ee2bb6096b375c1f034eb6d26cbb10623"),
    ("pizz", 50, -1.4, 1, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_D2_v1_RR1.wav", 723014, "434925e6b7d154cfa7c17e89ccc8e4a126e01a970cabee22fe09a9fb0e462bb6"),
    ("pizz", 50, 0.1, 2, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_D2_v2_RR1.wav", 770222, "5f80f5fd2f8f3f2cc33b8e7cdba1c5984b5a8158d6d34cd03fe48ae46b335461"),
    ("pizz", 53, 9.1, 1, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_F2_v1_RR1.wav", 662600, "ff44e135372083b7c7989fc741c2ebc97bf91f11c5ba7d3c99bcf2c967f6c4e8"),
    ("pizz", 53, 6.5, 2, 1, "vsco", "Strings/Cello Section/pizzT/pizzT_F2_v2_RR1.wav", 479312, "eb5b95b1f7b22370ad00713db544f2eb3cae6b70a29fcaf673c54d485e73c8a3"),
    ("pizz", 55, 0.5, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_G2_v1_rr1.wav", 409242, "7e424e4d35016be590f352eb9961e9175d6ecfceb31c010dd9f38d5905e518f6"),
    ("pizz", 55, -4.9, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_G2_v1_rr2.wav", 459646, "80df42a5f496d3f41a13345239baa41ab454bf000c95272eb1690e1a2905a3a7"),
    ("pizz", 55, -2.9, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_G2_v2_rr1.wav", 532010, "8de544d9df9ced1fc296d8c4589d354112339802f722361f8625a604ccfd556b"),
    ("pizz", 55, -2.2, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_G2_v2_rr2.wav", 437694, "85f4cdeff82491f0c6d1b881f5403aa178ac08b538498ba5179fd2c9c7004157"),
    ("pizz", 57, -0.3, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_A2_v1_rr1.wav", 220926, "056e2e28e989446da8cdda21f62211a7a30699ea03f4ea074045e85c708a0ea8"),
    ("pizz", 57, -10.0, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_A2_v1_rr2.wav", 247290, "3f795534c596db359e7675f99b877a3b05bf8475e0a392cc1dc258e16c75e282"),
    ("pizz", 57, -1.3, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_A2_v2_rr1.wav", 187354, "75a9bbd0120e03affffe89dd711e5a088507917362e0a197019ff9eff8101340"),
    ("pizz", 57, -4.7, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_A2_v2_rr2.wav", 315758, "da100ff90d5c4568b9d1787627ecf2114fc08f140f2d8481e547572ff5404a42"),
    ("pizz", 59, -3.7, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_B2_v1_rr1.wav", 124886, "6c6e279b3013700f7b0d47042b58679c5d4788637860f6a4788ee6ae7fa25940"),
    ("pizz", 59, -17.6, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_B2_v1_rr2.wav", 116098, "f01036c3a58c277e487070603c81658ff07e9e1ca8bdfa0e22dd1c9f65c2b432"),
    ("pizz", 59, -5.4, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_B2_v2_rr1.wav", 180134, "71aaf7c111d427e76d91a58efc4cf661880cae85ec91123f8f57d421fe36cd06"),
    ("pizz", 59, -3.3, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_B2_v2_rr2.wav", 292378, "4b9b81daa260704f90fb5883263a9fdbe4cb3c74389346b0592ef85f479d5e1c"),
    ("pizz", 62, 5.2, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_D3_v1_rr1.wav", 280306, "fb8819b3626d141393a6bd25daaba728dade39b9f611e6ec449d9018fb3f699c"),
    ("pizz", 62, -1.2, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_D3_v1_rr2.wav", 375514, "82cca3cf7e1d9893cedc42b23c5ee4cfcfce1f9d764936e5f72977857c998e13"),
    ("pizz", 62, -2.7, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_D3_v2_rr1.wav", 391226, "772b8e3bf0f0143cd9aa73dbf64607a41776c0f124c62ef3fecb835f3510ce6a"),
    ("pizz", 62, -1.8, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_D3_v2_rr2.wav", 410238, "386de13448544594429d903be5603ff6b302b2582a6734ec0d754c3cbf284efd"),
    ("pizz", 66, -8.6, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_F#3_v1_rr1.wav", 197422, "a4b60e0fe3090df0282dfd78eb74ac0a4977d8029ed69dd1d67d736e76d33362"),
    ("pizz", 66, -12.8, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_F#3_v1_rr2.wav", 135562, "bfbdce2c919c8959ec11b49224736af943253b31427577ff6e073f0a20f90b74"),
    ("pizz", 66, -0.3, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_F#3_v2_rr1.wav", 157066, "2c6093daad3f6f7a977ac9775660b57227429651d35d489d6f98e617067e8ea6"),
    ("pizz", 66, -5.2, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_F#3_v2_rr2.wav", 176738, "fef269022693eef0b318c1db1a03658f1063ee4d7e3b3bb25e29add97bad6cdc"),
    ("pizz", 69, 1.1, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_A3_v1_rr1.wav", 163490, "6807c9f8a2b8851e866e1f9bb92e9809982693e3593882673d0fe6dedf9b7a96"),
    ("pizz", 69, -5.1, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_A3_v1_rr2.wav", 180382, "aa4d92ddd001ca80737ffcd3aa6a10f6e1b27192bb47a184c05f183475343385"),
    ("pizz", 69, 1.1, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_A3_v2_rr1.wav", 194010, "631720219cbd7b11718b393bdacf04eb512ef5071f9e5d0d73d74b3f17179ec2"),
    ("pizz", 69, 9.2, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_A3_v2_rr2.wav", 205482, "aa6e4d7c84536837e6b9b19203b701a83263b2f4005fc44bd0959321e80c91a5"),
    ("pizz", 72, 3.4, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_C4_v1_rr1.wav", 105914, "7002bd5b93f26bb773ff77e349fbb3b5aa059404889706ddda9673da7488886c"),
    ("pizz", 72, 15.2, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_C4_v1_rr2.wav", 122922, "738c073c13a365f5dcc75f07ef5c540eb15c228e493dc406b9467168af894421"),
    ("pizz", 72, 7.0, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_C4_v2_rr1.wav", 184590, "909eb79fc2c9076909680fa3c2dabdbbd15870f674a883ddab33bbcd0dac965a"),
    ("pizz", 72, 4.6, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_C4_v2_rr2.wav", 197238, "f7ca78a98e4d7dae1ad0a1e1d7f20d9696aedb22751748a3b28f5c4ec2df7de2"),
    ("pizz", 76, -13.2, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_E4_v1_rr1.wav", 109318, "415fce1c81bcaad3a0eac27d328f0c9c0963f7a639823faba9f430bf6d8d5f81"),
    ("pizz", 76, -5.8, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_E4_v1_rr2.wav", 150326, "93ca0b47eb68569f71ab6c9506f776014d05fc5d88763eec64e7b2704a623231"),
    ("pizz", 76, -4.4, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_E4_v2_rr1.wav", 146742, "1e1dcef99c3961a601ed0c8336fbf4819fd432ab783445fe4f44fc488e598993"),
    ("pizz", 76, -8.0, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_E4_v2_rr2.wav", 167882, "7d30e264bdb4884d9d6fe1e6a36e87ada920fa9c630576208510e27f3b2cd22b"),
    ("pizz", 79, -6.0, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_G4_v1_rr1.wav", 148766, "5e3c5dad3385efc081975f7fc76b7574699d836fe01a714afffa2ef1054f8ef8"),
    ("pizz", 79, -0.3, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_G4_v1_rr2.wav", 82618, "2071d0fc7be9b89ad20f646e02acfe6c8fb9aa93f105cfd224c496669adf0ebe"),
    ("pizz", 79, -13.9, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_G4_v2_rr1.wav", 184102, "46d42acdbfe83337f6c6775e03fa99ac99275fd357bdd2d4fa73702c4c7be542"),
    ("pizz", 79, 1.2, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_G4_v2_rr2.wav", 170178, "ac6f949c0f4882274371c49aecc29cf2e91c7e8d741c559dee60107bd25829ab"),
    ("pizz", 83, -11.1, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_B4_v1_rr1.wav", 88054, "69296888a511f280644945ac4aa2890ed90913308a12e7e1f5b7a1cabeffbd6a"),
    ("pizz", 83, 2.6, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_B4_v1_rr2.wav", 92066, "f737d67995a452003352e9d85eb1357c99354b7e040a44cb6c4ac5b57a0d1d20"),
    ("pizz", 83, -3.1, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_B4_v2_rr1.wav", 106362, "ec6f6320f9403a5e0bbb1d0c534abe667a6a2093654343a389b26cf083d513d2"),
    ("pizz", 83, -3.2, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_B4_v2_rr2.wav", 126302, "a316a9761252799f7d5aa64987076432e57b2b4ba31a572e390c4f294ff114f2"),
    ("pizz", 86, -0.2, 1, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_D5_v1_rr1.wav", 122870, "47e1b6e331e8fd51f820f3676ecbd046b194a240334009d891fe183b32613ab7"),
    ("pizz", 86, 6.9, 1, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_D5_v1_rr2.wav", 77634, "e9ac949d9d0e90cd98e00b6ace9e66ea42352920b6de744ae8ae1816cd0e20ee"),
    ("pizz", 86, -1.0, 2, 1, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_D5_v2_rr1.wav", 113286, "50445c5f94fe25272ed98dd03d5af1c34b555f24aa2a7803653aa3b51ed929fc"),
    ("pizz", 86, 15.8, 2, 2, "vsco", "Strings/Violin Section/Pizz/VlnEns_Pizz_D5_v2_rr2.wav", 125806, "cbb872a715f93bba14d7913000015e89aefd477e3c1a7535c8e864e8fa6c0583"),
    ("violins", 55, -2.3, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_G2_v1.wav", 2341712, "feb96c5064fbef43087c495d61a9cab9f70ff1be5b22905147c1f86d5f89547c"),
    ("violins", 55, -1.8, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_G2_v2.wav", 2681324, "c0b06a23f0245c042f0609dc0db704adc14bfc9ea8a34cb5c97d80096715a0e6"),
    ("violins", 57, -2.2, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_A2_v1.wav", 1979216, "5b3ff9f991642a6dc2fdad56a7d94f581077d2c4082cc1ed89156737716ff22c"),
    ("violins", 57, -4.9, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_A2_v2.wav", 2231504, "db6bad06c78577a105f6c2a5dc5c7ac0643c36e6904742411f0506dd9d6fa84b"),
    ("violins", 59, -1.4, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_B2_v1.wav", 2314360, "1a873970a86da78ed8c9aa068303958496c34eee6fa94fcab39d499dbdfb7826"),
    ("violins", 59, 1.0, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_B2_v2.wav", 2373380, "a822fd195e60881afac5e0801d8d494b782a8f6787a08f3c711f5e00290b3fb6"),
    ("violins", 62, 0.5, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_D3_v1.wav", 2061808, "583e660bc5daa4e094aef5fc014fbb92751040be8741ed7a16847306a1fe0a99"),
    ("violins", 62, 1.1, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_D3_v2.wav", 2457908, "77893dbf1ea1be8c40ad756d16b916298e6b1b0742495e9853e020375592357c"),
    ("violins", 66, -0.1, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_F#3_v1.wav", 1585612, "8dc13d197373f0d1fe1b0744de57796800bde372906d3667398c55d473a383ea"),
    ("violins", 66, 0.7, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_F#3_v2.wav", 1720800, "d7bc6b4c259b9543de4fe66228ee107205b8f539c8d7c1de71f5781d45a14fc7"),
    ("violins", 69, -2.3, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_A3_v1.wav", 1890316, "72817a53dfd2eb61eca94658c14e1cab6017629ca2f27bab8e394c6675bfaad7"),
    ("violins", 69, -2.1, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_A3_v2.wav", 1671704, "3fc4a9e22037643fce11e755da72c61c664893f83e637c24a7b5c2d3824ab986"),
    ("violins", 72, 1.1, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_C4_v1.wav", 2063320, "c07edd5b2119fa1da2207aba996961b50dd616f69bbcf2300ab271bc6c16239f"),
    ("violins", 72, 0.7, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_C4_v2.wav", 2017512, "5857387b40c412f756ef281c1171247664432a4e5078c98142d595d15cd92ef9"),
    ("violins", 76, 0.7, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_E4_v1.wav", 2315540, "787fb4bcfb47d5c88ee1573c8db15f32d345386301be4a8eea6a825847413ae2"),
    ("violins", 76, -0.8, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_E4_v2.wav", 1702620, "030c09a631ebbc7304fc0b47bb5c346cd646e7451d9fdc531870f2534c60d9e9"),
    ("violins", 79, -0.0, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_G4_v1.wav", 2330236, "ed2a89cf254432d2af073699fa43ebfa16cfbc5552c7fc964a184fc434eaaa39"),
    ("violins", 79, -0.2, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_G4_v2.wav", 2150136, "a1d6d5a0397541692e2f88a0cd9820eabe90407784ee631aa3bfa74772637a65"),
    ("violins", 83, 2.3, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_B4_v1.wav", 2056964, "ec4cea41ac77f251bf5f4158fe9cbeeae13755e3785106e505808de18fdddc0d"),
    ("violins", 83, -0.1, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_B4_v2.wav", 1923744, "bdb85532f47e4ebd681f9617a415116e7e5aeb786dce2eeab5ab9b93c1b31644"),
    ("violins", 86, 3.6, 1, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_D5_v1.wav", 2116352, "f8d870457826c94270b9c3ead8e8ec02cb7e6c4a3481cded055641b7fab7df62"),
    ("violins", 86, 1.2, 2, 1, "vsco", "Strings/Violin Section/susVib/VlnEns_susVib_D5_v2.wav", 1976276, "0c2ca9de723bed0a0968e32126b934f778cd678b367a29e7fde91004daf84daf"),
    ("cellos", 36, -0.8, 1, 1, "vsco", "Strings/Cello Section/susvib/susvib_C1_v1_1.wav", 2347376, "abdcea431f384e135c469b0f3e4ac2a437f282f521dc5bcbe22abc221536e8de"),
    ("cellos", 40, -2.6, 1, 1, "vsco", "Strings/Cello Section/susvib/susvib_E1_v1_1.wav", 2468348, "de31a61b02d4e1d5a79b8bc432b0f35fe2e434290ad34402cc0f2dd7dc278cde"),
    ("cellos", 43, -2.5, 1, 1, "vsco", "Strings/Cello Section/susvib/susvib_G1_v1_1.wav", 2161700, "9e5d24e8e28d6c7f650f9bb2b33d43c13e341a8bd33124c64e23881378b181ba"),
    ("cellos", 47, -0.6, 1, 1, "vsco", "Strings/Cello Section/susvib/susvib_B1_v1_1.wav", 2372492, "4f95c087c4b8d87ee591e9d39c3c9caf085c6f1b9125eac3ca9e4e637da628ee"),
    ("cellos", 50, 3.8, 1, 1, "vsco", "Strings/Cello Section/susvib/susvib_D2_v1_1.wav", 2550956, "e8640dec9febc6e39fcf06b19d2c95a85d5ff8c38f13c9879e69f551eaf38ab8"),
    ("cellos", 53, -0.2, 1, 1, "vsco", "Strings/Cello Section/susvib/susvib_F2_v1_1.wav", 2186012, "162054eab4ba118924f8f8986cf1b17ccfd65211d1945743ffbae30b4953f901"),
    ("cellos", 57, -1.4, 1, 1, "vsco", "Strings/Cello Section/susvib/susvib_A2_v1_1.wav", 2336738, "c97a003184fdcb153d6b6c0bae8d82a90592a1b04b06bd7caaeda8b9776d5284"),
    ("cellos", 60, 0.5, 1, 1, "vsco", "Strings/Cello Section/susvib/susvib_C3_v1_1.wav", 2444174, "a614ee7ca821b44660236e47b89620cf914ec6ad27a99bc0d9764f47dbe512e1"),
    ("cellos", 64, -2.4, 1, 1, "vsco", "Strings/Cello Section/susvib/susvib_E3_v1_1.wav", 2456672, "d2f961e30bf64021cf4acbd88e0e7a1fd1840943ae78c62a711bcce3d109216e"),
    ("cellos", 67, 1.3, 1, 1, "vsco", "Strings/Cello Section/susvib/susvib_G3_v1_1.wav", 2431598, "8d658346b8d2054fd534b3222b5d7a23196d22a83a68c3a04ffb76b21853a3db"),
    ("flute", 60, -1.9, 1, 1, "vsco", "Woodwinds/Flute/susvib/LDFlute_susvib_C3_v1_1.wav", 2088144, "073631c8442b275d803e608e840c2ce6cad3b08320018e08510cf3cb57373154"),
    ("flute", 64, -0.8, 1, 1, "vsco", "Woodwinds/Flute/susvib/LDFlute_susvib_E3_v1_1.wav", 2802054, "831386b21a704a5fccf204b18a536d638ea191f1b56662200192241215e21abd"),
    ("flute", 69, 0.2, 1, 1, "vsco", "Woodwinds/Flute/susvib/LDFlute_susvib_A3_v1_1.wav", 2117124, "4ea04a7a2ba152752e1b475798619a62f2546f54972caa6ddcd88f29a2046c81"),
    ("flute", 72, 1.7, 1, 1, "vsco", "Woodwinds/Flute/susvib/LDFlute_susvib_C4_v1_1.wav", 2009832, "e88a0ff35e6b8c29fd88bc778a4c817d955b2c3a2934def97a7d093b72e2ae97"),
    ("flute", 76, -1.2, 1, 1, "vsco", "Woodwinds/Flute/susvib/LDFlute_susvib_E4_v1_1.wav", 2144718, "83d4eed0c54ebfe25fe9dfb0475fb90a88a43d11777bc2afac879b8b695e494c"),
    ("flute", 81, -1.1, 1, 1, "vsco", "Woodwinds/Flute/susvib/LDFlute_susvib_A4_v1_1.wav", 1942296, "cf3c1c30943b8b8ef8b5b9ced89430c014987a037204098d002f86e424391ba9"),
    ("flute", 84, -2.8, 1, 1, "vsco", "Woodwinds/Flute/susvib/LDFlute_susvib_C5_v1_1.wav", 1930938, "ecb78c59069866ea7c3327594851827cd2f50c5d411aad422269a88e53614fbe"),
    ("flute", 88, 0.8, 1, 1, "vsco", "Woodwinds/Flute/susvib/LDFlute_susvib_E5_v1_1.wav", 1586118, "6eab0a4827c43b49415cb0c846affd40e9555c884c74683422554923faf17681"),
    ("flute", 93, -1.4, 1, 1, "vsco", "Woodwinds/Flute/susvib/LDFlute_susvib_A5_v1_1.wav", 1457676, "067a42df19ec1864389c28235a6794033471c0ffa3d7e16637396a505ca7d7fd"),
    ("flute", 96, 0.1, 1, 1, "vsco", "Woodwinds/Flute/susvib/LDFlute_susvib_C6_v1_1.wav", 1260120, "0ead172a529daad09ecbab66027027b92189afe79f50f71dc20ee58ca66c9135"),
    ("horn", 33, -7.2, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_A0_v1_1.wav", 947196, "cf71214116045722b401d12867c1c4ea0c52314834e5fc0538eeae8b7da6acad"),
    ("horn", 36, -1.9, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_C1_v1_1.wav", 1093856, "886fd6f490b64f7f2a597f45fe6af01e8c90da9e01d0bf8bdcaceb540a071283"),
    ("horn", 39, -1.1, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_D#1_v1_1.wav", 1425196, "b5568812f0ed56900071c55cae86518d030b2eb23f9ee094b0706e47984b16d8"),
    ("horn", 43, -0.7, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_G1_v1_1.wav", 2038728, "f26c86c4ed934343c37291c33324c4797db1de62f5030dee1670d2d6e64dcb65"),
    ("horn", 46, 1.9, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_A#1_v1_1.wav", 2417592, "134f9c522ea928e5bfebb49c649b5eeb809075f1b9f42ac6b984f16ff7457fec"),
    ("horn", 50, -0.9, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_D2_v1_1.wav", 2500360, "c8a320cff7c6d19f7089c374e3041b1cbbc73718ba9de37149a82a1117866015"),
    ("horn", 53, -1.6, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_F2_v1_1.wav", 2163124, "d3dcfb6c90cb76954887eb56a85041d5e758bad21234ec0ed11e476d6f05352b"),
    ("horn", 57, -5.2, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_A2_v1_1.wav", 2672192, "897ffa7cfdf4e0413e4c80e7fa935f28e0a0971691e112f1516c6102da61809f"),
    ("horn", 60, 1.5, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_C3_v1_1.wav", 2519448, "d96bc1821e46352e620fc0e3eaa9bbc415824e0f84f19aac6373c54c6aaa34da"),
    ("horn", 74, 1.0, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_D4_v1_1.wav", 1445100, "2866520e737f3826ee9f53693f148109a9cc2d2e54235db0b92f78b2c100b8f7"),
    ("horn", 77, 0.7, 1, 1, "vsco", "Brass/F Horn/sus/MOHorn_sus_F4_v1_1.wav", 1477536, "580b2e57aa42f5fd6e4ecb65dcb79f01dfe510e98ddc2bea0a77fca1cba8d424"),
    ("timpani", 41, 48.9, 1, 1, "vsco", "Percussion/Timpani/Timpani1_Hit_v1_rr1_Sum.wav", 559976, "a43d60795e9eab808866c22b6b6b42a64d3a13f6754838f0100a0a1e9a3029cd"),
    ("timpani", 41, 48.9, 2, 1, "vsco", "Percussion/Timpani/Timpani1_Hit_v3_rr1_Sum.wav", 1602676, "8b39a785901d08dee14dd89914bdf2201e16ee418965e4d903fdb8e280a14d24"),
    ("timpani", 47, -23.7, 1, 1, "vsco", "Percussion/Timpani/Timpani2_Hit_v1_rr1_Sum.wav", 1150296, "19b6e335811edd38d7ecc180d9d6e4adada12ff7a882f83e5153f093a912ae85"),
    ("timpani", 47, -19.3, 2, 1, "vsco", "Percussion/Timpani/Timpani2_Hit_v3_rr1_Sum.wav", 1895164, "69e5d604effd3f29c86117d22ad2335f73e43f5d47868dc57d8fa593975ee241"),
    ("timpani", 49, 47.9, 1, 1, "vsco", "Percussion/Timpani/Timpani3_Hit_v1_rr1_Sum.wav", 929172, "00319863ade67b49ec64566eecc801ac7c95e101860b7bb3263f25c7d6757392"),
    ("timpani", 49, 48.9, 2, 1, "vsco", "Percussion/Timpani/Timpani3_Hit_v3_rr1_Sum.wav", 1608252, "46cd2ba3798f9e3a6be515b13dbc37d2ef65c82afb0d0e9e34121e4524bfcd3a"),
    ("timpani", 52, 42.3, 1, 1, "vsco", "Percussion/Timpani/Timpani4_Hit_v1_rr1_Sum.wav", 1183312, "0c2929ae4fa59e0cbd2a43ee1abb187cce99dc41713bcb012ea71eac39fe6c35"),
    ("timpani", 52, 41.1, 2, 1, "vsco", "Percussion/Timpani/Timpani4_Hit_v3_rr1_Sum.wav", 1012976, "05170757d30297aa680bfbc082c6e438deb1d1d72c5e757610d0b1bbd525968f"),
    ("timpani", 54, 50.1, 1, 1, "vsco", "Percussion/Timpani/Timpani5_Hit_v1_rr1_Sum.wav", 327568, "c6fc35883ec63df83250b9eb92b05763504a3a484fffad5e82eb95945cab32cf"),
    ("timpani", 54, 41.2, 2, 1, "vsco", "Percussion/Timpani/Timpani5_Hit_v3_rr1_Sum.wav", 1036528, "da8212316bb05e3c06c730d6a67ae4b3c8ed90ca5ec8c52410cb9d0cde1bddb4"),
    ("bass_drum", "hit", 0.0, 1, 1, "vcsl", "Membranophones/Struck Membranophones/Bass Drum 1/BDrumNew_hit_v2_rr1_Sum.wav", 281616, "56827fe9b55f282a0db851e242bc24660d339a0e358b182966aea047240c1136"),
    ("bass_drum", "hit", 0.0, 1, 2, "vcsl", "Membranophones/Struck Membranophones/Bass Drum 1/BDrumNew_hit_v2_rr2_Sum.wav", 302396, "f1f8979de26f8efe278fe778da7bdce2a39fbfb9f2cbf345e38ce8c66f171b59"),
    ("bass_drum", "hit", 0.0, 2, 1, "vcsl", "Membranophones/Struck Membranophones/Bass Drum 1/BDrumNew_hit_v3_rr1_Sum.wav", 367124, "a2d8829e8b2b59e8afb12fa396b01758827059339c2a84ad066d17b36c82d1ff"),
    ("bass_drum", "hit", 0.0, 2, 2, "vcsl", "Membranophones/Struck Membranophones/Bass Drum 1/BDrumNew_hit_v3_rr2_Sum.wav", 354580, "036c6c5fcfbcca845d92dbcdcef075ee6e0ae01636374a2f7dd1a696a7ba33f8"),
    ("bass_drum", "hit", 0.0, 3, 1, "vcsl", "Membranophones/Struck Membranophones/Bass Drum 1/BDrumNew_hit_v5_rr1_Sum.wav", 588092, "642aaf3375eaff1307973f7de3ccbf74d18e71fb3cf9412e021b08fc3bf1981c"),
    ("bass_drum", "hit", 0.0, 3, 2, "vcsl", "Membranophones/Struck Membranophones/Bass Drum 1/BDrumNew_hit_v5_rr2_Sum.wav", 614388, "a83943f8125ae39469ef5dab1d0be2fe3145c6842c0621b27be5d86aa44b325d"),
    ("bass_drum", "hit", 0.0, 4, 1, "vcsl", "Membranophones/Struck Membranophones/Bass Drum 1/BDrumNew_hit_v7_rr1_Sum.wav", 1105152, "7024054e68261d2cca0ee58fdf9d6f23b54370792d04aa2c1ccf41acc090bd2b"),
    ("bass_drum", "hit", 0.0, 4, 2, "vcsl", "Membranophones/Struck Membranophones/Bass Drum 1/BDrumNew_hit_v7_rr2_Sum.wav", 993988, "fa4374b9ffdc3b9a3c85331ce96c447cf13e46d956cce9cfd9ba02801f71276f"),
    ("snare", "hit", 0.0, 1, 1, "vcsl", "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitSN_v3_rr1_Mid.wav", 305304, "3d71765aa0d1e13260abeb003720aef0841432df601883177bf70e97d9af6c99"),
    ("snare", "hit", 0.0, 1, 2, "vcsl", "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitSN_v3_rr2_Mid.wav", 231264, "770a0b6bfe95583c11014d5f9af9c94c425a15bd05234c86213aec356a2ffe29"),
    ("snare", "hit", 0.0, 2, 1, "vcsl", "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitSN_v5_rr1_Mid.wav", 240496, "6ec8445cb207df8f1178d8c3894f47969fd53fb2b81c404317e466de4598dc3e"),
    ("snare", "hit", 0.0, 2, 2, "vcsl", "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitSN_v5_rr2_Mid.wav", 255456, "6d563828174cf9f29d221b14e1d3309ad4db8a4ac2cf10ff0ae4f0564e0d2590"),
    ("snare", "hit", 0.0, 3, 1, "vcsl", "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitSN_v7_rr1_Mid.wav", 271480, "e63d9ebb2d1f85456d7554448b52330031051bc45db36f5fe08ef5f5149421e6"),
    ("snare", "hit", 0.0, 3, 2, "vcsl", "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitSN_v7_rr2_Mid.wav", 258420, "c0ee12638c1255152d9e914c61bdbe6ff145e396d21302a91e33495d50335383"),
    ("snare", "hit", 0.0, 4, 1, "vcsl", "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitSN_v9_rr1_Mid.wav", 294868, "ea0adea05227c09002fb7305613cb2877003dc3ba3467d3b2d60c20f5664d59a"),
    ("snare", "hit", 0.0, 4, 2, "vcsl", "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitSN_v9_rr2_Mid.wav", 272616, "2a522774cab32b7c8ad6ea8d40ce5a4a36720c9735a653b4ee9c1c0c5294e61d"),
    ("snare", "roll", 0.0, 1, 1, "vcsl", "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_rollSN_v4_rr1_Mid.wav", 1649100, "b23fb9a338ae9c419b5c33b4f8365315a518914155078d3ed354073eb27a8880"),
    ("cymbal", "hit", 0.0, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Suspended Cymbal 1/susCymb1_hit_pp1.wav", 1844706, "d3221ae2c34233b1fa8ceb011ac91d9d3064a57bacff158e41fdef780ad575f8"),
    ("cymbal", "hit", 0.0, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Suspended Cymbal 1/susCymb1_hit_mp1.wav", 1981318, "426238ad2bfadab07895c7b8f89204fed623d865693cc02d72c68627a86df75e"),
    ("cymbal", "hit", 0.0, 3, 1, "vcsl", "Idiophones/Struck Idiophones/Suspended Cymbal 1/susCymb1_hit_f1.wav", 2046894, "42a8ece91eccec9b7063793e6644d037a9005c01d5b76f6bec358e8d53fb92a5"),
    ("cymbal", "hit", 0.0, 4, 1, "vcsl", "Idiophones/Struck Idiophones/Suspended Cymbal 1/susCymb1_hit_fff1.wav", 2285114, "993ceb041adaad19c88042e9d6e66707c30eda6e44a5a263d68bb4a3cdb2ca02"),
    ("cymbal", "swell2", 0.0, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Suspended Cymbal 1/susCymb1_cresc_2s.wav", 1837622, "a5507bf116b33ee220f4eff54506be56fd455e908c8d53903f217590341e5008"),
    ("cymbal", "swell4", 0.0, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Suspended Cymbal 1/susCymb1_cresc_4s.wav", 2291710, "bb3b6b251b0b9dac23b7b0fae47aab84a70abbefa4a110b05c9f4ad733e70741"),
    ("tambourine", "hit", 0.0, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Tambourine 1/Tamb1_Hit_v1_rr1_Mid.wav", 338496, "6fd5af9ec2d94c3b66fa871aecbc2e2844eea155a668fd0f15f07d59ae67dd40"),
    ("tambourine", "hit", 0.0, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Tambourine 1/Tamb1_Hit_v2_rr1_Mid.wav", 293256, "885ebf1d70f8e888f576682e4e4112b92b69649162f392c83b3379c91a09cf41"),
    ("tambourine", "shake", 0.0, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Tambourine 1/Tamb1_Shake_rr1_Mid.wav", 258948, "5876b66d1e8009b3ee884ff3bf52fbc420b44f9ddffffe830b4074d3dfc09924"),
    ("tambourine", "shake", 0.0, 1, 2, "vcsl", "Idiophones/Struck Idiophones/Tambourine 1/Tamb1_Shake_rr2_Mid.wav", 237792, "5ab51f8cd9fba10ae7a7125b96a520c69e049687409532b745fddd5356c6d6f3"),
    ("triangle", "hit", 0.0, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Triangles/Triangle1_Hit_v1_rr1_Mid.wav", 770316, "0397199e59671937bde1e5d29fc2e74946e6c56889cc196e5053f33644f17ff7"),
    ("triangle", "hit", 0.0, 1, 2, "vcsl", "Idiophones/Struck Idiophones/Triangles/Triangle1_Hit_v1_rr2_Mid.wav", 722212, "2a926f7a0619fad3f0deb2082f09a68379e9a331160225573a6dca0045a15bfc"),
    ("triangle", "hit", 0.0, 2, 1, "vcsl", "Idiophones/Struck Idiophones/Triangles/Triangle1_Hit_v2_rr1_Mid.wav", 1059424, "bec62db48c6a052bff1b54f88c11fc6cb6131b9633da2afb35636291754971af"),
    ("triangle", "hit", 0.0, 2, 2, "vcsl", "Idiophones/Struck Idiophones/Triangles/Triangle1_Hit_v2_rr2_Mid.wav", 1000876, "d4882b06475b34e4a7b248e1ca52169d74209a4226ae4ddac5a41aaaf455cbf2"),
    ("triangle", "mute", 0.0, 1, 1, "vcsl", "Idiophones/Struck Idiophones/Triangles/Triangle1_HitM_v1_rr2_Mid.wav", 208872, "260790ef70630f0b05f63f845a775011b020aadb3389c5ca68c9f6cf58f69bfc"),
    ("triangle", "mute", 0.0, 1, 2, "vcsl", "Idiophones/Struck Idiophones/Triangles/Triangle1_HitM_v1_rr4_Mid.wav", 194028, "6e4f8cad1b1ee2c352988067ab541dd53758195af8a10f2d1107dd7076ef9d8a"),
)  # fmt: skip

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(m):
    """'C4' for MIDI 60."""
    return f"{NAMES[int(m) % 12]}{int(m) // 12 - 1}"


def _index():
    """{instrument: {key: {layer: [FILES index, ...] in rr order}}}"""
    by = {}
    for i, (inst, key, _, layer, *_) in enumerate(FILES):
        by.setdefault(inst, {}).setdefault(key, {}).setdefault(layer, []).append(i)
    return by


BY = _index()


def _spec(inst):
    if inst not in INSTRUMENTS:
        raise ValueError(
            f"no instrument {inst!r}; sampler.py has {', '.join(INSTRUMENTS)}"
        )
    return INSTRUMENTS[inst]


def _pitches(inst):
    """[(sounding pitch of the key's recordings, key)] low to high: the key plus its files' mean offset."""
    out = []
    for key, layers in BY[inst].items():
        rows = [FILES[i] for ix in layers.values() for i in ix]
        out.append((key + sum(r[2] for r in rows) / len(rows) / 100, key))
    return sorted(out)


def spans(inst):
    """The MIDI notes inst can play, as [(lo, hi)] inclusive runs: within EDGE of its outermost samples and within
    MAX_SHIFT of the nearest one. [] for an unpitched instrument."""
    if _spec(inst)["kind"] == "hit":
        return []
    ps = [p for p, _ in _pitches(inst)]
    lo, hi = math.ceil(ps[0] - EDGE - 1e-9), math.floor(ps[-1] + EDGE + 1e-9)
    ok = [m for m in range(lo, hi + 1) if min(abs(m - p) for p in ps) <= MAX_SHIFT]
    runs = []
    for m in ok:
        if runs and m == runs[-1][1] + 1:
            runs[-1][1] = m
        else:
            runs.append([m, m])
    return [tuple(r) for r in runs]


# ---- the cache: fetch, verify, decode ----


def _file(i):
    lib, path = FILES[i][5], FILES[i][6]
    return CACHE / LIBS[lib]["folder"] / path


def _npy(i):
    p = _file(i)
    return p.with_name(f"{p.name}.{FILES[i][8][:12]}.npy")


def _sha256(p):
    with open(p, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def cached(i):
    """True when FILES[i]'s original is in CACHE with its pinned size and sha256."""
    p = _file(i)
    return p.is_file() and p.stat().st_size == FILES[i][7] and _sha256(p) == FILES[i][8]


def _rows(names):
    names = list(INSTRUMENTS) if names is None else list(names)
    for n in names:
        _spec(n)
    return names, [i for i, r in enumerate(FILES) if r[0] in names]


def _mb(inst):
    return sum(r[7] for r in FILES if r[0] == inst) / 1e6


def _decode(i):
    """Decode FILES[i] once into its .npy beside the original: ffmpeg to float32 stereo at SR, averaged to mono.
    The part file is named per process, so two builds decoding one file at once do not collide."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(_file(i)), "-f", "f32le"]
        + ["-ac", "2", "-ar", str(SR), "-"],
        capture_output=True,
        check=True,
    ).stdout
    x = np.frombuffer(raw, "<f4").reshape(-1, 2).mean(1).astype(np.float32)
    part = _npy(i).with_name(f"{_npy(i).name}.{os.getpid()}.part")
    with open(part, "wb") as f:
        np.save(f, x)
    part.replace(_npy(i))
    return x


def _download(i):
    """FILES[i] into CACHE when missing or wrong; returns '' or what failed."""
    if cached(i):
        return ""
    *_, lib, path, size, sha = FILES[i]
    url = f"https://raw.githubusercontent.com/{LIBS[lib]['repo']}/{LIBS[lib]['commit']}/{urllib.parse.quote(path)}"
    data = urllib.request.urlopen(url, timeout=120).read()
    got = hashlib.sha256(data).hexdigest()
    if len(data) != size or got != sha:
        return f"{path}: {len(data)} bytes, sha256 {got[:12]}; want {size}, {sha[:12]}"
    p = _file(i)
    p.parent.mkdir(parents=True, exist_ok=True)
    part = p.with_name(f"{p.name}.{os.getpid()}.part")
    part.write_bytes(data)
    part.replace(p)
    return ""


def fetch(names=None):
    """Download every file of the named instruments (all when None) that is missing or wrong, each kept only when its
    size and sha256 match, and decode each once. Returns the number of files that failed."""
    names, ix = _rows(names)
    with ThreadPoolExecutor(6) as pool:
        errs = list(pool.map(_download, ix))
    bad = [e for e in errs if e]
    for e in bad:
        print(f"FAIL {e}")
    for i in ix:
        if not _npy(i).is_file() and cached(i):  # hash only what still needs decoding
            _decode(i)
    for n in names:
        held = [i for i in ix if FILES[i][0] == n and _npy(i).is_file()]
        total = sum(1 for r in FILES if r[0] == n)
        print(
            f"{'ok  ' if len(held) == total else 'FAIL'} {n:<13} {len(held)} of {total} files, {_mb(n):.1f} MB"
        )
    print(
        f"FETCH: {'FAIL' if bad else 'OK'} ({len(names)} of {len(INSTRUMENTS)} instruments asked, in {CACHE})"
    )
    return len(bad)


def missing(names=None):
    """The named instruments (all when None) that are not ready to play: any file not decoded in the cache."""
    names, ix = _rows(names)
    gone = {FILES[i][0] for i in ix if not _npy(i).is_file()}
    return [n for n in names if n in gone]


def _from_onset(x):
    """x from PRE before its onset (synth.landmarks' measure: the first 1 ms block within 30 dB of the loudest), the
    kept head faded in. Run again on every finished note and chord, not only on the recording: a slow attack hovers
    near -30 dB for a while, and a note's own loudest block moves with its length, pitch and sum (a horn shifted 3
    semitones read its onset 16 ms in before this second pass)."""
    w1 = C.sample_of(0.001, SR)
    m = -(-len(x) // w1)
    b1 = np.pad(x * x, (0, m * w1 - len(x))).reshape(m, w1).mean(1)
    on = int(np.argmax(b1 >= b1.max() / 1e3)) * w1
    start = max(0, on - C.sample_of(PRE, SR))
    if start == 0:
        return x
    y = x[start:].copy()
    n = on - start
    y[:n] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)
    return y


@cache
def _prepared(i):
    """FILES[i] ready to play, float32 mono at SR: started PRE before its onset (_from_onset), cut after the last 5 ms
    block within FLOOR dB of the loudest with a 10 ms fade, and peak-normalised to 1."""
    npy = _npy(i)
    if npy.is_file():
        x = np.load(npy)
    elif cached(i):
        x = _decode(i)
    else:
        inst = FILES[i][0]
        raise FileNotFoundError(
            f"{inst} is not cached ({_file(i).name} is missing in {CACHE}): run `python sampler.py fetch {inst}` "
            f"once ({_mb(inst):.1f} MB, CC0 1.0)"
        )
    y = _from_onset(np.asarray(x, float))
    w5 = C.sample_of(0.005, SR)
    m = -(-len(y) // w5)
    b5 = np.pad(y * y, (0, m * w5 - len(y))).reshape(m, w5).mean(1)
    end = min(len(y), (np.nonzero(b5 >= b5.max() * 10 ** (FLOOR / 10))[0][-1] + 1) * w5)
    y = y[:end]
    f = min(len(y), C.sample_of(0.01, SR))
    y[len(y) - f :] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(f) / f)
    return (y / np.abs(y).max()).astype(np.float32)


# ---- pitch: band-limited resampling ----


def _fast(n):
    """The smallest 2^a 3^b 5^c at or above n: numpy's FFT on such a size took 11 ms for 450,000 samples, against
    60 to 140 ms on sizes with a large prime factor (2026-11-10)."""
    best, p5 = 1 << (n - 1).bit_length(), 1
    while p5 < best:
        p35 = p5
        while p35 < best:
            q = p35
            while q < n:
                q *= 2
            best, p35 = min(best, q), p35 * 3
        p5 *= 5
    return best


def resample(x, r):
    """x played r times as fast (r > 1 raises the pitch by 12 * log2(r) semitones and shortens it), band-limited by
    FFT: the spectrum is cut (or zero-padded) at the lower Nyquist with a TAPER roll-off, so nothing aliases. The
    output length is round(N / r) for the padded input length N, so the ratio is exact to 0.5 / that length (0.02
    cents for a 1 s sound); at least 512 zeros after the end keep the wrap-around of the attack off the sound."""
    x = np.asarray(x, float)
    n = _fast(len(x) + 512)
    m = max(1, round(n / r))
    spec = np.fft.rfft(x, n)
    k = min(n, m) // 2 + 1
    out = np.zeros(m // 2 + 1, complex)
    k0 = int(k * (1 - TAPER))
    w = np.ones(k)
    w[k0:] = 0.5 + 0.5 * np.cos(np.pi * (np.arange(k - k0) + 1) / (k - k0))
    out[:k] = spec[:k] * w
    y = np.fft.irfft(out, m) * (m / n)
    return y[: math.ceil(len(x) / r)]


def _xcorr(seg, tpl):
    """Normalised correlation of tpl with every window of seg of its length (len(seg) - len(tpl) + 1 values)."""
    n, f = len(seg), len(tpl)
    size = 1 << (n + f).bit_length()
    c = np.fft.irfft(np.fft.rfft(seg, size) * np.conj(np.fft.rfft(tpl, size)), size)
    e = np.concatenate([[0.0], np.cumsum(seg * seg)])
    return c[: n - f + 1] / np.sqrt(np.maximum((e[f:] - e[:-f]) * (tpl @ tpl), 1e-30))


def _xfade(a, b, rho):
    """a fading into b over len(a) samples. The gain keeps the power constant for two signals correlated by rho:
    equal gain at rho 1 (a matched loop of one player), equal power at rho 0 (a section, whose phases never line up)."""
    u = 0.5 - 0.5 * np.cos(np.pi * (np.arange(len(a)) + 0.5) / len(a))
    d = 1 - u
    rho = min(1.0, max(0.0, float(rho)))
    return (a * d + b * u) / np.sqrt(u * u + d * d + 2 * rho * u * d)


def _loop_marks(y):
    """Where a sustained recording can be held, in samples: a (the attack is within 3 dB of the sustain level), b (the
    end of the last block within 6 dB of it: the recorded release starts there), and the loop [p, q) inside the
    longest steady stretch (smoothed 50 ms level within 4 dB of the sustain level), at least half that stretch long,
    whose return q -> p matches best (normalised correlation over XF, less 0.05 per dB of level step), with that
    correlation rho. The sustain level is the median of the 250 ms-smoothed blocks within 20 dB of the loudest."""
    w, f = C.sample_of(0.05, SR), C.sample_of(XF, SR)
    m = len(y) // w
    pw = (y[: m * w].reshape(m, w) ** 2).mean(1)
    db = 10 * np.log10(np.convolve(pw, np.ones(5) / 5, mode="same") + 1e-20)
    level = np.median(db[db >= db.max() - 20])
    a = int(np.argmax(db >= level - 3))
    b = int(np.nonzero(db >= level - 6)[0][-1])
    steady = np.abs(db - level) <= 4
    best, run = (a, a), None
    for k in range(a, b + 1):
        if steady[k]:
            run = (run[0], k) if run else (k, k)
            if run[1] - run[0] > best[1] - best[0]:
                best = run
        else:
            run = None
    ra, q = best[0] * w, min((best[1] + 1) * w - C.sample_of(0.1, SR), (b + 1) * w)
    lo = ra + f
    hi = max(lo, q - max(C.sample_of(0.3, SR), (q - ra) // 2))
    # a steady stretch too short to loop: loop the second half of whatever is there
    if q - hi <= f:
        q = max(q, 4 * f)
        lo = hi = max(f, q // 2)
    r = _xcorr(y[lo - f : hi], y[q - f : q])
    lvl = np.array([db[min(m - 1, p // w)] for p in range(lo, hi + 1)])
    k = int(np.argmax(r - 0.05 * np.abs(lvl - db[min(m - 1, q // w)])))
    return {"a": a * w, "b": (b + 1) * w, "p": lo + k, "q": q, "rho": float(r[k])}


@lru_cache(maxsize=64)
def _shifted(i, r, cut=None):
    """FILES[i] prepared and resampled by r (float32), with its loop marks when it is a sustain. cut: resample only
    the first cut samples (a damped decay never plays the rest), their last 10 ms faded so the cut does not ring."""
    y = _prepared(i)
    if cut is not None and cut < len(y):
        y = np.array(y[:cut], float)
        f = C.sample_of(0.01, SR)
        y[cut - f :] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(f) / f)
    if r != 1.0:
        y = resample(y, r).astype(np.float32)
    marks = (
        _loop_marks(np.asarray(y, float))
        if INSTRUMENTS[FILES[i][0]]["kind"] == "sustain"
        else None
    )
    return y, marks


def _held(y, mk, n):
    """The first n samples of y held on: y itself to the loop end q, then [p, q) again and again, each return to p
    crossfaded over XF (the crossfaded return is the same every time, so it is built once)."""
    p, q, f = mk["p"], mk["q"], C.sample_of(XF, SR)
    if n <= q:
        return y[:n]
    ret = _xfade(y[q - f : q], y[p - f : p], mk["rho"])
    head = np.concatenate([y[: q - f], ret])
    unit = np.concatenate([y[p : q - f], ret])
    reps = -(-(n - len(head)) // len(unit))
    return np.concatenate([head] + [unit] * max(0, reps))[:n]


def _sustain(y, mk, dur):
    """A sustain held dur seconds, then released: spliced into its own recorded release (the stretch from b - SEEK to
    b that best matches the held sound's last XF, crossfaded), or faded out over REL when dur ends in the attack."""
    f = C.sample_of(XF, SR)
    d = C.sample_of(dur, SR)
    if d < mk["a"] + f or d < 2 * f:
        n = C.sample_of(REL, SR)
        s = np.array(_held(y, mk, d + n))
        k = len(s) - min(d, len(s))
        s[len(s) - k :] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(k) / max(1, k))
        return s
    s = _held(y, mk, d)
    hi = min(mk["b"], len(y) - 1)
    lo = min(hi, max(mk["a"] + f, mk["b"] - C.sample_of(SEEK, SR)))
    r = _xcorr(y[lo - f : hi], s[d - f : d])
    k = int(np.argmax(r))
    t0 = lo + k
    return np.concatenate(
        [s[: d - f], _xfade(s[d - f : d], y[t0 - f : t0], r[k]), y[t0:]]
    )


def _decay(y, dur, damp):
    """A struck or plucked sound ringing for dur seconds, then damped (exp(-t / damp) for 6 time constants, the last
    3 ms faded to 0); the whole recording when dur is None or longer than it."""
    d = len(y) if dur is None else C.sample_of(dur, SR)
    if d >= len(y):
        return np.array(y)
    tail = np.array(y[d : d + C.sample_of(6 * damp, SR)])
    tail *= np.exp(-np.arange(len(tail)) / (damp * SR))
    f = min(len(tail), C.sample_of(0.003, SR))
    tail[len(tail) - f :] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(f) / max(1, f))
    return np.concatenate([y[:d], tail])


def _seed_int(seed):
    return (
        int(seed)
        if isinstance(seed, (int, np.integer))
        else zlib.crc32(str(seed).encode())
    )


def _pick(inst, key, vel, seed):
    """(FILES index) for key: the layer nearest ceil(vel * the instrument's layer count), then a round robin chosen
    from the call's own arguments and seed, so consecutive seeds always alternate (seed=i for note i)."""
    layers = BY[inst][key]
    top = (
        max(max(v) for v in BY[inst].values()) if isinstance(key, int) else max(layers)
    )
    want = min(top, max(1, math.ceil(vel * top)))
    layer = min(layers, key=lambda v: (abs(v - want), v))
    ix = layers[layer]
    base = zlib.crc32(f"{inst}|{key}|{layer}".encode())
    return ix[(base + _seed_int(seed)) % len(ix)]


def _vel(vel):
    if not 0 < vel <= 1:
        raise ValueError(f"vel {vel} outside (0, 1]")
    return vel**VEL_CURVE


def note(inst, midi, dur, vel=0.8, seed=0):
    """inst playing MIDI note midi (a float plays between the keys) for dur seconds, as a mono float array at SR whose
    attack starts at sample 0. From the recording nearest in pitch, resampled to the exact pitch (its measured tuning
    included). A decay instrument rings and is damped at dur (None: rings out); a sustain is held for dur, looped from
    its steady part when dur outlasts the recording, then released through its own recorded release, which starts
    within SEEK of dur. vel picks the dynamic layer and sets the peak (vel ** VEL_CURVE); seed picks the round robin."""
    spec, gain = _spec(inst), _vel(vel)
    if spec["kind"] == "hit":
        raise ValueError(f"{inst} is unpitched: use sampler.hit({inst!r})")
    if dur is not None and dur <= 0:
        raise ValueError(f"dur {dur} must be positive")
    if not any(lo <= midi <= hi for lo, hi in spans(inst)):
        have = ", ".join(
            f"{note_name(a)} ({a}) to {note_name(b)} ({b})" for a, b in spans(inst)
        )
        raise ValueError(f"{inst} plays {have}, not {midi}")
    _, key = min(_pitches(inst), key=lambda pk: (abs(midi - pk[0]), pk[0]))
    i = _pick(inst, key, vel, seed)
    r = 2 ** ((midi - key - FILES[i][2] / 100) / 12)
    cut = None
    if spec["kind"] == "decay" and dur is not None:
        # a damped note needs (dur + 6 damp) s of the recording, plus 50 ms past the faded cut; the power of two
        # above that lets notes of nearby lengths share one resampled copy
        need = C.sample_of((dur + 6 * spec["damp"]) * r + 0.05, SR)
        cut = 1 << (need - 1).bit_length()
    y, mk = _shifted(i, round(r, 12), cut)
    y = np.asarray(y, float)
    if spec["kind"] == "decay":
        out = _decay(y, dur, spec["damp"])
    else:
        out = np.array(y) if dur is None else _sustain(y, mk, dur)
    return _from_onset(out) * gain


def hit(inst, variant=None, vel=0.8, seed=0):
    """An unpitched hit of inst, whole (it rings out), as a mono float array at SR whose attack starts at sample 0.
    variant: one of variants(inst), the first when None. vel picks the layer and sets the peak; seed the round robin."""
    if _spec(inst)["kind"] != "hit":
        raise ValueError(f"{inst} is pitched: use sampler.note({inst!r}, midi, dur)")
    gain, vs = _vel(vel), variants(inst)
    variant = vs[0] if variant is None else variant
    if variant not in vs:
        raise ValueError(f"{inst} has variants {', '.join(vs)}, not {variant!r}")
    return np.asarray(_prepared(_pick(inst, variant, vel, seed)), float) * gain


def chord(inst, midis, dur, vel=0.8, strum=0.0, seed=0):
    """The notes in midis together, each at vel (the sum is not normalised), all released at dur. strum seconds
    between notes, in the order given (negative: last note first); note k takes seed + k, so no two share a robin."""
    order = list(midis) if strum >= 0 else list(midis)[::-1]
    step = abs(strum)
    parts = []
    for k, m in enumerate(order):
        sk = seed + k if isinstance(seed, (int, np.integer)) else f"{seed}.{k}"
        d = None if dur is None else max(dur - k * step, 0.02)
        parts.append((C.sample_of(k * step, SR), note(inst, m, d, vel, sk)))
    out = np.zeros(max(i + len(x) for i, x in parts))
    for i, x in parts:
        out[i : i + len(x)] += x
    return _from_onset(out)


def library(inst):
    """The LIBS key inst comes from (each instrument comes from one library)."""
    _spec(inst)
    return next(r[5] for r in FILES if r[0] == inst)


def variants(inst):
    """The variants an unpitched instrument has, the default first; [] for a pitched one."""
    if _spec(inst)["kind"] != "hit":
        return []
    return list(BY[inst])


def instruments():
    """One dict per instrument: name, family, kind, library, licence, spans (playable MIDI runs, [] when unpitched),
    range (note names), layers, variants, files, mb, cached (every file decoded in the cache), use."""
    out = []
    for name, spec in INSTRUMENTS.items():
        rows = [r for r in FILES if r[0] == name]
        sp = spans(name)
        out.append(
            {
                "name": name,
                "family": spec["family"],
                "kind": spec["kind"],
                "library": LIBS[library(name)]["title"],
                "licence": "CC0 1.0",
                "spans": sp,
                "range": ", ".join(f"{note_name(a)}-{note_name(b)}" for a, b in sp),
                "layers": max(r[3] for r in rows),
                "variants": variants(name),
                "files": len(rows),
                "mb": round(_mb(name), 2),
                "cached": not missing([name]),
                "use": spec["use"],
            }
        )
    return out


def credits(names):
    """The lines a delivery report prints under Media and credits for the instruments a score played, one per
    library: who made it, the licence, its homepage and the pinned commit the files came from. CC0 asks for no
    credit; VSCO 2 CE's readme asks for one with its homepage, so every line gives it."""
    names = sorted(set(names), key=list(INSTRUMENTS).index)
    for n in names:
        _spec(n)
    lines = []
    for lib, info in LIBS.items():
        used = [n for n in names if library(n) == lib]
        if used:
            lines.append(
                f"Sampled instruments ({', '.join(used)}): {info['title']} by {info['by']}, CC0 1.0, "
                f"{info['home']} (files from github.com/{info['repo']} at {info['commit'][:7]})"
            )
    return lines


# ---- demo: one 8-bar phrase, also rendered with the synth voices in the A/B check ----

DEMO_BPM = 100
# (bar, beat, instrument, MIDI notes, beats held, vel, gain, align); bars from 0, C - Am - F - G twice, then C
DEMO_CHORDS = [
    (48, (60, 64, 67)),
    (45, (57, 60, 64)),
    (41, (57, 60, 65)),
    (43, (59, 62, 67)),
]
DEMO_TUNE = [  # glockenspiel, from bar 2: (bar, beat, MIDI, beats)
    (2, 0, 88, 1), (2, 1, 86, 1), (2, 2, 84, 2), (3, 0, 83, 1), (3, 1, 86, 1), (3, 2, 79, 2),
    (4, 0, 84, 1), (4, 1, 88, 1), (4, 2, 91, 2), (5, 0, 93, 1), (5, 1, 91, 1), (5, 2, 88, 2),
    (6, 0, 89, 1), (6, 1, 93, 1), (6, 2, 96, 1), (6, 3, 93, 1), (7, 0, 91, 2), (7, 2, 86, 2),
]  # fmt: skip


def demo_score():
    """The demo phrase as events: cellos and violins hold each bar's chord, pizz plays eighths on it, the
    glockenspiel carries the tune from bar 3, the harp arpeggiates bars 5 to 8, and bar 9 lands on C."""
    ev = []
    for bar in range(8):
        root, triad = DEMO_CHORDS[bar % 4]
        ev.append((bar, 0, "cellos", (root,), 4, 0.6, 0.55, "pad"))
        ev.append((bar, 0, "violins", triad, 4, 0.45, 0.32, "pad"))
        for k, step in enumerate((0, 7, 12, 7, 0, 7, 12, 7)):
            v = 0.75 if k % 2 == 0 else 0.6  # the on-beat eighths a little harder
            ev.append((bar, k / 2, "pizz", (root + 12 + step,), 0.5, v, 0.42, "onset"))
        if bar >= 4:
            up = [m + 12 for m in triad]
            for k, m in enumerate([*triad, *up, up[1], triad[2]]):
                ev.append((bar, k / 2, "harp", (m,), 1.5, 0.6, 0.30, "onset"))
    for bar, beat, m, beats in DEMO_TUNE:
        ev.append((bar, beat, "glockenspiel", (m,), beats, 0.8, 0.36, "onset"))
    ev += [
        (8, 0, "cellos", (36, 48), 6, 0.6, 0.5, "pad"),
        (8, 0, "violins", (60, 64, 67, 72), 6, 0.45, 0.30, "pad"),
        (8, 0, "harp", (48, 55, 60, 64, 67, 72), 6, 0.7, 0.28, "onset"),
        (8, 0, "glockenspiel", (84, 96), 6, 0.8, 0.30, "onset"),
    ]
    return ev


def render_demo(play=None):
    """The demo phrase as one mono music bus at SR. play(inst, midis, dur, vel, k) makes each event's sound (k counts
    the events, for round robins); the default plays these instruments (the harp's last chord strummed)."""

    def sampled(inst, midis, dur, vel, k):
        strum = 0.03 if inst == "harp" and len(midis) > 2 else 0.0
        return chord(inst, midis, dur, vel, strum, seed=k)

    play = play or sampled
    beat = 60 / DEMO_BPM
    bus = np.zeros(C.sample_of(9 * 4 * beat + 6 * beat + 1.0, SR))
    for k, (bar, b, inst, midis, beats, vel, g, align) in enumerate(demo_score()):
        # half a second of lead-in, so the first pads' early start (align='pad') fits
        t = 0.5 + (bar * 4 + b) * beat
        snd = play(inst, midis, beats * beat, vel, k)
        S.place(bus, snd, t, g, align=align, stem="music")
    return S.reverb(bus, 0.1)


def demo(path, play=None):
    """render_demo written beside path as <stem>_raw.wav (audio.write_wav) and mastered into path (audio.master,
    -14 LUFS, -2 dBTP, 48 kHz). Returns audio.master's result."""
    import audio

    path = Path(path)
    raw = path.with_name(f"{path.stem}_raw.wav")
    audio.write_wav(raw, render_demo(play))
    return audio.master(str(raw), str(path))


def main(argv):
    try:
        if argv[:1] == ["fetch"]:
            return 1 if fetch(argv[1:] or None) else 0
        if argv[:1] == ["missing"]:
            gone = missing()
            for n in gone:
                print(f"{n:<13} {_mb(n):6.1f} MB  python sampler.py fetch {n}")
            print(
                f"INSTRUMENTS: {len(INSTRUMENTS) - len(gone)} of {len(INSTRUMENTS)} cached in {CACHE}"
            )
            return 1 if gone else 0
        if argv[:1] == ["demo"] and len(argv) == 2:
            res = demo(argv[1])
            st = res["rows"][0].status
            print(
                f"DEMO: {argv[1]} {res['I']:.2f} LUFS, {res['tp']:.2f} dBTP, Q805 {st}"
            )
            return 0 if st == "PASS" else 1
        if argv[:1] in ([], ["list"]):
            for d in instruments():
                what = d["range"] or "variants " + ", ".join(d["variants"])
                state = "cached" if d["cached"] else "missing"
                print(
                    f"{d['name']:<13} {d['family']:<15} {d['kind']:<8} {what:<29} layers {d['layers']} "
                    f"{d['files']:3d} files {d['mb']:6.1f} MB  {state}"
                )
            return 0
    except (ValueError, FileNotFoundError) as e:
        print(f"sampler.py: {e}")
        return 2
    print("usage: python sampler.py [list | fetch [names] | missing | demo out.wav]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
