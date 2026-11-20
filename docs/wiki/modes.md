# The five modes

[Wiki home](README.md) · User guide

The tabs across the top pick the mode. Each mode has its own controls on the right and
remembers its own settings.

| Mode | What it does | Uses the prompt sidebar |
|---|---|---|
| [Generate](#generate) | Text to image | yes |
| [Person](#person) | Images of a specific person, from reference photos | yes |
| [Refine](#refine) | Image to image: redraw an existing image | yes |
| [Edit](#edit) | Change an image by instruction, keeping the rest | no: its own instruction box |
| [Animate](#animate) | Image to video | no: its own motion box |

Any result can be sent straight into Refine, Edit or Animate from its "⋯" menu (see
[Results and the gallery](gallery.md)).

## Generate

Text to image with any installed checkpoint: SD 1.5, SDXL, FLUX.1, FLUX.2 or Z-Image. The model
picker groups them by family.

- **Picking a model fills in its recommended size, steps and CFG** (for example 1024² for SDXL,
  512² for SD 1.5, 4 steps for FLUX.1 schnell). They're a starting point: change them freely.
  Reloading the page keeps your numbers; only picking another model replaces them.
- **FLUX** relabels CFG as **Guidance** and hides the negative prompt, which FLUX ignores. So do
  the distilled models (Z-Image Turbo, FLUX.2 Klein).
- **Seed** `-1` is random; any other number repeats an image.
- **LoRAs:** add a stack under the controls (see [Models](models.md#loras)).

## Person

Images of one specific person from **1 to 8 reference photos**, using PuLID on FLUX.1-dev. Drop
the photos on the dropzone; several photos of the same face are averaged.

- **The prompt describes the scene, not the face.** "standing on a pier at sunset, wearing a
  raincoat" is right; the face comes from the photos.
- **Likeness** (default 1.0): 0.8–1.0 keeps the face close; lower lets the prompt change more.
- **Identity from / until**: when in the sampling the face is applied. Starting at 0.1–0.3
  leaves composition, pose and style to the prompt and puts the face in afterwards.
- **Use FLUX.1-dev.** The picker lists FLUX.1 models only, dev first. Schnell is faster but
  loses most of the likeness, because PuLID was trained on dev.
- A photo without a detectable face is skipped. If none has one, the job still succeeds, with
  a stranger.
- Defaults: 1024², 20 steps, guidance 3.5.

## Refine

Image to image: the source image is partly re-noised and redrawn from your prompt.

- Upload a source, or pick one from the gallery (or send a result here from its "⋯" menu).
- **Denoise** is how much changes: low keeps the picture and touches up detail, high keeps little
  more than the composition.
- Takes the same models and LoRAs as Generate.

## Edit

Instruction-based editing with **Flux Kontext**: the picture is kept as context and your text is
read as an instruction, so whatever you don't mention stays as it was.

- **Write an instruction, not a description.** "change the background to a snowy mountain" or
  "make him wear a red baseball cap" works; "a man in a red cap, 8k, detailed" makes it redraw
  the whole picture.
- **Guidance** (default 2.5): about 1.5 for subtle changes, about 4 for forceful ones.
- No negative prompt, no denoise, no LoRAs. It ignores the prompt sidebar.

## Animate

Image to video with **WAN 2.2 TI2V 5B**: give it a source image and describe the motion.

- **Describe what happens**, for example "she raises her right hand and touches her shoulder".
  The sidebar is ignored: its pose would contradict the motion.
- **Length** (default 81 frames, about 3.4 s at 24 fps) is the biggest factor in whether an
  action finishes. At 49 frames the model often starts a movement and runs out of time. Lengths
  are snapped down to the 4n+1 grid the model needs (5 to 121); the label shows the real length.
- **Size**: 1280×704 is the model's native size and looks best; 960×544, 704×1280 (portrait)
  and 640×640 are faster.
- Defaults: 24 fps, 30 steps, CFG 5, shift 8.
- **Framing matters.** A tight head-and-shoulders crop has no arm in it, so there is nothing to
  raise. Pick a source that shows what should move.
- No LoRAs. Videos come out as MP4.
