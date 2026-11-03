"""Shared generation defaults and model-type helpers used across all workflow modules."""


# ── Model type detection ───────────────────────────────────────────────────────

import re

def is_flux(checkpoint: str) -> bool:
    return "flux" in checkpoint.lower()

# Z-Image (Tongyi-MAI): z_image_turbo_bf16, z_image_bf16, "Z-Image" / "zImage" finetunes.
_ZIMAGE = re.compile(r"z[-_ ]?image", re.I)

def is_zimage(checkpoint: str) -> bool:
    return bool(_ZIMAGE.search(checkpoint)) and not is_flux(checkpoint)

def is_sdxl(checkpoint: str) -> bool:
    if is_flux(checkpoint) or is_zimage(checkpoint):
        return False
    name = checkpoint.lower()
    _SDXL_NAMES = {"crealism", "mirabilis", "juggernaut", "dreamshaper", "realvis", "pony"}
    return "xl" in name or "sdxl" in name or any(k in name for k in _SDXL_NAMES)


# Display order for grouped checkpoint lists, newest architecture first. Groups with no
# installed members are skipped by the frontend, so this order costs nothing when a family
# is absent.
BASES = ("Z-Image", "FLUX", "SDXL", "SD 1.5")


def base_of(checkpoint: str) -> str:
    """Which model family a checkpoint belongs to.

    The single source of truth for this classification. The frontend used to re-derive it
    from an `xl` substring test, which got `crealismTerraMirabilis` wrong — it is SDXL but
    has no "xl" in its name — and meant every new checkpoint had to be taught to two
    separate lists. /checkpoints now reports the base so there is only one.
    """
    if is_zimage(checkpoint):
        return "Z-Image"
    if is_flux(checkpoint):
        return "FLUX"
    if is_sdxl(checkpoint):
        return "SDXL"
    return "SD 1.5"


def default_size(checkpoint: str) -> tuple[int, int]:
    """
    Native training resolution for the checkpoint's family.

    Callers that have no explicit size should ask for this rather than assuming a
    fixed default: SDXL, FLUX and Z-Image are trained at 1024², and running them at 512²
    degrades output badly (soft, malformed, duplicated subjects).
    """
    big = is_sdxl(checkpoint) or is_flux(checkpoint) or is_zimage(checkpoint)
    return (1024, 1024) if big else (512, 512)


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

# Video — WAN 2.2. Deliberately does NOT suppress motion.
#
# The AnimateDiff-era list this replaces carried "abrupt motion", "jitter", "flickering"
# and "strobing": terms aimed at that model's temporal artifacts. Under WAN at CFG 5 they
# also push away from *deliberate* movement, because raising an arm is exactly "abrupt
# motion" next to ambient drift. Measured on a fixed seed and source image, swapping to
# this list raised mean frame-to-frame motion ~25% and was the difference between a hand
# landing on the shoulder it was told to touch and drifting to the chest.
#
# The anti-motion terms are kept on the POSITIVE side of the ledger instead: "static,
# still frame, frozen, motionless" as negatives ask for movement rather than forbidding it.
NEGATIVE_VIDEO = (
    "(worst quality, low quality:1.4), "
    "(jpeg artifacts, compression artifacts, blurry:1.2), "
    "deformed, bad anatomy, extra limbs, malformed hands, "
    "watermark, signature, text, "
    "static, still frame, frozen, motionless"
)
