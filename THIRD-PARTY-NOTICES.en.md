# Third-Party Components and Source Notices

> [中文](THIRD-PARTY-NOTICES.md) · English

This file records the origin of this project (MTR Pathfinding Bot), the modifications made, and the third-party components distributed with the repository.
The project as a whole is licensed under **GPL-3.0-only**; the full text is in [LICENSE](LICENSE).

---

## I. Upstream Works and Modification Notice

Pursuant to GPLv3 Section 5(a): this project **has modified** the upstream works, and notice is hereby given.

The derivation chain of this project is:

```
CokeStudios/mtr-pathfinder  (GPL-3.0)
        │
        └──> Leonmmcoset/MTRPathQQBot  (GPLv3)
                    │
                    └──> 本项目：MTR 寻路 Bot  (GPL-3.0-only)
```

| Upstream | Address | License | What this project did with it |
|---|---|---|---|
| mtr-pathfinder | https://github.com/CokeStudios/mtr-pathfinder | GPL-3.0 | The pathfinding core (CSA pathfinding, data fetching, and image rendering in `mtr_pathfinder_v4.py`) comes from this work; this project made compatibility and robustness modifications |
| MTRPathQQBot | https://github.com/Leonmmcoset/MTRPathQQBot | GPLv3 | This project continues modifying on top of it |

**Modification time**: from November 2026.
**Modification content**: for the complete list see "This Round's Code Fix List" in [项目结构.en.md](项目结构.en.md); a summary follows:

- Fixed fatal issues such as Python 3.8 compatibility, subprocess encoding, and `libraqm.dll` loading
- Corrected wrong dwell time and station name lookups (timetable, train diagram)
- Refactored command parsing, external script invocation, and the logging mechanism (added `bot_commands.py`, `script_runner.py`, `logging_setup.py`)
- Fixed paths, configuration reading, and exception handling in the plugin layer
- Added automated tests in `tests/` (112 items)

This project is **not** an official version of any of the works above, and has no commercial endorsement.

---

## II. Third-Party Components Distributed with the Repository

The following files physically exist in this repository, and their respective licensing requirements must be retained upon redistribution.

### 1. Noto Sans Font Family

| Item | Content |
|---|---|
| Files | The 8 `.ttf` files under `botpy/examples/mtr_pathfinder_data/fonts/`<br>(NotoSans, NotoSansSC/TC/HK/JP/KR, NotoSansArabic, NotoSansThaiLooped) |
| License | SIL Open Font License 1.1 (OFL-1.1) |
| Copyright | Copyright The Noto Project Authors / Google Inc. |
| Redistribution requirements | The OFL-1.1 license text must be included; the fonts must not be sold separately; if the fonts are modified, the derivative fonts must not use the Reserved Font Name |
| Full license text | https://openfontlicense.org |

> These 8 fonts take up about 36 MB of the repository and are used to render multilingual station names in images; they are required runtime resources.

### 2. libraqm

| Item | Content |
|---|---|
| File | `botpy/examples/libraqm.dll` |
| License | MIT |
| Copyright | Copyright the libraqm contributors |
| Purpose | Pillow's complex text layout (`raqm_support.py` is responsible for preloading it before PIL is imported) |

### 3. FriBidi

| Item | Content |
|---|---|
| File | `botpy/examples/fribidi-0.dll` |
| License | LGPL-2.1-or-later |
| Copyright | Copyright the FriBidi project contributors |
| Purpose | Dependency of libraqm; bidirectional text (Arabic, Hebrew) layout |
| Redistribution requirements | LGPL requires that the license text be included and that recipients be able to replace the library (this project provides it as a standalone DLL that can be replaced by a file of the same name, which satisfies this requirement) |

---

## III. Dependencies Installed via pip (Not Distributed with the Repository)

The following dependencies are installed locally by the user via `pip install -r requirements.txt` and are not included in this repository;
each follows its own license, see the metadata of the corresponding package for details:

`qq-botpy` (MIT), `opencc`, `pillow`, `fonttools`, `requests`, `aiohttp`,
`sqlalchemy`, `pyyaml`, `selenium`, `networkx`.

Among them, `qq-botpy` is Tencent's official bot SDK (MIT); it is only called as a library, which does not constitute modification or redistribution of its code.

---

## IV. Objections

If you are the copyright holder of any of the works above and believe that this project's attribution, licensing, or redistribution is problematic,
please file an Issue or contact the repository maintainer directly, and we will address it as soon as possible.
