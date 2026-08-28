#!/usr/bin/env python3
"""
ComfyUI automation CLI.

Usage examples:
  python run.py text2img "a futuristic city at sunset"
  python run.py text2img "a cat on a rooftop" --width 768 --height 512 --steps 30
  python run.py text2img "a portrait" --checkpoint absolutereality_v181.safetensors
  python run.py img2img photo.jpg "make it look like a watercolor painting" --denoise 0.6

Size defaults to the checkpoint's native resolution (1024² for SDXL/FLUX, 512² for
SD 1.5), so switching --checkpoint doesn't silently generate at the wrong scale.
Note the per-checkpoint step/CFG tuning in the web GUI is not replicated here —
lightning models still need an explicit --steps 6 --cfg 2.
  python run.py video "a dragon flying over mountains, cinematic" --length 49
  python run.py video "ocean waves at night" --image shore.png --length 81

The video commands drive WAN 2.2 TI2V 5B and need the weights from
ai-stack/comfyui/INSTALL.md §8. With --image the still is animated (image→video);
without it the clip is built from the prompt alone. --length is snapped to the 4n+1
grid the model's VAE requires.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import client
from workflows import text2img, img2img, video
from workflows.defaults import default_size

OUTPUT_DIR = Path(__file__).parent / "outputs"


def resolve_size(args) -> tuple[int, int]:
    """
    Size to generate at: an explicit --width/--height wins, otherwise the
    checkpoint's native resolution. Not a fixed 512 — the default checkpoint is
    SDXL, and 512² would quietly wreck every image.
    """
    w, h = default_size(args.checkpoint)
    return (args.width or w, args.height or h)


def cmd_text2img(args):
    width, height = resolve_size(args)
    workflow = text2img.build(
        prompt=args.prompt,
        negative_prompt=args.negative,
        checkpoint=args.checkpoint,
        width=width,
        height=height,
        steps=args.steps,
        cfg=args.cfg,
        seed=args.seed,
        sampler=args.sampler,
    )
    print(f"Model: {args.checkpoint} @ {width}x{height}")
    paths = client.run_workflow(workflow, save_dir=OUTPUT_DIR)
    print(f"\nDone! {len(paths)} image(s) saved to: {OUTPUT_DIR.resolve()}")


def cmd_img2img(args):
    src = Path(args.image)
    if not src.exists():
        print(f"Error: image not found: {src}", file=sys.stderr)
        sys.exit(1)

    # No width/height here: img2img derives its size from the source image.
    workflow = img2img.build(
        image_path=src,
        prompt=args.prompt,
        negative_prompt=args.negative,
        checkpoint=args.checkpoint,
        denoise=args.denoise,
        steps=args.steps,
        cfg=args.cfg,
        seed=args.seed,
    )
    print(f"Model: {args.checkpoint}")
    paths = client.run_workflow(workflow, save_dir=OUTPUT_DIR)
    print(f"\nDone! {len(paths)} image(s) saved to: {OUTPUT_DIR.resolve()}")


def cmd_video(args):
    common = dict(
        prompt=args.prompt,
        negative_prompt=args.negative,
        width=args.width,
        height=args.height,
        length=args.length,
        steps=args.steps,
        cfg=args.cfg,
        seed=args.seed,
        fps=args.fps,
        shift=args.shift,
    )
    if args.image:
        src = Path(args.image)
        if not src.is_file():
            print(f"\nNo such image: {src}", file=sys.stderr)
            sys.exit(1)
        workflow = video.build_i2v(image_path=src, **common)
    else:
        workflow = video.build_t2v(**common)

    # Matches the web app's VIDEO_TIMEOUT: a long clip that finished but got reported as
    # a timeout would burn the GPU time and throw the result away.
    paths = client.run_workflow(workflow, save_dir=OUTPUT_DIR, timeout=1800)
    print(f"\nDone! {len(paths)} video(s) saved to: {OUTPUT_DIR.resolve()}")


def main():
    parser = argparse.ArgumentParser(
        description="Automate ComfyUI workflows from the command line."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── text2img ──────────────────────────────────────────────────────────────
    t = sub.add_parser("text2img", help="Generate an image from a text prompt")
    t.add_argument("prompt", help="Describe the image you want")
    t.add_argument("--negative", default=text2img.DEFAULT_NEGATIVE, help="What to avoid")
    t.add_argument("--checkpoint", default=text2img.DEFAULT_CHECKPOINT,
                   help=f"Checkpoint filename (default: {text2img.DEFAULT_CHECKPOINT}). "
                        "A name containing 'flux' switches to the FLUX workflow.")
    t.add_argument("--width", type=int, default=None,
                   help="Default: the checkpoint's native size (1024 for SDXL/FLUX, else 512)")
    t.add_argument("--height", type=int, default=None, help="See --width")
    t.add_argument("--steps", type=int, default=25)
    t.add_argument("--cfg", type=float, default=7.0)
    t.add_argument("--seed", type=int, default=-1, help="-1 for random")
    t.add_argument("--sampler", default="euler")

    # ── img2img ───────────────────────────────────────────────────────────────
    i = sub.add_parser("img2img", help="Edit an existing image using a text prompt")
    i.add_argument("image", help="Path to source image")
    i.add_argument("prompt", help="Describe how to change the image")
    i.add_argument("--negative", default=img2img.DEFAULT_NEGATIVE)
    i.add_argument("--checkpoint", default=img2img.DEFAULT_CHECKPOINT,
                   help=f"Checkpoint filename (default: {img2img.DEFAULT_CHECKPOINT})")
    i.add_argument(
        "--denoise",
        type=float,
        default=0.75,
        help="0.0 = keep original, 1.0 = full redraw (default: 0.75)",
    )
    i.add_argument("--steps", type=int, default=25)
    i.add_argument("--cfg", type=float, default=7.0)
    i.add_argument("--seed", type=int, default=-1)

    # ── video ─────────────────────────────────────────────────────────────────
    v = sub.add_parser("video", help="Generate a short video, optionally from a still")
    v.add_argument("prompt", help="Describe the motion")
    v.add_argument("--image", help="Still to animate; omit for text-only video")
    v.add_argument("--negative", default=video.DEFAULT_NEGATIVE)
    v.add_argument("--length", type=int, default=49,
                   help=f"Frames, snapped to 4n+1 ({video.MIN_LENGTH}–{video.MAX_LENGTH})")
    v.add_argument("--width", type=int, default=video.NATIVE_W)
    v.add_argument("--height", type=int, default=video.NATIVE_H)
    v.add_argument("--steps", type=int, default=30)
    v.add_argument("--cfg", type=float, default=5.0)
    v.add_argument("--seed", type=int, default=-1)
    v.add_argument("--fps", type=int, default=24)
    v.add_argument("--shift", type=float, default=8.0)

    args = parser.parse_args()

    dispatch = {"text2img": cmd_text2img, "img2img": cmd_img2img, "video": cmd_video}
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
