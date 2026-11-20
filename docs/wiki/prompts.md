# Writing prompts

[Wiki home](README.md) · User guide

The left rail is the prompt. It feeds Generate, Person and Refine; Edit and Animate have their
own boxes and ignore it (see [The five modes](modes.md)).

## Prompt first

You write the subject in the **prompt box**. The dropdowns below it only **add** to what you
wrote, and every one of them is off (`—`) by default, so a fresh session sends exactly what you
typed. The composed prompt is shown live under the box, so you always see what goes to the model.

The prompt box and the preview stay pinned while the dropdowns scroll underneath.

## The modifiers

| Dropdown | Choices | Groups |
|---|---|---|
| Art style | 18 | Photographic · Digital & cinematic · Illustration · Traditional media |
| Setting | 29 | Studio & interior · Outdoor & nature · Urban · Fantasy & sci-fi |
| Lighting | 25 | Natural · Studio · Dramatic & cinematic · Coloured & artificial |
| Camera | 20 | Framing · Angle · Lens |
| Clothing | 36 | Casual · Formal · Costume & genre · Swim & active · Lingerie & revealing · Undressed |
| Pose | 30 | Standing · Seated & reclining · Action · Intimate |
| Focus | 14 | Portrait · Body · Explicit |
| Expression | 24 | Warm · Composed · Distressed · Sensual |
| Eye colour | 15 | Natural · Striking |

Explicit choices sit in their own clearly labelled group at the end of a list.

Some tips:

- **Film-stock styles are the strongest realism words** on photographic SDXL models:
  `35mm film photography`, `analog photograph`, `candid snapshot` change grain and colour, not
  just the label.
- **Genres are places, under Setting**: `in a neon-lit cyberpunk alley`, `in a gothic
  cathedral`. That way they don't fight the art style.
- **Lighting uses real photographic names** (`Rembrandt lighting`, `chiaroscuro`, `high key`),
  which models know from their training captions.
- Nothing stops two dropdowns contradicting each other (`moonlight` in a kitchen). Settle it in
  the prompt box.

## The order the prompt is built in

The parts are joined in a fixed order, your text first, because models weigh early words more:

your text → expression → eye colour → clothing (`wearing …`) → setting → lighting → art style →
camera → pose → focus

The order is fixed in code. It doesn't follow the order of the dropdowns on screen.

## The negative prompt

Generate and Refine have a negative prompt for models that use one (SD 1.5, SDXL, Z-Image base,
FLUX.2 Klein base). It is hidden for the models that ignore it.

## Saved prompts

The row under the Prompt heading saves and reloads prompts:

- **Save** asks for a name. Re-using a name overwrites it, after a confirm.
- Picking a saved prompt loads it. If the sidebar already holds something different, it asks
  first.
- **✕** deletes the selected one.

A saved prompt is the prompt box, the nine dropdowns and the negative prompt. It deliberately
doesn't include the model, LoRAs or numbers, so loading a prompt never swaps your model. Saved
prompts live on the server (`data/saved-prompts.json`), so they are the same in every browser and
survive a rebuild. A saved dropdown value that no longer exists comes back as `—`.

## What is remembered

Your current prompt, mode, model, LoRA stack and every mode's numbers are kept in the
browser's local storage and come back on the next visit, in that browser.
