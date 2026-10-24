# Emulsa

Film looks for your photos. Pick a look, see it on your photo instantly, tweak it, and export one photo or a whole folder.

![Emulsa with the look assistant open](docs/screenshot.png)

Emulsa ships with 77 looks: Fuji film simulations, Kodak, Ilford and Cinestill stocks, Ricoh GR, Leica, Canon, Nikon and more. They started life as in-camera recipes for Sony cameras (from [Recipe Lab](https://github.com/voxivoid/recipe-lab-sony-pmca/tree/v1.7.0)). Emulsa turns each recipe into a colour grade a computer can apply to any photo, from any camera, and adds what a camera setting can't express: split toning, per-colour shifts, faded blacks and grain.

## What it does

- **Opens JPEG, PNG, TIFF and RAW** (Sony .ARW, Canon .CR2/.CR3, Nikon .NEF, Fuji .RAF, .DNG and others).
- **Shows every look on your own photo** in the looks list, so you can see the result before you click.
- **Adjusts any look** with exposure, contrast, highlights, shadows, faded blacks, temperature, tint, saturation, grain, vignette and black & white. Hold the `\` key to compare with the original.
- **Saves your own versions** as custom looks, and lets you star favourites.
- **Exports in batches** to JPEG, TIFF or PNG, at full size or resized. Your originals are never changed. EXIF data from JPEGs is kept.
- **Saves any look as a .cube LUT** for DaVinci Resolve, Premiere, Final Cut or OBS (grain and vignette aren't part of a LUT).
- **Look assistant.** Click the button in the corner of the photo, describe a look ("warm 70s film, faded blacks") or attach a photo whose colours you like, and it builds the look on your photo. Undo it or save it as your own.
- **Light and dark mode**, following your system.

## Install

Download the file for your computer from the [Releases](../../releases) page.

| System | File | First launch |
| --- | --- | --- |
| Windows 10/11 (64-bit) | `EmulsaSetup-x.y.z.exe` | If Windows says it protected your PC, click **More info → Run anyway**. |
| macOS 11+ on Apple Silicon (M1 and newer) | `Emulsa-x.y.z-macOS-arm64.dmg` | Drag Emulsa to Applications. The first time, macOS blocks it: open **System Settings → Privacy & Security** and click **Open Anyway**. |
| Linux (x86-64) | `Emulsa-x.y.z-x86_64.AppImage` | `chmod +x Emulsa-*.AppImage` then run it. If it won't start, install `libxcb-cursor0` (Ubuntu/Debian) or `xcb-util-cursor` (Fedora/Arch). |

The warnings appear because the app isn't signed with a paid developer certificate yet. Intel Macs can run Emulsa from source (below).

## Updating

Your favourites, custom looks, settings and assistant key are kept when you update. They're stored in your user folder, not inside the app, so replacing the app never touches them.

1. **Get the new version** from the [Releases](../../releases) page. Between releases, the newest build is under [Actions](../../actions): open the latest run marked ✓ and download the file for your system under **Artifacts** (you need to be signed in to GitHub).
2. **Install it over the old one:**
   - **Windows:** close Emulsa and run the new `EmulsaSetup-x.y.z.exe`. It replaces the old version in place, so there's no need to uninstall first.
   - **macOS:** open the new `.dmg`, drag Emulsa to Applications and choose **Replace**.
   - **Linux:** replace the old `.AppImage` file with the new one and make it executable again (`chmod +x`).
3. **Check the version** in the ••• menu → **About Emulsa**.

**If you build Emulsa yourself:**

- **Cloned with git:** run `git pull`, then build again (`build.bat` on Windows) and run the new installer from the `dist` folder.
- **Downloaded a zip:** download the new zip from the green **Code** button and copy its files over your folder. You can keep `.venv`, `build` and `dist`. Then build again the same way. `build.bat` installs any new requirements on its own.

## The look assistant

The assistant runs on Claude, using **your own Anthropic API key**, so it costs you nothing beyond your own API usage, typically a few cents per message.

1. Get a key from the [Claude Console](https://platform.claude.com/).
2. Click the button in the corner of the photo and paste the key.
3. Describe a look or attach reference photos (up to 4 per message).

**Privacy:** when you press Send, a copy of your current photo (shrunk to 1024 px) and any reference photos you attached go to Anthropic to answer that message. Nothing is sent otherwise. Your key is stored in your system's keychain (Windows Credential Manager, macOS Keychain or the Linux Secret Service), never in Emulsa's settings file. If no keychain is available, the key is only kept until you close Emulsa. You can also set the `ANTHROPIC_API_KEY` environment variable instead.

Emulsa treats the assistant's answers as data: every setting is checked against a fixed list and clamped to a safe range, and replies are shown as plain text.

## Keyboard

On a Mac, use `Cmd` instead of `Ctrl`.

| Key | Does |
| --- | --- |
| `\` (hold) | Show the original photo |
| `F` | Add or remove the current look from favourites |
| `Ctrl+O` | Open a folder |
| `Ctrl+Shift+O` | Open individual photos |
| `Ctrl+E` | Export |
| `Ctrl+K` | Open the look assistant |
| `Ctrl+Shift+E` | Save the look as a .cube |
| Double-click a slider | Return it to the look's value |

## Run from source

```
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run_emulsa.py
```

Works on Windows, macOS (Apple Silicon and Intel) and Linux with Python 3.11 or newer.

## Build the apps

- **Windows:** install [Python](https://www.python.org/downloads/) and [Inno Setup 6](https://jrsoftware.org/isinfo.php), then double-click `build.bat`.
- **macOS:** `pip install -r requirements.txt pyinstaller && pyinstaller packaging/emulsa.spec && bash packaging/make_dmg.sh`
- **Linux:** `pip install -r requirements.txt pyinstaller && pyinstaller packaging/emulsa.spec && bash packaging/make_appimage.sh`

Every build can check itself with `Emulsa --self-test`.

On GitHub, `.github/workflows/build.yml` runs on every push. It first runs the safety checks: the unit tests, a security scan of the code ([bandit](https://bandit.readthedocs.io/)) and a check of every dependency against known vulnerabilities ([pip-audit](https://pypi.org/project/pip-audit/)). Then it builds and self-tests the Windows, macOS and Linux apps. Push a tag such as `v0.2.0` to attach all three to a release.

## How the looks work

Each look is a small set of numbers (see `emulsa/engine.py`, `DEFAULTS`). The engine runs those numbers through one pipeline on a 33×33×33 grid of colours, which gives a 3D LUT. Photos are graded by looking colours up in that LUT, so the preview, the export and a saved .cube file always match.

To add or tune a look, edit `emulsa/looks.py`:

- `RECIPES` holds the in-camera settings: Creative Style, saturation, contrast, white balance, DRO, exposure and Picture Effect.
- `CHARACTER` holds the film character layered on top: split toning, per-colour hue and saturation, faded blacks, grain.

Run the tests with `python -m unittest discover -s tests`.

## Thanks

Emulsa wouldn't exist without **[André Domingues (voxivoid)](https://github.com/voxivoid)** and his app [Recipe Lab](https://github.com/voxivoid/recipe-lab-sony-pmca). He worked out how to store film looks inside the Sony A6000 and built the 77 recipes this app starts from, testing them against reference frames on the camera itself. Thank you, André. If you shoot an older Sony that runs camera apps, use Recipe Lab on the camera, and consider [sponsoring his work](https://github.com/sponsors/voxivoid).

## Credits and licence

MIT licence; see [LICENSE](LICENSE). The recipe values come from Recipe Lab v1.7.0 by André Domingues, released under MIT.

Film and camera names describe the look each preset approximates. Emulsa isn't affiliated with or endorsed by Fujifilm, Kodak, Ilford, Cinestill, Ricoh, Leica, Hasselblad, Canon, Nikon, Panasonic, Olympus, Agfa, Polaroid or Sony.
