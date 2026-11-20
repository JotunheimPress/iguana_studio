"""PuLID-FLUX (Person mode): graph shape, reference batching, LoRA order, validation.

    .venv/bin/python -m pytest -q tests
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import jobs  # noqa: E402
from workflows import pulid  # noqa: E402

DEV = "flux1-dev-Q8_0.gguf"


@pytest.fixture(autouse=True)
def no_upload(monkeypatch):
    """Stand in for ComfyUI's /upload/image: the server name is the local file name."""
    monkeypatch.setattr(pulid, "upload_image", lambda p: Path(p).name)


def test_single_reference_graph():
    wf = pulid.build(["a.png"], "a woman reading in a cafe", checkpoint=DEV, seed=7)
    apply = wf["p_apply"]["inputs"]
    assert wf["p_apply"]["class_type"] == "ApplyPulidFlux"
    assert apply["model"] == ["1", 0] and apply["image"] == ["pad_0", 0]
    assert (apply["weight"], apply["start_at"], apply["end_at"]) == (1.0, 0.0, 1.0)
    assert wf["5"]["class_type"] == "ModelSamplingFlux"
    assert wf["5"]["inputs"]["model"] == ["p_apply", 0]          # sampler sees the patched model
    assert wf["1"]["class_type"] == "UnetLoaderGGUF"
    assert wf["p_face"]["inputs"]["provider"] == "CPU"
    assert wf["p_model"]["inputs"]["pulid_file"] == pulid.PULID_MODEL
    assert wf["2"]["inputs"]["guidance"] == 3.5 and wf["6"]["inputs"]["steps"] == 20  # dev defaults
    assert wf["2"]["inputs"]["t5xxl"] == "a woman reading in a cafe"   # no trigger word
    assert wf["ref_0"]["inputs"]["image"] == "a.png"
    assert not any(k.startswith("batch_") for k in wf)


def test_references_are_padded_then_batched():
    wf = pulid.build(["a.png", "b.jpg", "c.webp"], "x", checkpoint=DEV, seed=1)
    for i in range(3):
        pad = wf[f"pad_{i}"]
        assert pad["class_type"] == "ResizeAndPadImage"
        assert pad["inputs"]["image"] == [f"ref_{i}", 0]
        assert pad["inputs"]["target_width"] == pad["inputs"]["target_height"] == pulid.REF_SIZE
    assert wf["batch_1"]["inputs"] == {"image1": ["pad_0", 0], "image2": ["pad_1", 0]}
    assert wf["batch_2"]["inputs"] == {"image1": ["batch_1", 0], "image2": ["pad_2", 0]}
    assert wf["p_apply"]["inputs"]["image"] == ["batch_2", 0]


def test_loras_sit_between_loader_and_pulid():
    wf = pulid.build(["a.png"], "x", checkpoint=DEV, seed=1,
                     loras=[{"name": "style.safetensors", "strength": 0.8}])
    assert wf["lora_0"]["inputs"]["model"] == ["1", 0]
    assert wf["lora_0"]["inputs"]["clip"] == ["1c", 0]
    assert wf["p_apply"]["inputs"]["model"] == ["lora_0", 0]
    assert wf["5"]["inputs"]["model"] == ["p_apply", 0]


def test_settings_reach_the_graph():
    wf = pulid.build(["a.png"], "x", checkpoint=DEV, seed=1, steps=28, guidance=4.0,
                     width=832, height=1216, weight=0.85, start_at=0.2, end_at=0.9)
    apply = wf["p_apply"]["inputs"]
    assert (apply["weight"], apply["start_at"], apply["end_at"]) == (0.85, 0.2, 0.9)
    assert wf["6"]["inputs"]["steps"] == 28 and wf["2"]["inputs"]["guidance"] == 4.0
    assert (wf["4"]["inputs"]["width"], wf["4"]["inputs"]["height"]) == (832, 1216)


@pytest.mark.parametrize("paths,kw", [
    ([], {}),
    (["a.png"] * (pulid.MAX_REFS + 1), {}),
    (["a.png"], {"start_at": 0.5, "end_at": 0.5}),
])
def test_rejects_bad_input(paths, kw):
    with pytest.raises(ValueError):
        pulid.build(paths, "x", checkpoint=DEV, **kw)


def test_params_for_maps_the_form():
    f = {"prompt": "p", "checkpoint": "", "width": 1024, "height": 1024, "steps": 20,
         "cfg": 3.5, "seed": -1, "weight": 0.9, "start_at": 0.1, "end_at": 1.0, "loras": []}
    params = jobs.params_for("pulid", f)
    assert params["checkpoint"] == pulid.DEFAULT_CHECKPOINT
    assert params["guidance"] == 3.5 and params["weight"] == 0.9
    with pytest.raises(ValueError):
        jobs.params_for("pulid", {**f, "start_at": 1.0})
