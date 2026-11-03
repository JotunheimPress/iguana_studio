"""FLUX.2: detection, defaults and graph shape for Dev, Klein distilled and Klein base.

    .venv/bin/python -m pytest -q tests
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.models import config_for  # noqa: E402
from workflows import flux2, text2img  # noqa: E402
from workflows.defaults import base_of  # noqa: E402

KLEIN = "flux-2-klein-4b.safetensors"
KLEIN_BASE = "flux-2-klein-base-4b.safetensors"
KLEIN_9B = "flux-2-klein-9b.safetensors"
DEV = "flux2_dev_fp8mixed.safetensors"
FIXED = dict(text_encoder="te.safetensors", vae="vae.safetensors")   # no ComfyUI lookup


def test_detection_keeps_flux1_apart():
    for name in (KLEIN, KLEIN_BASE, KLEIN_9B, DEV, "FLUX.2-klein-4b-fp8.safetensors"):
        assert base_of(name) == "FLUX.2", name
    for name in ("flux1-schnell-Q4_K_S.gguf", "flux1-dev.safetensors",
                 "flux1-kontext-dev-Q4_K_M.gguf"):
        assert base_of(name) == "FLUX", name


def test_variants_and_defaults():
    assert (flux2.variant(DEV), flux2.variant(KLEIN), flux2.variant(KLEIN_9B)) == ("dev", "4b", "9b")
    assert config_for(KLEIN) == {"steps": 4, "cfg": 1.0, "w": 1024, "h": 1024, "neg": False}
    assert config_for(KLEIN_BASE)["steps"] == 20 and config_for(KLEIN_BASE)["neg"] is True
    dev = config_for(DEV)
    assert (dev["steps"], dev["cfg"], dev["neg"], dev["cfg_label"]) == (20, 4.0, False, "Guidance")


def test_pick_prefers_installed():
    prefs = ("a.safetensors", "b.safetensors")
    assert flux2.pick(prefs, ["b.safetensors"]) == "b.safetensors"
    assert flux2.pick(prefs, None) == "a.safetensors"       # ComfyUI unreachable
    assert flux2.pick(prefs, []) == "a.safetensors"         # nothing installed: ComfyUI says so


def test_klein_distilled_graph():
    wf = text2img.build("a fox", checkpoint=KLEIN, steps=4, cfg=1.0, seed=3)  # via the router
    assert wf["1c"]["inputs"]["type"] == "flux2"
    assert wf["3"]["class_type"] == "ConditioningZeroOut"
    assert wf["g"]["class_type"] == "CFGGuider" and wf["g"]["inputs"]["cfg"] == 1.0
    assert wf["s"]["inputs"] == {"steps": 4, "width": 1024, "height": 1024}
    assert wf["4"]["class_type"] == "EmptyFlux2LatentImage"
    assert wf["6"]["inputs"]["sigmas"] == ["s", 0] and wf["n"]["inputs"]["noise_seed"] == 3
    assert not any(k.startswith("_") for k in wf)


def test_klein_base_uses_negative():
    wf = flux2.build("a fox", "blurry", checkpoint=KLEIN_BASE, seed=1, **FIXED)
    assert wf["3"]["class_type"] == "CLIPTextEncode" and wf["3"]["inputs"]["text"] == "blurry"
    assert wf["g"]["inputs"]["cfg"] == 5.0 and wf["s"]["inputs"]["steps"] == 20


def test_dev_graph():
    wf = flux2.build("a fox", checkpoint=DEV, seed=1, **FIXED)
    assert wf["2g"]["class_type"] == "FluxGuidance" and wf["2g"]["inputs"]["guidance"] == 4.0
    assert wf["g"]["class_type"] == "BasicGuider" and "3" not in wf


def test_img2img_runs_requested_steps():
    wf = flux2.build_img2img(None, "a fox", checkpoint=KLEIN, denoise=0.5, seed=1,
                             server_image="up.png", **FIXED)
    assert wf["s"]["inputs"]["steps"] == 8                 # 4 steps / 0.5 → split keeps ~4
    assert wf["s"]["inputs"]["width"] == ["5s", 0]
    assert wf["sp"]["inputs"]["denoise"] == 0.5
    assert wf["6"]["inputs"]["sigmas"] == ["sp", 1] and wf["6"]["inputs"]["latent_image"] == ["5", 0]


def test_loras_splice():
    wf = flux2.build("x", checkpoint=KLEIN_BASE, seed=1, loras=[{"name": "l.safetensors"}], **FIXED)
    assert wf["lora_0"]["inputs"]["model"] == ["1", 0] and wf["lora_0"]["inputs"]["clip"] == ["1c", 0]
    assert wf["g"]["inputs"]["model"] == ["lora_0", 0]
    assert wf["2"]["inputs"]["clip"] == ["lora_0", 1] and wf["3"]["inputs"]["clip"] == ["lora_0", 1]
