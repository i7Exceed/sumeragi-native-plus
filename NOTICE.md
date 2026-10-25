# Sumeragi Native+
*The Sumeragi experience, evolved.*

An independent native PC runtime and launcher for **Sengoku Basara 4 Sumeragi** (PlayStation 4, CUSA01159).
The game's compiled x86-64 code executes directly on the host CPU; PlayStation 4 system libraries
are re-implemented function by function in native C/C++; and GPU draw calls and shaders are translated to Vulkan 1.3.

No game files, console keys, decrypted binaries, or DLC packages are distributed with this software.
Users must supply their own legally obtained game files dumped from their own PlayStation 4 console.

---

## Legal Disclaimer

- **Independent Community Project**: Sumeragi Native+ is an independent, community-developed open-source software project.
- **No Official Affiliation**: This project is not affiliated with, endorsed by, sponsored by, or an official product of **Capcom Co., Ltd.** or **Sony Interactive Entertainment**.
- **Compatibility Identification Only**: Game titles ("Sengoku Basara 4 Sumeragi"), company names, and platform references ("PlayStation 4", "PS4") are used strictly as factual nominative references to identify the software's intended technical compatibility.
- **No Proprietary Content**: This repository does not distribute game dumps, decrypted executables, ELF/SELF binaries, console firmware keys, console licenses (`.rif`/`.rap`), DLC payloads, or copyrighted game audio/visual assets.
- **User Responsibility**: Users are solely responsible for providing their own legally obtained game files from their own hardware.
- **Third-Party Rights**: All third-party software components and libraries remain governed by their respective licenses.
- **No Warranty**: Experimental features and performance optimizations are provided "as is" under the terms of the GNU General Public License v2.0 (or later), without warranty of any kind.

For a full breakdown of source provenance, component licensing, and risk audit classifications, see [docs/COPYRIGHT_AND_LICENSE_AUDIT.md](docs/COPYRIGHT_AND_LICENSE_AUDIT.md).

---

## Sumeragi Native+ Contributions (by [i7Exceed](https://github.com/i7Exceed), 2026)

Copyright (C) 2026 i7Exceed. Released under the GNU General Public License v2.0 or later.

- **Original Visual Identity & Branding**: Wholly original vector SVG crest (`assets/sumeragi_icon.svg`), logo wordmark (`assets/sumeragi_logo.svg`), and multi-resolution Windows icons (`launcher/sumeragi.ico`) created from abstract geometric Japanese technical heraldry without proprietary game assets.
- **Separate Game Update Overlay Subsystem** (`scripts/game_update.py`, `scripts/mods.py`, `scripts/patches.py`): Non-destructive mounting of separately extracted game update directories over base game dumps via dynamic NTFS junctions/symlinks.
- **Local DLC Discovery & Mounting Subsystem** (`scripts/dlc.py`, `src/runtime_content.c`, `src/runtime_offline.c`, `src/probe.c`): Safe discovery, entitlement validation, binary manifest generation (`B4ADD001`), AppContent enumeration (`sceAppContentGetAddcontInfoList`), and guest mounting (`/addcont0` ... `/addcont15`) for locally extracted add-on content without synthetic license bypasses.
- **Dynamic Title ID & Game Version Detection**: Automated parsing of `param.sfo` across base game dumps, update folders, and add-on DLCs.
- **Dual-Binary Backward Compatibility**: Seamless resolution and execution of both canonical (`sumeragi-core.exe`, `sumeragi-pad-mapper.exe`) and legacy (`basara4-core.exe`, `basara4-pad-mapper.exe`) runtime binaries and settings files (`sumeragi.ini` / `basara4.ini`).
- **Launcher Modernization**: Complete card-based layout overhaul, responsive sidebar, DLC management UI, and gamepad configuration workflows in `launcher/sumeragi_launcher.py`.
- **Release & Repository Compliance Validator** (`packaging/validate_release.py`): Automated static analysis ensuring no proprietary assets, logs, or unpermitted files enter packaging or git tracking.
- **Automated DLC Extraction Pipeline** (`tools/extract_dlc.py`): Clean batch processing and structuring of local DLC packages into valid entitlement directories.

---

## Basara 4 Native PC Contributions (by Razz, 2026)

Copyright (C) 2026 Razz. Released under the GNU General Public License v2.0 or later.

