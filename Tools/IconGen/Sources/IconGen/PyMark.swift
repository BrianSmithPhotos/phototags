import AppKit
import CoreGraphics
import CoreText
import IconForge

/// The aperture with "Py" for the language. The blade ring, the hexagonal
/// opening and the seams are the same geometry MacPhotoMaster-Swift's icon
/// uses; the letters and the cut are what tell this app apart.
struct PyMark {
    var R: CGFloat = 0.325
    var shift: CGPoint = .zero
    /// Degrees of blade ring taken out, if any, for the letters to sit in.
    var cutFrom: CGFloat = 0
    var cutTo: CGFloat = 0
    /// Seams to cut along instead of `cutFrom`/`cutTo`, so the blades end on a
    /// dark line rather than at some angle near one. Negative for none.
    var cutSeam: Int = -1
    var cutToSeam: Int = -1
    /// Where the letters sit, in the ring's own polar terms.
    var pyAngle: CGFloat = 0
    var pyRadius: CGFloat = 0
    /// Width of the letters as a fraction of the ring's radius.
    var pyWidth: CGFloat = 0.80
    /// Nudge off that polar position, in units of the ring's radius.
    var pyNudge: CGPoint = .zero
    var rounded: Bool = false
    var barWeight: CGFloat = 0.11

    var isCut: Bool { cutTo != cutFrom || cutSeam >= 0 || cutToSeam >= 0 }
}

/// The letters as a path rather than drawn text, so they can be scaled to a
/// width, centred on their own ink, and given the same dark halo as everything
/// else. Text drawn straight would be sized by the font's metrics - which
/// include space above the cap and below the descender that no one can see.
private func lettering(_ string: String, rounded: Bool) -> CGPath {
    let base = NSFont.systemFont(ofSize: 256, weight: .bold)
    var font = base
    if rounded, let descriptor = base.fontDescriptor.withDesign(.rounded) {
        font = NSFont(descriptor: descriptor, size: 256) ?? base
    }
    let line = CTLineCreateWithAttributedString(
        NSAttributedString(string: string, attributes: [.font: font]))
    let path = CGMutablePath()
    for run in CTLineGetGlyphRuns(line) as? [CTRun] ?? [] {
        let count = CTRunGetGlyphCount(run)
        var glyphs = [CGGlyph](repeating: 0, count: count)
        var places = [CGPoint](repeating: .zero, count: count)
        CTRunGetGlyphs(run, CFRange(), &glyphs)
        CTRunGetPositions(run, CFRange(), &places)
        for i in 0..<count {
            guard let glyph = CTFontCreatePathForGlyph(font as CTFont, glyphs[i], nil) else { continue }
            path.addPath(glyph, transform: CGAffineTransform(translationX: places[i].x,
                                                             y: places[i].y))
        }
    }
    return path
}

private func fitted(_ path: CGPath, width: CGFloat, at p: CGPoint) -> CGPath {
    let box = path.boundingBoxOfPath
    let scale = width / box.width
    var t = CGAffineTransform(translationX: p.x, y: p.y)
        .scaledBy(x: scale, y: scale)
        .translatedBy(x: -box.midX, y: -box.midY)
    return path.copy(using: &t)!
}

/// The region taken out of the blades, as a slice reaching well past the rim so
/// it can be used as a clip.
///
/// Either edge can follow a seam rather than a radius. A seam is a chord, not a
/// radius, so a radial cut near a dark line leaves a wedge beside it that widens
/// towards the rim - white on the leading edge, leftover seam ink on the
/// trailing one. Running the cut along the seam's own line is the only way for
/// the blades to end *on* the line.
private func cutEdge(_ seam: Int, angle: CGFloat, centre c: CGPoint,
                     R: CGFloat, weight: CGFloat) -> (start: CGPoint, direction: CGPoint) {
    guard seam >= 0 else {
        let a = angle * .pi / 180
        return (c, CGPoint(x: cos(a), y: sin(a)))
    }
    let ray = seamRay(seam, centre: c, radius: R, weight: weight)
    // Off the seam by half its width, a quarter turn anticlockwise - the way the
    // blades sweep. Which edge of the dark band that lands on falls out of which
    // side of the seam the cut is on: the leading edge keeps the band, dressing
    // the blade it leaves behind, and the trailing edge takes it away.
    let half = R * weight / 2
    return (CGPoint(x: ray.start.x - ray.direction.y * half,
                    y: ray.start.y + ray.direction.x * half), ray.direction)
}

