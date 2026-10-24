# Emulsa

Film looks for your photos. Pick a look, see it on your photo instantly, tweak it, and export one photo or a whole folder.

![Emulsa main window](docs/screenshot.png)

Emulsa ships with 77 looks: Fuji film simulations, Kodak, Ilford and Cinestill stocks, Ricoh GR, Leica, Canon, Nikon and more. They started life as in-camera recipes for Sony cameras (from [Recipe Lab](https://github.com/voxivoid/recipe-lab-sony-pmca/tree/v1.7.0)). Emulsa turns each recipe into a colour grade a computer can apply to any photo, from any camera, and adds what a camera setting can't express: split toning, per-colour shifts, faded blacks and grain.

## What it does

- **Opens JPEG, PNG, TIFF and RAW** (Sony .ARW, Canon .CR2/.CR3, Nikon .NEF, Fuji .RAF, .DNG and others).
- **Shows every look on your own photo** in the looks list, so you can see the result before you click.
- **Adjusts any look** with exposure, contrast, highlights, shadows, faded blacks, temperature, tint, saturation, grain, vignette and black & white. Hold the `\` key to compare with the original.
- **Saves your own versions** as custom looks, and lets you star favourites.
- **Exports in batches** to JPEG, TIFF or PNG, at full size or resized. Your originals are never changed. EXIF data from JPEGs is kept.
- **Saves any look as a .cube LUT** for DaVinci Resolve, Premiere, Final Cut or OBS (grain and vignette aren't part of a LUT).

## Install

Download `EmulsaSetup-x.y.z.exe` from the [Releases](../../releases) page and run it. Windows 10 or 11, 64-bit.

## Keyboard

| Key | Does |
| --- | --- |
| `\` (hold) | Show the original photo |
| `F` | Add or remove the current look from favourites |
| `Ctrl+O` | Open a folder |
| `Ctrl+Shift+O` | Open individual photos |
| `Ctrl+E` | Export |
| Double-click a slider | Return it to the look's value |

## Run from source

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_emulsa.py
```

Works on Windows, macOS and Linux with Python 3.11 or newer.

## Build the installer

Install [Python](https://www.python.org/downloads/) and [Inno Setup 6](https://jrsoftware.org/isinfo.php), then double-click `build.bat`. It runs the tests, builds `dist\Emulsa\Emulsa.exe` with PyInstaller and packs it into `dist\EmulsaSetup-0.1.0.exe`.

On GitHub, the workflow in `.github/workflows/build.yml` does the same on every push. Push a tag such as `v0.1.0` and it attaches the installer to a release.

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
