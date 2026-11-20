# Iguana Studio wiki

**Iguana Studio** is a prompt-first browser app for [ComfyUI](https://github.com/comfyanonymous/ComfyUI).
You type a prompt, pick a mode and press Generate: Iguana Studio builds the ComfyUI workflow
graph for you, sends it, shows its progress and puts the result in a gallery. There is no node
editor and nothing to wire.

It is a frontend for [AI Ecosystem](https://github.com/JotunheimPress/ai_ecosystem), which
runs ComfyUI as a shared backend, but it works with any ComfyUI it can reach. The page is
written in Python and runs in the browser. Releases are tagged `vX.Y.Z` on the repo.

This wiki has two halves. The **user guide** is for making images and videos. The **developer
guide** explains how the app is built and points into the detailed notes
([`comfyui-auto/CLAUDE.md`](../../comfyui-auto/CLAUDE.md)) that sit next to the code.

## User guide

| Page | What it covers |
|---|---|
| [Getting started](getting-started.md) | Requirements, installing, the first start, opening it from other devices, settings |
| [The five modes](modes.md) | Generate, Person, Refine, Edit and Animate: what each does and how to drive it |
| [Writing prompts](prompts.md) | The prompt sidebar, the modifier dropdowns, saved prompts, what is remembered |
| [Models](models.md) | Which model families work, the files each mode needs, per-model defaults, LoRAs |
| [Results and the gallery](gallery.md) | Results, the gallery, the full-screen viewer, sending images between modes, deleting |
| [Troubleshooting](troubleshooting.md) | Out of memory, lost jobs, models that ignore the prompt, and other problems seen so far |

## Developer guide

| Page | What it covers |
|---|---|
| [Architecture](architecture.md) | The container, the pytincture page, BFFs and plain routes, jobs and progress, security |
| [Workflow graphs](workflows.md) | How each mode's ComfyUI graph is built, LoRA splicing, adding a model family |
| [Contributing](contributing.md) | Running from a virtualenv, the tests, the CLI, releases, this wiki |

## Where else to look

- [`README.md`](../../README.md): the repo's front page.
- [`comfyui-auto/CLAUDE.md`](../../comfyui-auto/CLAUDE.md): the full working notes, with the
  measurements and the reasons behind each decision.
- [AI Ecosystem wiki](https://github.com/JotunheimPress/ai_ecosystem/wiki): running the
  backends, ComfyUI's models and custom nodes, the dashboard.
