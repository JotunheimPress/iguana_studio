# Results and the gallery

[Wiki home](README.md) · User guide

## While a job runs

A running job shows what ComfyUI is doing (loading the model, sampling, decoding), a progress
bar with the current step, and an estimate of the time left. The estimate comes from how
fast the steps have actually gone, so it appears from the second step and corrects itself as the
run goes on. The bar covers sampling; loading the model comes before it and decoding (or
building the video) after it.

**Reloading the page during a job reconnects to it.** Long videos keep reporting past any
time limit on a single connection.

## Results

Finished images and videos appear under the controls and in the gallery. Click one to open
it full screen.

Every result and gallery tile has a **"⋯" menu**:

| Item | What it does |
|---|---|
| Download | Saves the file |
| Refine | Opens Refine with this image as the source |
| Edit | Opens Edit with this image as the source |
| Animate | Opens Animate with this image as the source |
| Delete | Deletes the file, after a confirm |

Refine, Edit and Animate aren't offered on videos.

## The gallery

The gallery strip under the results opens into a grid of everything in `outputs/`, newest
first, filling the whole workspace. It loads only the tiles in view, using small thumbnails, so
thousands of images scroll smoothly. Generating, or picking a source from it, closes it again.

## The viewer

Clicking a tile or a result opens the full-screen viewer:

| Key or action | Does |
|---|---|
| ← → | Previous / next |
| Home / End | First / last |
| + / − | Zoom in / out |
| 0 | Fit to the screen |
| 1 | Actual size (100%) |
| Wheel | Zoom at the cursor |
| Drag | Pan, once zoomed |
| Double-click | Fit ↔ 100% |
| Delete | Delete this file |
| Esc | Close |

Refine, Edit, Animate and Delete are buttons in the viewer too. Videos play with the usual
controls and can't be zoomed.

## Deleting

Delete removes the file (and its thumbnail) from `outputs/`, from the gallery and from the
results at once. It can't be undone.
