"""LoRA stacking — injects a chain of LoraLoader nodes into a finished workflow.

A LoRA is not a standalone model: it is a small set of low-rank matrices merged into an
existing checkpoint's attention layers at load time. In a ComfyUI graph that means a
`LoraLoader` sits *between* the checkpoint and everything downstream of it — it takes
MODEL + CLIP in and hands back patched MODEL + CLIP. Stacking is just chaining: each
loader consumes the previous one's outputs.

Rather than have every builder thread LoRA wiring through its own node layout, this
rewrites a graph after the fact. Every builder that loads a checkpoint already publishes
the same two edges — `[ckpt, 0]` for MODEL and `[ckpt, 1]` for CLIP — so redirecting those
to the end of the LoRA chain is enough, whatever the rest of the graph looks like. That is
what makes one function cover text2img, img2img, pulid and both FLUX builders.

The VAE edge, `[ckpt, 2]`, is deliberately left alone: LoRAs do not patch the VAE.

Split graphs work too when the caller names the CLIP source: the GGUF FLUX path loads
MODEL from `UnetLoaderGGUF` and CLIP from a `DualCLIPLoader`, and a `LoraLoader` happily
takes its two inputs from two different nodes. `apply(..., clip_ref=["1c", 0])` covers
that. Kontext and video still don't take LoRAs — nothing here wires them.
"""

# Node ids are strings in the ComfyUI API format, and builders use plain numerals ("1",
# "2", …). Prefixing keeps injected ids from ever colliding with a builder's own.
_ID = "lora_{}"


def normalise(loras) -> list[dict]:
    """Coerce whatever arrived over the wire into a clean [{name, strength_model,
    strength_clip}] list, dropping entries with no name. Returns [] for None."""
    out = []
    for entry in (loras or []):
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        # One slider drives both strengths unless a caller distinguishes them. That is
        # what nearly every LoRA wants; splitting them is a power-user knob, not a default.
        strength = float(entry.get("strength", 1.0))
        out.append({
            "name": name,
            "strength_model": float(entry.get("strength_model", strength)),
            "strength_clip": float(entry.get("strength_clip", strength)),
        })
    return out


_SPLIT_LOADERS = ("UnetLoaderGGUF", "UNETLoader")


def apply(workflow: dict, loras, ckpt_node: str = "1", clip_ref: list | None = None) -> dict:
    """Splice a LoRA chain into `workflow` between the model/CLIP sources and their consumers.

    `ckpt_node` supplies MODEL at slot 0. CLIP comes from slot 1 of the same node for a
    checkpoint, or from `clip_ref` (e.g. `["1c", 0]`) when the model was loaded split.
    Mutates and returns the workflow. A falsy or all-empty `loras` is a no-op, so callers
    can pass it through unconditionally.
    """
    loras = normalise(loras)
    if not loras:
        return workflow
    cls = workflow.get(ckpt_node, {}).get("class_type")
    if clip_ref is None and cls != "CheckpointLoaderSimple":
        raise ValueError(
            f"LoRAs need a CheckpointLoaderSimple at node {ckpt_node!r}; found {cls!r}")
    if clip_ref is not None and cls not in _SPLIT_LOADERS + ("CheckpointLoaderSimple",):
        raise ValueError(f"LoRAs can't attach to a {cls!r} at node {ckpt_node!r}")

    model_src = [ckpt_node, 0]
    clip_src = list(clip_ref) if clip_ref is not None else [ckpt_node, 1]
    orig_clip = list(clip_src)
    chain = {}
    for i, lora in enumerate(loras):
        node_id = _ID.format(i)
        chain[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora["name"],
                "strength_model": lora["strength_model"],
                "strength_clip": lora["strength_clip"],
                "model": model_src,
                "clip": clip_src,
            },
        }
        model_src = [node_id, 0]
        clip_src = [node_id, 1]

    # Redirect the checkpoint's existing MODEL/CLIP consumers to the end of the chain.
    # This runs BEFORE the chain is merged in, so the loaders' own [ckpt, 0] / [ckpt, 1]
    # inputs are not rewritten out from under them — the first link must stay on the
    # checkpoint. Slot 2 (VAE) is skipped: LoRAs do not touch it.
    for node in workflow.values():
        for key, value in node.get("inputs", {}).items():
            if not (isinstance(value, list) and len(value) == 2):
                continue
            if value == [ckpt_node, 0]:
                node["inputs"][key] = list(model_src)
            elif value == orig_clip:
                node["inputs"][key] = list(clip_src)

    workflow.update(chain)
    return workflow
