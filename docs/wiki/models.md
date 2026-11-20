# Models

[Wiki home](README.md) · User guide

Iguana Studio has no models of its own: it uses what is installed in ComfyUI. With AI
Ecosystem, the ComfyUI install guide
([`comfyui/INSTALL.md`](https://github.com/JotunheimPress/ai_ecosystem/blob/master/comfyui/INSTALL.md))
lists the files and where they go, and its dashboard can download them.

## Model families

The family is worked out from the file name, and decides the graph, the defaults and which
controls show.

| Family | Recognised by | Loaded from | Defaults (size, steps, CFG) |
|---|---|---|---|
| SD 1.5 | anything not below | `models/checkpoints/` | 512², 25, 7 |
| SDXL | `xl` and a list of known names | `models/checkpoints/` | 1024², 25, 7 |
| FLUX.1 | `flux` | a GGUF in `models/unet/`, or a checkpoint | schnell 4 steps, guidance 1; dev 20, 3.5 |
| FLUX.2 | `flux2`, `flux-2` | `models/diffusion_models/` | Klein 4 steps, CFG 1; Klein base 20, 5; Dev 20, guidance 4 |
| Z-Image | `z-image`, `z_image` | `models/diffusion_models/` | Turbo 8 steps, CFG 1; base 25, 4 |

All are 1024² except SD 1.5. Some well-known checkpoints have their own tuned defaults: the
DreamShaper XL and RealVisXL **Lightning** ones get 6 steps at CFG 2. Any other SDXL Lightning or
Turbo checkpoint gets the family's defaults, which are far too many steps: set about 6 steps and
CFG 2 yourself.

**FLUX.1 as a GGUF** (with the [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) custom
node) keeps it small: `flux1-schnell-Q4_K_S.gguf` (6.8 GB) fits a 12 GB card next to other
work, while `flux1-dev-Q8_0.gguf` (12.7 GB, the one Person mode wants) needs a bigger card or a
Q4 dev quant instead. It also needs `clip_l`, `t5xxl_fp8_e4m3fn_scaled` and the `ae` VAE.

**Z-Image** needs `qwen_3_4b` in `models/text_encoders/` and the `ae` VAE. **FLUX.2 Klein**
uses the same `qwen_3_4b` (Klein 9B: `qwen_3_8b`) and `flux2-vae`.

## What each mode needs

| Mode | Files |
|---|---|
| Generate, Refine | any checkpoint or model of the families above |
| Person | the [ComfyUI_PuLID_Flux_ll](https://github.com/lldacing/ComfyUI_PuLID_Flux_ll) custom node (AI Ecosystem installs it, with the patch current ComfyUI needs); `flux1-dev-Q8_0.gguf`; `pulid_flux_v0.9.1` in `models/pulid/`; `EVA02_CLIP_L_336_psz14_s6B` in `models/clip/`; the facexlib weights in `models/facexlib/`; InsightFace `antelopev2` in `models/insightface/models/antelopev2/` |
| Edit | ComfyUI-GGUF; `flux1-kontext-dev-Q4_K_M.gguf` in `models/unet/`; `t5xxl_fp8_e4m3fn_scaled` and `clip_l` in `models/text_encoders/`; `ae` in `models/vae/` (about 12.5 GB in all) |
| Animate | `wan2.2_ti2v_5B_fp16` in `models/diffusion_models/`, `umt5_xxl_fp8_e4m3fn_scaled` in `models/text_encoders/`, `wan2.2_vae` in `models/vae/`. ComfyUI supports WAN natively: no custom node |

**Licences differ.** FLUX.1-dev, FLUX.2 Dev and Klein 9B, and InsightFace's `antelopev2` are
non-commercial. FLUX.1 schnell, FLUX.2 Klein 4B and Z-Image are Apache 2.0. Check each model's
card before using what you make with it commercially.

## LoRAs

A LoRA is a small add-on that nudges a model towards a style, a character or a concept. It
belongs to one family: an SDXL LoRA doesn't load onto SD 1.5, and a FLUX.1 LoRA doesn't load onto
FLUX.2. Put them in ComfyUI's `models/loras/`.

- Generate, Person and Refine take a **LoRA stack**; Edit and Animate don't.
- **Order matters**: each LoRA patches the model the one before it already patched. The rows
  are numbered and can be moved up and down.
- **Strength** runs from −1 to 2. Negative pushes away from the concept.
- **Most LoRAs need a trigger word** in the prompt. It's on the LoRA's model card; the app can't
  know it.
- A saved stack can name a file that has since been removed. It stays in the list, flagged, and
  is left out of the job instead of failing it.