- **Basara 4 Runtime System Contracts** (`src/runtime_offline.c`): ~130 system functions specific to Basara 4, including kernel event flags, AppContent / PlayGo, offline NetCtl / NP / Http models, and dialog/screenshot services.
- **Software Ngs2 Audio Engine**: Multi-channel ATRAC9 streaming via LibAtrac9, PCM voice playback, submixers, and AudioOut integration.
- **Frame-Limiter Unlock Patch** (originally in `launcher/basara4_patches.py`, evolved into `launcher/sumeragi_patches.py`): Automated memory patch locating the internal frame limiter signature for high-refresh rates (>60 FPS).
- **Standalone Gamepad Mapper** (`tools/gamepad_mapper.c`): SDL3-based mapper tool for generic DirectInput and modern gamepads.
- **Core Launcher Foundations** (originally in `launcher/basara4_launcher.py`, evolved into `launcher/sumeragi_launcher.py`): Automatic preparation pipeline from `eboot.bin`, FSR 1 upscaling, RCAS sharpening, and anisotropic filtering controls.
- **In-Game Overlay Adaptation** (`gpu/shim/spartanport_overlay.cpp`): Game-specific overlay tabs and performance monitors.
- **LibAtrac9 Hardening** (`third_party/LibAtrac9/C/src/`): Buffer validation preventing crashes on corrupted ATRAC9 streams.
- **Packaging & Diagnostics**: Initial packaging scripts, `SPARTAN_AUDIO_DEBUG`, and diagnostic logging.

---

## Upstream Lineage & Third-Party Projects

Sumeragi Native+ is a legitimate fork building upon the following foundational open-source projects:

| Project / Component | Upstream Author(s) | Role & Lineage | License |
|---|---|---|---|
| **Basara 4 Native PC** | Razz | Direct upstream fork: Basara 4 system contracts, software Ngs2, initial launcher | GPL-2.0-or-later |
| **SpartanPort** (`gow3_pc`) | Felipe Prado | Base PC runtime architecture, probe loader, exception handling | GPL-2.0-or-later |
| **bloodborne_pc for Windows** | Supermedo (Mohammed Albarghouthi) | Windows MinGW/Clang porting harness | GPL-2.0-or-later |
| **bloodborne_pc** | deadinside28 | Original native PC porting architecture | GPL-2.0-or-later |
| **shadPS4 Video Core** | shadPS4 Team | PS4 GPU command translation, PM4 processing, GCN shader translation to SPIR-V/Vulkan, `aerolib` NID tables | GPL-2.0-or-later |
| **Video Core Fixes** | cuesta4 | Emulation blending, depth/stencil, and aliasing fixes | GPL-2.0-or-later |
| **LibAtrac9** | Alexander Barney | ATRAC9 audio decoding library | MIT |
| **FSR-Vulkan** | FireBurn / AMD | FidelityFX Super Resolution Vulkan implementation | MIT |
| **Dear ImGui** | Omar Cornut | In-game configuration overlay GUI | MIT |
| **Vulkan Memory Allocator** | Advanced Micro Devices, Inc. | Vulkan memory allocation management | MIT |
| **GCN Header Offsets** | Advanced Micro Devices, Inc. | AMD GCN register definitions | MIT |
| **sirit** | sirit contributors | SPIR-V assembly library | BSD-3-Clause |
| **magic_enum** | Daniil Goncharov | Compile-time enum reflection | MIT |
| **miniz** | Rich Geldreich | Deflate/Inflate compression library | MIT |
| **xbyak** | MITSUNARI Shigeo | JIT x86/x64 assembler library | 3-Clause BSD |
| **DejaVu Sans Font** | Bitstream / DejaVu Team | Overlay UI typeface (`DejaVuSans.ttf`) | DejaVu License |
| **SDL3** | Sam Lantinga & SDL contributors | Windowing, display, and gamepad abstraction | Zlib License |
| **FFmpeg** | FFmpeg Team | Video decoding and audio helper utilities | LGPL-2.1-or-later |

Files inherited from these projects retain their original copyright notices and license headers. Where this project has made modifications, change notices are documented in accordance with the applicable licenses.

---

## License Terms

The collective work is licensed under the **GNU General Public License, Version 2** or (at your option) any later version. See [LICENSE](LICENSE) for the full text.

Anyone receiving a binary release of Sumeragi Native+ is entitled to receive corresponding source code under the terms of the GNU GPL.
