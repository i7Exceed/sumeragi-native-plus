# Trophy System in Sumeragi Native+

Sumeragi Native+ includes a fully functional, offline trophy experience for **Sengoku Basara 4 Sumeragi** (PS4, `CUSA01159`), inspired by SpartanPort's trophy subsystem.

The trophy system runs directly from your own game dump and saves, providing both a **desktop launcher trophy manager** and an **in-game overlay with live unlock notifications and a browseable trophy list**.

---

## 1. How Trophy Detection Works

1. **Dynamic Package Discovery**:
   - The game runtime and launcher look for the trophy package in:
     - `sce_sys/trophy/trophy00.trp` inside your game folder, or
     - `sce_sys/trophy/trophy00.trp` inside your update folder (if an update is selected).
   - If an update contains its own trophy package, the update's package takes priority.
2. **Dynamic Trophy IDs & Count**:
   - The runtime dynamically scans the TRP archive header and entries table (`TROP###.PNG`).
   - Sengoku Basara 4 Sumeragi has **43 trophies** (IDs `0` through `42`). Unlike God of War III (35 trophies), the system dynamically accommodates any trophy count up to 128 without hardcoded limits.
3. **Local Icon Extraction**:
   - High-definition trophy icons (`TROP000.PNG`, `TROP001.PNG`, ...) are parsed and extracted locally from the TRP archive into memory.
   - No copyrighted artwork or game files are bundled with the software.

---

## 2. In-Game Trophy Experience

During gameplay, the runtime connects directly to the Vulkan GPU overlay:

- **Unlock Notification (Toast)**:
  - When you accomplish a trophy in Sengoku Basara 4 Sumeragi, an animated toast notification slides in from the top-right corner of the screen.
  - The notification displays the trophy icon, trophy title, description, and a gold border.
- **In-Game Trophy List**:
  - Press **`F8`** on your keyboard, or press **`R3 + R2`** on your gamepad at any time during gameplay to bring up the in-game trophy list.
  - Controls:
    - **Up / Down** (or `W` / `S` / D-Pad): Scroll through the trophy cards.
    - **Left / Right** (or `A` / `D` / Bumpers): Cycle filters (**All**, **Unlocked**, **Locked**).
    - **`F8` / `Esc` / `Insert` / `B` (Circle) / `A` (Cross)**: Close the trophy list and return immediately to gameplay.
- **Automatic Platinum**:
  - In accordance with PlayStation system contracts, unlocking all non-platinum trophies automatically grants Trophy ID `0` (Platinum Trophy).

---

## 3. Storage and Persistence

| Item | Location | Description |
| :--- | :--- | :--- |
| **Progress State** | `user/trophies.dat` | 16-byte bitmask (4 x 32-bit unsigned integers) tracking unlocked trophy IDs. |
| **Backup State** | `user/trophies.dat.bak` | Automatic backup created whenever you choose to reset progress in the launcher. |
| **Custom Texts** | `user/trophy_texts.txt` | UTF-8 text file holding custom names, descriptions, and UI label overrides. |

> [!NOTE]
> The runtime environment variable `SPARTAN_USER_DIR` (or `SPARTAN_GPU_USER_DIR`) guarantees that the launcher and runtime both read and write to the same `user/` folder.

---

## 4. Customizing Names and Descriptions

Because official PS4 trophy metadata files (`.ESFM`) inside `trophy00.trp` are encrypted, Sumeragi Native+ uses neutral fallbacks (`Trophy #0`, `Trophy #1`, ...) by default.

You can easily supply your own trophy names, descriptions, and UI overrides using `user/trophy_texts.txt`:

```ini
# user/trophy_texts.txt
# UI Label overrides
@heading=Trophies
@notice=TROPHY UNLOCKED
@unlocked=UNLOCKED
@locked=LOCKED
@all=All trophies
@only_unlocked=Unlocked
@only_locked=Locked
@counter={} of {} unlocked
@hint=F8 / R3+R2: open or close the trophy list

# Trophy Overrides (ID = Name | Description)
0=Sengoku Basara 4 Sumeragi Master | Earn all trophies in Sengoku Basara 4 Sumeragi.
1=First Victory | Win your first battle in Battle Chronicle mode.
9=Legendary General | Complete the game on the hardest difficulty.
```

- User custom overrides in `user/trophy_texts.txt` are **strictly preserved** when switching languages or refreshing the launcher.
- Both UTF-8 with and without BOM are supported.

---

## 5. Launcher Trophy Manager

The Sumeragi Native+ Launcher features a dedicated **🏆 Trophies** window:

1. Click **🏆 Trophies** in the launcher's Utilities panel.
2. View:
   - **Progress readout & visual bar**: `X / 43 unlocked (Y%)`.
   - **Filter tabs**: View **All**, **Unlocked**, or **Locked** trophies.
   - **Trophy cards**: Extracted icon, trophy name, category tag (`[Platinum]`, `[Gold]`, `[Silver]`, `[Bronze]`), description, and unlock status badge.
   - **Language Toggle**: Switch between **English (EN)** and **Indonesian (ID)** labels.
3. **Reset Progress**:
   - Click **↺ Reset Progress** if you want to restart your trophy hunt from scratch.
   - A confirmation dialog will prompt you before creating a safe backup at `user/trophies.dat.bak`.

---

## 6. Known Limitations

- **Offline Only**: There is no connection to PlayStation Network (PSN) servers. Trophies are managed and stored strictly on your local PC.
- **Physical PS4 Sync**: Importing or synchronizing trophies earned on a physical PlayStation 4 console is not supported.
- **Encrypted Descriptions**: Official localized trophy texts inside `.ESFM` are encrypted; custom descriptions can be added through `user/trophy_texts.txt`.
