# Changelog

## 0.5.0

- Zoom: scroll or pinch to zoom at the cursor, drag to move around, double-click to switch between Fit and 100%. The zoom button in the top bar has Fit, 50%, 100%, 200% and 400%. Zoomed-in views are rendered from the full-resolution photo, RAW included, so you see real detail with the look applied.
- Open one photo, several photos or a whole folder: from the Open photos menu, with the two buttons on the start screen, or by dropping them in. Clicking the drop area opens a folder.
- The taskbar now shows the Emulsa icon on Windows, sharp at every size.

## 0.4.0

- Update notices: once a day Emulsa checks GitHub for a newer release and shows a small notice with Download and What's new. Skip a version with ×, check by hand from ••• → Check for Updates…, or turn it off.
- The check only reads public release information; nothing is sent and nothing is downloaded without your click.

## 0.3.0

- New logo: a lowercase e made of silver-halide grains, with an `emulsa` wordmark set in Bricolage Grotesque.
- Startup animation: the e develops grain by grain, then the wordmark appears. Click to skip; turn it off in ••• → Startup Animation.
- New app icons for Windows, macOS and Linux, with a simplified e at small sizes so it stays sharp in the taskbar.
- `build.bat` finds Inno Setup installed "for me only", logs to `build.log` and self-tests the app before packaging.
- First release on the GitHub Releases page, with installers for all three systems.

## 0.2.0

- Look assistant: describe a look or attach reference photos, and Claude builds it on your photo (uses your own Anthropic API key).
- Redesigned interface with light and dark mode.
- macOS (.dmg) and Linux (AppImage) builds.
- Safety checks on every build: unit tests, a code security scan and a dependency vulnerability audit.

## 0.1.0

- First version: 77 film looks, JPEG and RAW, adjustments, favourites, custom looks, batch export and .cube export.