private func slice(centre c: CGPoint, radius R: CGFloat, mark: PyMark) -> CGPath {
    let far = R * 6
    let lead = cutEdge(mark.cutSeam, angle: mark.cutFrom, centre: c, R: R, weight: mark.barWeight)
    let trail = cutEdge(mark.cutToSeam, angle: mark.cutTo, centre: c, R: R, weight: mark.barWeight)
    let leadOut = CGPoint(x: lead.start.x + lead.direction.x * far,
                          y: lead.start.y + lead.direction.y * far)
    let trailOut = CGPoint(x: trail.start.x + trail.direction.x * far,
                           y: trail.start.y + trail.direction.y * far)

    let path = CGMutablePath()
    path.move(to: c)
    path.addLine(to: lead.start)
    path.addLine(to: leadOut)
    path.addArc(center: c, radius: far,
                startAngle: atan2(leadOut.y - c.y, leadOut.x - c.x),
                endAngle: atan2(trailOut.y - c.y, trailOut.x - c.x), clockwise: false)
    path.addLine(to: trailOut)
    path.addLine(to: trail.start)
    path.closeSubpath()
    return path
}

func drawPy(_ mark: PyMark) -> Artwork {
    { ctx, rect, palette in
        let centre = CGPoint(x: rect.midX + rect.width * mark.shift.x,
                             y: rect.midY + rect.width * mark.shift.y)
        let R = rect.width * mark.R
        let dark = palette.bottom.copy(alpha: 0.95)!

        let ring = CGMutablePath()
        ring.addEllipse(in: CGRect(x: centre.x - R, y: centre.y - R, width: R * 2, height: R * 2))
        ring.addPath(opening(centre: centre, radius: R))

        ctx.saveGState()
        if mark.isCut {
            let cut = CGMutablePath()
            cut.addRect(rect)
            cut.addPath(slice(centre: centre, radius: R, mark: mark))
            ctx.addPath(cut)
            ctx.clip(using: .evenOdd)
        }
        ctx.setFillColor(white(0.90))
        ctx.addPath(ring)
        ctx.fillPath(using: .evenOdd)

        // The bars stop where the blades do, cut by the edge they have to meet.
        ctx.addPath(ring)
        ctx.clip(using: .evenOdd)
        seams(ctx, centre: centre, radius: R, ink: dark, weight: mark.barWeight)
        ctx.restoreGState()

        let a = mark.pyAngle * .pi / 180
        let py = fitted(lettering("Py", rounded: mark.rounded), width: R * mark.pyWidth,
                        at: CGPoint(x: centre.x + R * (mark.pyRadius * cos(a) + mark.pyNudge.x),
                                    y: centre.y + R * (mark.pyRadius * sin(a) + mark.pyNudge.y)))
        ctx.setStrokeColor(dark)
        ctx.setLineWidth(R * 0.07)
        ctx.setLineJoin(.round)
        ctx.addPath(py)
        ctx.strokePath()
        ctx.setFillColor(white(0.93))
        ctx.addPath(py)
        ctx.fillPath()
    }
}

// MARK: - The mark

/// The aperture with a quadrant taken out at the lower right and the letters
/// set in the gap.
///
/// Inside the opening the hexagon caps them at 0.90R across the flats, which is
/// too small to read anywhere but at full size; out here they can run past the
/// rim. Both edges of the cut are seams rather than angles near them, so the
/// blades end on a dark line with neither a sliver of white beside the P nor a
/// stub of seam ink left above it.
let pyChosen = PyMark(
    R: 0.285, shift: CGPoint(x: -0.028, y: 0.028),
    cutSeam: 3, cutToSeam: 5, pyAngle: 315, pyRadius: 0.94, pyWidth: 1.24,
    pyNudge: CGPoint(x: -0.13, y: 0.09))
