Icon assets and conversion

Files:
- `app.svg` — general application icon (rounded square)
- `key.svg` — key-style icon
- `lock.svg` — lock-style icon

Converting to PNG/ICO

Recommended: install ImageMagick or `cairosvg` + `Pillow`.

ImageMagick example (Windows / PowerShell):

```powershell
# make sizes
magick convert assets/icons/app.svg -background none -resize 16x16 assets/icons/app-16.png
magick convert assets/icons/app.svg -background none -resize 32x32 assets/icons/app-32.png
magick convert assets/icons/app.svg -background none -resize 48x48 assets/icons/app-48.png
magick convert assets/icons/app.svg -background none -resize 256x256 assets/icons/app-256.png
# combine into .ico (Windows)
magick convert assets/icons/app-16.png assets/icons/app-32.png assets/icons/app-48.png assets/icons/app-256.png assets/icons/app.ico
```

Or with Python (requires `cairosvg` and `Pillow`):

```python
from cairosvg import svg2png
from PIL import Image
svg2png(url='assets/icons/app.svg', write_to='assets/icons/app-256.png', output_width=256, output_height=256)
svg2png(url='assets/icons/app.svg', write_to='assets/icons/app-48.png', output_width=48, output_height=48)
# combine to ICO
img48 = Image.open('assets/icons/app-48.png')
img256 = Image.open('assets/icons/app-256.png')
img48.save('assets/icons/app.ico', sizes=[(48,48),(256,256)])
```

Notes:
- These are simple SVG assets you can edit or hand off to a designer for refinement.
- If you want, I can generate PNG/.ico files here, but that requires installing conversion tools (ImageMagick or Python packages). I can proceed if you approve installing them in this environment.
