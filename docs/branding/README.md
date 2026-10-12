# FRM black identity

Selected direction: FRAME, with separate wordmark and symbol.

- `frm-wordmark-black.png`: FRM letters only, transparent PNG, 1935 × 813 px.
- `frm-symbol-black.png`: opposing frame corners and Play symbol, transparent PNG, 1254 × 1254 px.

Created with the built-in image generation tool from Luca Auletta's supplied references. These are raster artwork masters, not SVG vectors or packaged operating-system icons. Version 0.3.2 integrates a white wordmark in the dark workspace and the black symbol on a light app-icon tile. Run `python scripts/build_branding.py` to regenerate the PNG, ICO and ICNS application assets. Original black masters remain unchanged.

Generation specifications:

1. Preserve the supplied FRM wordmark's thick angular letterforms, proportions, spacing and diagonal cuts. Use black lettering on genuine transparency; remove the background and include no symbol, container, shadows or extra text.
2. Preserve the internal frame-corner and Play shapes from the supplied icon. Recolor the symbol black, remove the rounded black container, and use genuine transparency with no letters, shadows or extra elements.
