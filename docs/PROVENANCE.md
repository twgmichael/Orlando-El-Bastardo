# Asset provenance & license register

Every acquired or salvaged asset gets an entry (acquisition policy:
docs/RESOURCES.md). Asset binaries live in gitignored `assets/`; this
register is the committed record.

| Asset (location under `assets/`) | Source | License | Tier | Notes |
|---|---|---|---|---|
| `characters/oeb_guy_characters.glb` (+`.usdc`) | Salvaged from project owner's original Infini-D works, 1996–2003 (`guy.dxf`, 2000) | Owner's original work — all rights held | 1 (no external license) | Converted 2026-07-06 by `tools/convert_legacy_dxf.py`; both `char_hero_v1` and `char_bartender_v1` derive from the same geometry |
| `mƒ jb5k/`, `mƒ Orlando El Bastardo/` (source folders) | Project owner's originals, 1996–2003 (Infini-D, classic Mac) | Owner's original work | 1 | Salvage review 2026-07-06; Infini-D scene files remain locked (`elmo`/`SI·D` format) |
| `Universal Base Characters[Standard]/` | Quaternius — quaternius.com (Standard/free edition) | **CC0 1.0 Universal** (public domain; `License_Standard.txt` in-folder) | 1 (CC0 default) | Added 2026-07-06. Superhero Male/Female full-body, skinned, UE-mannequin bone naming (`spine_01..03`, `upperarm_l`, …), glTF + FBX + PBR textures + rigged hairstyles. NO animations in this edition. Vendor README: prefer glTF (FBX scaling bug) — matches our pipeline. SOURCE (paid) edition exists with rigged .blends/engine projects. **Converted to packed GLB 2026-07-06** (`GLB/` in-pack; skin + 5 textures verified, 1.73 m) |

| `Ultimate Modular Sci-Fi - Feb 2021/` | Quaternius | **CC0 1.0** (`License.txt` in-folder) | 1 | Added 2026-07-06. 91 modular interior pieces (floor tiles, walls, doors, columns + details) — set-building kit. Source formats Blends/FBX/OBJ; **converted to GLB 2026-07-06** (`GLB/` in-pack, `tools/batch_convert_glb.py`, flat-color as designed) |
| `Ultimate Space Kit - March 2023/` | Quaternius | **CC0 1.0** (`License.txt` in-folder; NOTE: file header says "Ultimate Platformer Pack" — Quaternius copy-paste, license block itself is CC0 and the pack is distributed as CC0 on quaternius.com) | 1 | Added 2026-07-06. glTF included ✓. Vehicles (4 spaceships + 3 rovers — kitbash/reference donors for the JB5K rebuild), Environment (planets, domes, buildings), Items, Characters (stylized animal astronauts + mechs — style outliers, reference only). No animations in sampled files. **Converted to GLB 2026-07-06** (`GLB/` in-pack, 92 pieces from the glTF sources — atlas textures verified embedded) |

| `Universal Animation Library[Standard]/` | Quaternius | **CC0 1.0** (`License.txt` in-folder) | 1 | Added 2026-07-06. 43 clips in two GLBs (`UAL1_Standard.glb` in-place, `UAL1_Standard_RM.glb` root-motion-baked) on the SAME UE-mannequin skeleton as the Universal Base Characters — direct pairing, no retargeting. Includes `A_TPose` (rest reference), `Walk_Loop`, `Sitting_Enter/Exit`, `Sitting_Idle_Loop`, `Sitting_Talking_Loop`, `Idle_Loop`, `Idle_Talking_Loop`, `Interact`, and more |

| `sets/bar_scene_scifi.glb` (+`.usdc`) | Built 2026-07-06 by `tools/build_scifi_bar.py` from Ultimate Modular Sci-Fi pieces (CC0, above) + project layout data; carries over grey-box props/marks/cameras | CC0 components; assembly is project original | 1 | 8×8 m room: 4×4 floor grid, 2-module walls (front open for cameras), corner columns, backbar shelves + dressing; canonical node `set_bar_small_A`; kit-material alpha bug fixed at build time (forced opaque) |

Standing rules: CC0 preferred (Tier 1); anything else needs explicit records
here BEFORE use (Tier 2); attribution-heavy/share-alike/unclear = blocked
pending review (Tier 3). Downloads require human approval per the workflow
standing constraints.
