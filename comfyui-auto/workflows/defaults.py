"""Shared generation defaults and model-type helpers used across all workflow modules."""


# ── Model type detection ───────────────────────────────────────────────────────

def is_flux(checkpoint: str) -> bool:
    return "flux" in checkpoint.lower()

def is_sdxl(checkpoint: str) -> bool:
    if is_flux(checkpoint):
        return False
    name = checkpoint.lower()
    _SDXL_NAMES = {"crealism", "mirabilis", "juggernaut", "dreamshaper", "realvis", "pony"}
    return "xl" in name or "sdxl" in name or any(k in name for k in _SDXL_NAMES)


def default_size(checkpoint: str) -> tuple[int, int]:
    """
    Native training resolution for the checkpoint's family.

    Callers that have no explicit size should ask for this rather than assuming a
    fixed default: SDXL and FLUX are trained at 1024², and running them at 512²
    degrades output badly (soft, malformed, duplicated subjects).
    """
    return (1024, 1024) if is_sdxl(checkpoint) or is_flux(checkpoint) else (512, 512)


# ── Negative prompts ───────────────────────────────────────────────────────────

# General-purpose negative prompt — works across SD 1.5, SDXL, and Pony-based models.
# Weighted emphasis (1.2–1.4) on the most common failure modes.
NEGATIVE = (
    "(worst quality, low quality, normal quality:1.4), "
    "(jpeg artifacts, compression artifacts, blurry, grainy, noisy:1.2), "
    "(deformed, distorted, disfigured:1.3), "
    "bad anatomy, bad proportions, "
    "(extra limbs, missing limbs, floating limbs:1.2), "
    "(extra fingers, missing fingers, fused fingers, too many fingers:1.4), "
    "malformed hands, mutated hands, "
    "long neck, ugly face, bad face, "
    "watermark, signature, text, logo, username, "
    "out of frame, cropped, lowres, draft"
)

# Portrait / PhotoMaker — same base plus face-specific terms
NEGATIVE_PORTRAIT = (
    "(worst quality, low quality, normal quality:1.4), "
    "(jpeg artifacts, compression artifacts, blurry, grainy, noisy:1.2), "
    "(deformed, distorted, disfigured:1.3), "
    "bad anatomy, bad proportions, "
    "(extra limbs, missing limbs, floating limbs:1.2), "
    "(extra fingers, missing fingers, fused fingers, too many fingers:1.4), "
    "malformed hands, mutated hands, "
    "(bad face, ugly face, disfigured face:1.3), "
    "(asymmetric eyes, cross-eyed, uneven eyes:1.2), "
    "bad teeth, open mouth, "
    "watermark, signature, text, logo, "
    "out of frame, cropped, lowres"
)

# FLUX — guidance is baked into CLIPTextEncodeFlux; negative is not used
NEGATIVE_FLUX = ""

# AnimateDiff video — motion-specific additions
NEGATIVE_VIDEO = (
    "(worst quality, low quality, normal quality:1.4), "
    "(jpeg artifacts, compression artifacts, blurry, grainy:1.2), "
    "deformed, bad anatomy, "
    "watermark, signature, text, "
    "flickering, strobing, jitter, static, still frame, "
    "abrupt motion, inconsistent lighting, lens flare"
)
