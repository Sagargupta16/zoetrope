# run_all.py : proof -> frames -> audio -> encode. Run in stages: proof first, wait for approval, then the rest.
#   python run_all.py proof          proof.png, proof_keys.png and review_times.json
#   python run_all.py full [procs]   every frame (in parallel), audio, two-pass master, H.264 encode
import shutil, subprocess, sys
import engine as E

E.W, E.H, E.FPS, E.SS = 1920, 1080, 30, 1  # must be set before importing scenes
import scenes, proof, render, audio

OUT = "out.mp4"  # rename per video: {slug}_{aspect}_{length}s_v{n}.mp4
CRF = 18  # 20 for grain-heavy styles (formats.md)


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def main():
    if sys.argv[1] == "proof":
        proof.contact_sheet(
            "proof.png"
        )  # then open it in a session tab and ask for approval
        print(f"wrote proof.png ({len(proof.proof_times(scenes.SCHEDULE))} stills)")
        out, n_keys, n_shown = proof.key_sheet()
        print(f"wrote {out} ({n_shown} of {n_keys} key times) and review_times.json")
        return
    for old in (
        OUT,
        "mix.wav",
    ):  # a failed run must not leave the last good file to be reviewed
        if shutil.os.path.exists(old):
            shutil.os.remove(old)
    procs = int(sys.argv[2]) if len(sys.argv) > 2 else None
    print(f"wrote {render.render_parallel('frames', procs)} frames")
    audio.write_wav(
        "mix_raw.wav",
        audio.music(
            scenes.DURATION,
            getattr(scenes, "BPM", 120),
            cuts=[v[0] for v in list(scenes.SCHEDULE.values())[1:]],
        ),
    )
    ff = shutil.which("ffmpeg") or next(
        (
            p
            for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg")
            if shutil.os.path.exists(p)
        ),
        None,
    )
    if not ff:
        print("NO_FFMPEG: use rung b in the sandbox")
        return
    audio.master("mix_raw.wav", "mix.wav", ff)  # two-pass loudnorm to -14 LUFS, TP -1.5
    run(
        [
            ff,
            "-y",
            "-framerate",
            str(E.FPS),
            "-i",
            "frames/f%05d.png",
            "-i",
            "mix.wav",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            str(CRF),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(E.FPS),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            OUT,
        ]
    )
    print(f"wrote {OUT} ({shutil.os.path.getsize(OUT) / 1e6:.1f} MB)")


if (
    __name__ == "__main__"
):  # required: Windows re-imports this file in every render worker
    main()
