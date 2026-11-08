# Emulsa website

The website for [Emulsa](https://github.com/ajr-alves/emulsa), film looks for your photos.

A static page served by GitHub Pages from this `gh-pages` branch at https://ajr-alves.github.io/emulsa/: `index.html`, `assets/site.css` and `assets/site.js`, with no build step.

- **Download links update themselves.** The page reads the latest release from the GitHub API and points each button at the right installer. If that request fails, the links already in the page are used.
- **The sample images are real Emulsa output.** Every photo in the demo and the looks grid was rendered with Emulsa's own engine (`emulsa/engine.py`). The photos are CC0 or public domain (credits in the page footer).
- **Light and dark** follow the visitor's system, using the same colours as the app.

The wordmark font is Bricolage Grotesque, under the SIL Open Font License (`assets/fonts/OFL.txt`).
