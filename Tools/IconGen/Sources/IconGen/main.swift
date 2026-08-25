import Foundation
import IconForge

// Draws the app icon. Run from the repo root:
//
//     swift run --package-path Tools/IconGen IconGen . --sheet   # judge the candidates
//     swift run --package-path Tools/IconGen IconGen .           # write the chosen one
//
// The tile - the gradient, the squircle, the light from above, the shadow, the
// 824/1024 grid every Dock icon sits on - comes from IconForge, which
// MacPhotoMaster-Swift draws its icon with too. Only the mark belongs to this
// app, which is what makes the two a family without a copied PNG drifting
// between them.

let args = CommandLine.arguments.dropFirst()
let root = URL(fileURLWithPath: args.first(where: { !$0.hasPrefix("--") }) ?? ".")

// The same teal MacPhotoMaster-Swift uses. The palette is the part that has to
// be identical across the family, so it comes from IconForge rather than being
// picked here; the letters are what tell this one apart.
let palette = Palette.teal

let chosen = drawPy(pyChosen)

if args.contains("--sheet") {
    // 64, 32 and 16 under each. An icon judged at 1024 alone is how you end up
    // with one that is mud in the Dock.
    let sheet = ContactSheet.render([
        .init(name: "Py aperture (current)", artwork: chosen),
        .init(name: "serpent coil (kept)", artwork: draw(serpentCoil)),
    ], palette: palette, columns: 2)
    let out = root.appendingPathComponent("icons/contact-sheet.png")
    try Icon.writePNG(sheet, to: out)
    print("wrote \(out.path)")
} else {
    let icon = Icon.render(side: 1024, palette: palette, shaped: true, artwork: chosen)

    // The source scripts/make_icns.sh sips down into resources/AppIcon.icns for
    // the py2app bundle.
    try Icon.writePNG(icon, to: root.appendingPathComponent("icons/AppIcon-1024.png"))

    // The Dock icon a plain `uv run python main.py` gets: no bundle, so no
    // Info.plist to name an .icns, and Qt has to be handed the image itself.
    try Icon.writePNG(icon, to: root.appendingPathComponent("resources/AppIcon.png"))

    print("wrote the icon into \(root.standardizedFileURL.path)")
}
