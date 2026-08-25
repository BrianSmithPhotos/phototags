# IconGen

Draws the app icon rather than storing it as a PNG nobody can adjust, so the
shape, the palette and the sizes stay one set of numbers.

    swift run --package-path Tools/IconGen IconGen .

That writes two files, because two things ask for the icon in two places:
`icons/AppIcon-1024.png`, which `scripts/make_icns.sh` sips down into
`resources/AppIcon.icns` for the `py2app` bundle, and `resources/AppIcon.png`,
which `phototags/app.py` hands to Qt so a plain `uv run python main.py` gets a
Dock icon too. Full rebuild steps are in `docs/PACKAGING.md`.

To judge a change:

    swift run --package-path Tools/IconGen IconGen . --sheet

which writes `icons/contact-sheet.png` - the icon at 1024 with 64, 32 and 16
under it. That row is the point of it: an icon judged at 1024 alone is how you
end up with one that is mud in the Dock. The sheet is gitignored; it is a thing
to look at, not an input.

## Why a Swift package in a Python repo

The tile - the teal, the continuous-corner squircle, the light from above, the
shadow, the 824/1024 grid every Dock icon sits on - comes from
[IconForge](https://github.com/BrianSmithPhotos/IconForge), which
MacPhotoMaster-Swift draws its icon with too. Only the mark is ours. That split
is what makes the two apps read as a family without a copied PNG drifting
between them, and it is worth a second toolchain in the repo to get: the
alternative is redrawing the tile in Pillow and watching the two slowly diverge.

Nothing at runtime touches this. It is a generator run by hand when the icon
changes, and its output is committed.

## The mark

The aperture, with `Py` for the language. `Aperture.swift` is the lens - a blade
ring, a hexagonal opening, and the six dark bars where one blade laps over the
next, all at the size MacPhotoMaster-Swift draws them, which is the family
resemblance. `PyMark.swift` is what this app adds: a quadrant taken out of the
ring at the lower right, and the letters set in the gap.

Four things there are load-bearing and look like fussiness until you change
them:

- The letters go **outside the opening**, not in it. The hexagon is 0.90R across
  the flats, and letters that fit inside it are a smudge at 32px and gone at 16.
  Out in the cut they run past the rim and are still legible at 32.
- The cut starts at a **seam, not an angle near one**. A seam is a chord, not a
  radius, so a radial cut beside a dark line leaves a wedge of white that widens
  towards the rim. `seamRay` is the one definition of where a seam lies, and both
  the stroking and the cut come off it.
- Where a bar stops is left to a **clip of the blade ring** - the disc with the
  hexagon taken out of it - so each bar is cut by the very edge it has to meet,
  at any size, rather than by an endpoint worked out per bar.
- The letters are a **path, not drawn text**. Text is placed by the font's
  metrics, which include space above the cap and below the descender that no one
  can see; converted to a path they can be sized by their own ink and given the
  same dark halo - stroked dark, then filled white - as everything else.

`Snake.swift` still holds the coiled snake this icon was drawn as first. Nothing
writes it; `--sheet` renders it beside the current mark so it stays comparable.
