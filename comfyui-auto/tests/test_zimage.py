"""Z-Image: detection, defaults and graph shape (no ComfyUI needed).

    .venv/bin/python -m pytest -q tests
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.models import config_for  # noqa: E402
from workflows import text2img, zimage  # noqa: E402
from workflows.defaults import base_of, default_size  # noqa: E402


def test_detection():
    for name in ("z_image_turbo_bf16.safetensors", "z_image_bf16.safetensors",
                 "zImageTurbo_v1.safetensors", "Z-Image-finetune.safetensors"):
        assert base_of(name) == "Z-Image", name
        assert default_size(name) == (1024, 1024)
    # Nothing that was classified before moves.
    assert base_of("flux1-schnell-Q4_K_S.gguf") == "FLUX"
    assert base_of("juggernautXL_ragnarokBy.safetensors") == "SDXL"
    assert base_of("absolutereality_v181.safetensors") == "SD 1.5"


def test_defaults():
    assert config_for("z_image_turbo_bf16.safetensors") == {
        "steps": 8, "cfg": 1.0, "w": 1024, "h": 1024, "neg": False}
    assert config_for("z_image_bf16.safetensors")["steps"] == 25
    assert config_for("z_image_bf16.safetensors")["neg"] is True


def test_text2img_graph():
    wf = text2img.build("a lighthouse", checkpoint="z_image_turbo_bf16.safetensors",
                        steps=8, cfg=1.0, seed=7)
    assert wf["1"]["class_type"] == "UNETLoader"
    assert wf["1c"]["inputs"] == {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2",
                                  "device": "default"}
    assert wf["1s"]["class_type"] == "ModelSamplingAuraFlow" and wf["1s"]["inputs"]["shift"] == 3.0
    ks = wf["6"]["inputs"]
    assert (ks["sampler_name"], ks["scheduler"], ks["steps"], ks["cfg"]) == ("res_multistep", "simple", 8, 1.0)
    assert ks["model"] == ["1s", 0]
    assert wf["4"]["class_type"] == "EmptySD3LatentImage"


def test_auto_steps():
    wf = zimage.build("x", checkpoint="z_image_bf16.safetensors", seed=1)
    assert (wf["6"]["inputs"]["steps"], wf["6"]["inputs"]["cfg"]) == (25, 4.0)


def test_loras_splice_between_loaders_and_consumers():
    wf = zimage.build("x", checkpoint="z_image_turbo_bf16.safetensors", seed=1,
                      loras=[{"name": "a.safetensors", "strength": 0.8},
                             {"name": "b.safetensors", "strength": 0.5}])
    assert wf["lora_0"]["inputs"]["model"] == ["1", 0]
    assert wf["lora_0"]["inputs"]["clip"] == ["1c", 0]
    assert wf["lora_1"]["inputs"]["model"] == ["lora_0", 0]
    assert wf["1s"]["inputs"]["model"] == ["lora_1", 0]        # shift sits after the chain
    assert wf["2"]["inputs"]["clip"] == ["lora_1", 1]
    assert wf["3"]["inputs"]["clip"] == ["lora_1", 1]
    assert wf["7"]["inputs"]["vae"] == ["1v", 0]               # VAE untouched
