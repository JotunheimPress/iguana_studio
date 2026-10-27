"""Per-checkpoint recommended settings, server-side (they lived in the classic page's JS).

The classification itself (FLUX / SDXL / SD 1.5) stays in workflows/defaults.py — the one
home for model rules. This adds what the UI stamps into the steps/CFG/size boxes on an
explicit model change: tuned numbers for known checkpoints, else the base's defaults.
"""
from __future__ import annotations

from workflows.defaults import base_of

# Tuned per file (carried over verbatim from the classic page's CKPT_CONFIGS).
CKPT_CONFIGS: dict[str, dict] = {
    "ponyDiffusionV6XL_v6StartWithThisOne.safetensors": {"steps": 28, "cfg": 7.0, "w": 1024, "h": 1024},
    "juggernautXL_ragnarokBy.safetensors":              {"steps": 35, "cfg": 7.0, "w": 1024, "h": 1024},
    "dreamshaperXL_lightningDPMSDE.safetensors":        {"steps": 6,  "cfg": 2.0, "w": 1024, "h": 1024},
    "realvisxlV50_v50LightningBakedvae.safetensors":    {"steps": 6,  "cfg": 2.0, "w": 1024, "h": 1024},
    "sd_xl_base_1.0.safetensors":                       {"steps": 25, "cfg": 7.0, "w": 1024, "h": 1024},
    "secuanceDreamDeliberate_v125Main.safetensors":     {"steps": 25, "cfg": 7.0, "w": 512,  "h": 512},
    "absolutereality_v181.safetensors":                 {"steps": 25, "cfg": 7.0, "w": 512,  "h": 512},
    "crealismTerraMirabilis_v2025Steps.safetensors":    {"steps": 25, "cfg": 7.0, "w": 1024, "h": 1024},
    "v1-5-pruned-emaonly-fp16.safetensors":             {"steps": 20, "cfg": 7.0, "w": 512,  "h": 512},
}


def config_for(name: str, base: str | None = None) -> dict:
    """{steps, cfg, w, h} to stamp on an explicit model change. For FLUX, `cfg` is guidance."""
    base = base or base_of(name)
    if base == "FLUX":
        # schnell is distilled to 4 steps and ignores guidance; dev wants 20 at 3.5.
        return ({"steps": 4, "cfg": 1.0, "w": 1024, "h": 1024} if "schnell" in name.lower()
                else {"steps": 20, "cfg": 3.5, "w": 1024, "h": 1024})
    if name in CKPT_CONFIGS:
        return dict(CKPT_CONFIGS[name])
    if base == "SDXL":
        return {"steps": 25, "cfg": 7.0, "w": 1024, "h": 1024}
    return {"steps": 25, "cfg": 7.0, "w": 512, "h": 512}
