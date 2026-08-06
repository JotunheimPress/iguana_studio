#!/usr/bin/env python3
"""
ComfyUI automation CLI.

Usage examples:
  python run.py text2img "a futuristic city at sunset"
  python run.py text2img "a cat on a rooftop" --width 768 --height 512 --steps 30
  python run.py img2img photo.jpg "make it look like a watercolor painting" --denoise 0.6
  python run.py video "a dragon flying over mountains, cinematic" --frames 16 --fps 8
  python run.py video "ocean waves at night" --frames 24 --format mp4
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import client
from workflows import text2img, img2img, video

COMFY_BASE = Path(os.environ.get("COMFY_BASE", "/home/user/ComfyUI"))
OUTPUT_DIR = Path(__file__).parent / "outputs"


def cmd_text2img(args):
    workflow = text2img.build(
        prompt=args.prompt,
        negative_prompt=args.negative,
        width=args.width,
        height=args.height,
        steps=args.steps,
        cfg=args.cfg,
        seed=args.seed,
        sampler=args.sampler,
    )
    paths = client.run_workflow(workflow, save_dir=OUTPUT_DIR)
    print(f"\nDone! {len(paths)} image(s) saved to: {OUTPUT_DIR.resolve()}")


def cmd_img2img(args):
    src = Path(args.image)
    if not src.exists():
        print(f"Error: image not found: {src}", file=sys.stderr)
        sys.exit(1)

    workflow = img2img.build(
        image_path=src,
        prompt=args.prompt,
        negative_prompt=args.negative,
        denoise=args.denoise,
        steps=args.steps,
        cfg=args.cfg,
        seed=args.seed,
    )
    paths = client.run_workflow(workflow, save_dir=OUTPUT_DIR)
    print(f"\nDone! {len(paths)} image(s) saved to: {OUTPUT_DIR.resolve()}")


def cmd_video(args):
    try:
        workflow = video.build(
            prompt=args.prompt,
            negative_prompt=args.negative,
            num_frames=args.frames,
            width=args.width,
            height=args.height,
            steps=args.steps,
            cfg=args.cfg,
            seed=args.seed,
            fps=args.fps,
            format=args.format,
            comfy_base=COMFY_BASE,
        )
    except RuntimeError as e:
        print(f"\n{e}", file=sys.stderr)
        sys.exit(1)

    paths = client.run_workflow(workflow, save_dir=OUTPUT_DIR, timeout=900)
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
    t.add_argument("--width", type=int, default=512)
    t.add_argument("--height", type=int, default=512)
    t.add_argument("--steps", type=int, default=25)
    t.add_argument("--cfg", type=float, default=7.0)
    t.add_argument("--seed", type=int, default=-1, help="-1 for random")
    t.add_argument("--sampler", default="euler")

    # ── img2img ───────────────────────────────────────────────────────────────
    i = sub.add_parser("img2img", help="Edit an existing image using a text prompt")
    i.add_argument("image", help="Path to source image")
    i.add_argument("prompt", help="Describe how to change the image")
    i.add_argument("--negative", default=img2img.DEFAULT_NEGATIVE)
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
    v = sub.add_parser("video", help="Generate a short video from a text prompt")
    v.add_argument("prompt", help="Describe the animated scene")
    v.add_argument("--negative", default=video.DEFAULT_NEGATIVE)
    v.add_argument("--frames", type=int, default=16, help="Number of frames (multiple of 8)")
    v.add_argument("--width", type=int, default=512)
    v.add_argument("--height", type=int, default=512)
    v.add_argument("--steps", type=int, default=20)
    v.add_argument("--cfg", type=float, default=7.5)
    v.add_argument("--seed", type=int, default=-1)
    v.add_argument("--fps", type=int, default=8)
    v.add_argument("--format", choices=["gif", "mp4"], default="gif")

    args = parser.parse_args()

    dispatch = {"text2img": cmd_text2img, "img2img": cmd_img2img, "video": cmd_video}
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
