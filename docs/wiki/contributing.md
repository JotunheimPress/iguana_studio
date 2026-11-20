# Contributing

[Wiki home](README.md) · Developer guide

## Running from a virtualenv

Iterate without rebuilding the image. Port 7862 is the container's, so use another one; ComfyUI
is reached on the port the host publishes (8188 with AI Ecosystem):

```bash
cd comfyui-auto
git clone https://github.com/WAwesome-AI/wa_pytincture_widgetset.git <wapyt>    # once, anywhere
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt pytest <wapyt>
PYTHON=$PWD/.venv/bin/python <wapyt>/scripts/dev_wheel.sh appcode   # the browser's wapyt wheel
COMFY_HOST=localhost PORT=7872 .venv/bin/python service.py          # http://127.0.0.1:7872/
```

## Tests

```bash
.venv/bin/python -m pytest -q tests
IGUANA_URL=http://127.0.0.1:7872 CHROME=<path to chrome> \
  uv run --with playwright python tests/smoke.py   # SMOKE_GENERATE=1 also runs a real job
```

- `test_prompt.py` checks the prompt composer against 200 golden outputs (`prompt_golden.json`).
- `test_zimage.py`, `test_flux2.py` and `test_pulid.py` check their graphs.
- `smoke.py` opens every mode in a browser, drives the viewer, and fails on any console error.

## The CLI

`run.py` is a thinner alternative for scripts: `text2img`, `img2img` and `video`, without Person
mode or the page's per-model tuning.

```bash
python run.py text2img "a cat on a windowsill, 35mm film photography"
python run.py img2img photo.png "make it snow" --denoise 0.55
python run.py video "she turns and smiles" --image photo.png   # omit --image: text to video
```

Lightning checkpoints need their settings passed explicitly: `--steps 6 --cfg 2`.

## Changes and releases

- Work on a branch and open a pull request into `main`; pull requests are squash-merged.
- Add the prompt-composer or graph test that covers your change, and run the smoke test for
  anything visible.
- **Releases** are tags, `vX.Y.Z` on `main`, with a GitHub release. AI Ecosystem installs and
  updates Iguana Studio to the newest tag, and its dashboard shows "vX.Y.Z available" when a
  newer one is out, so a fix reaches users only once it is tagged.
- [`comfyui-auto/CLAUDE.md`](../../comfyui-auto/CLAUDE.md) is the source of truth for how things
  work. Update it with the code, and update a page here when what a user sees changes.

## This wiki

`docs/wiki/` is the source, reviewed in pull requests with the code.
[`docs/publish-wiki.sh`](../../docs/publish-wiki.sh) publishes it to the GitHub wiki: page names
come from titles (`README.md` becomes Home), links out of `docs/wiki/` become links into the
repo on `main`, and it adds a sidebar and a footer naming the release and commit. Edits made on
GitHub are overwritten by the next publish.

```bash
docs/publish-wiki.sh --dry-run   # what would change
docs/publish-wiki.sh             # publish what is committed
docs/publish-wiki.sh --out DIR   # only build the pages, to read them
```

Run it after a pull request that changes `docs/wiki/` is merged, and after each release.
