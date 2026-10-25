Sumeragi Native+ · The Sumeragi experience, evolved.
===================================================
An independent native Windows port runtime for Sengoku Basara 4 Sumeragi (PS4, CUSA01159).
Maintained by i7Exceed. Based on Basara 4 Native PC by Razz, SpartanPort, and shadPS4.
Free software under GNU GPL v2 or later. Complete notices: NOTICE.md.

DISCLAIMER
----------
Sumeragi Native+ is an independent, community-developed open-source project.
It is not affiliated with, endorsed by, sponsored by, or an official product of
Capcom Co., Ltd., Sony Interactive Entertainment, or any related entity.
Game and platform titles are used strictly for technical compatibility identification.
NO GAME FILES, PROPRIETARY PAYLOADS, DLC DATA, CONSOLE KEYS, OR EXECUTABLES ARE INCLUDED.
Users must supply their own legally obtained game files from their own PS4 console.

How to play
  1. Put your legally obtained game dump (the folder containing eboot.bin) in "game\",
     or press "Browse" in the launcher to select its location.
     Optional: Separately extracted game updates can be placed in "update\", and
     extracted add-on DLCs in "dlc\".
  2. Open "Sumeragi Native+.exe" and press PLAY. The first launch prepares the game image
     from eboot.bin (takes ~1 minute). It regenerates automatically if files change.
  "Play Sumeragi Native+.cmd" starts the game directly using the last saved settings.

Requirements
  Windows 10 (1903+) or 11, 64-bit.
  CPU with AVX / AVX2 instruction support.
  Graphics card supporting Vulkan 1.3 with up-to-date drivers.

Folder contents
  Sumeragi Native+.exe   Launcher: graphics, display, resolution, frame rate, controller & DLC
  bin\                   Runtime core (sumeragi-core.exe), pad mapper, and dependencies
  game\                  Your provided game dump (eboot.bin, sce_sys, sce_module, etc.)
  update\                Optional separate game update directory
  dlc\                   Optional extracted add-on DLC directory
  out\                   Prepared game image (generated automatically)
  user\                  Saves, shader cache, sumeragi.ini, last_run.log, prepare.log
  scripts\               Image preparation and linking pipeline scripts
  launcher\              Launcher source files and assets

Launcher options
  Display mode      Windowed, Borderless, Exclusive
  Window size       Native, 720p, 900p, 1440p, 1800p, 4K (base game renders at 1080p)
  Upscaling         Off, or AMD FidelityFX Super Resolution 1 (FSR 1)
  Frame limit       60 (default), 90, 120, 144, 165, 240, Unlimited
  VSync, sharpening (RCAS), anisotropic filtering 2x-16x
  Separate Update   Select custom update path with automated overlay merge
  Add-on DLCs       Discover and mount add-on content manifests automatically
  Trophies          View 43 trophies, progress bar, category tags, filters, and reset action
  Controls          Remap logical game actions (Cross, Circle, Square, Triangle, L1, R1, L3, R3, Options, D-pad)
  Controller        Map controller / Map sticks only / Reset mapping
  Credits           Displays NOTICE.md

In-game menu & Trophies
  Insert on keyboard, or R3 + L2 (RS + LT) on controller opens the in-game settings menu.
  F8 on keyboard, or R3 + R2 (RS + RT) on controller opens the in-game Trophy List.
  Trophy unlock notifications (toasts) appear automatically when trophies are earned.
  F12 takes a screenshot.
  L1/R1 or Q/E switches tabs.
  Detailed trophy documentation: docs/TROPHIES.md

Controller & Button Remapping
  XInput, DualShock 4, DualSense, and SDL-supported pads work out-of-the-box.
  Remap game buttons: click "Controls" in the launcher (supports live button capture and swapping).
  Other generic pads: use "Map controller" in the launcher to calibrate hardware buttons and axes.

Troubleshooting
  Attach user\last_run.log (and user\prepare.log if image preparation failed) to your report.
