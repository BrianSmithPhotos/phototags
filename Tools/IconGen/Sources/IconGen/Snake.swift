import CoreGraphics
import IconForge

/// A real coil: one band spiralling between two radii, tapering to a point at
/// the tail. Concentric rings are not a coil - the giveaway is that they have no
/// end, so the eye reads them as machined parts rather than as one animal. A
/// spiral has a tail tip somewhere, and putting that tip in the middle is what
/// makes the winding legible.
///
/// Parameterised from the tail (t = 0) to the head (t = 1), so `rTail` and
/// `rHead` decide which way it winds: outward for a snake whose head comes up on
/// the rim, inward for one whose head is raised in the centre.
struct Coil {
    var rTail: CGFloat
    var rHead: CGFloat
    var turns: CGFloat
    var band: CGFloat
    /// Where the body ends, in degrees.
    var headAngle: CGFloat
    /// +1 winds anticlockwise towards the head, -1 clockwise.
    var dir: CGFloat = -1
    /// How much of the run, in turns, is spent narrowing to the tail tip.
    var taperTurns: CGFloat = 1.4

    private var sweep: CGFloat { dir * turns * 2 * .pi }
    private var headTheta: CGFloat { headAngle * .pi / 180 }
    private func theta(_ t: CGFloat) -> CGFloat { headTheta - sweep * (1 - t) }
    private func radius(_ t: CGFloat) -> CGFloat { rTail + (rHead - rTail) * t }

    private func halfWidth(_ t: CGFloat) -> CGFloat {
        let span = min(1, taperTurns / turns)
        let x = min(1, t / span)
        return band / 2 * (0.04 + 0.96 * x * x * (3 - 2 * x))
    }

    /// Offsetting by radius rather than along the curve normal: for a spiral this
    /// gentle the difference is invisible, and it makes the gap between turns
    /// exactly `(rHead - rTail) / turns - band`, which is the number that has to
    /// be positive for the coil to read as coiled at all.
    func path(centre c: CGPoint, R: CGFloat) -> CGPath {
        let path = CGMutablePath()
        let steps = max(360, Int(turns * 260))
        func point(_ t: CGFloat, _ side: CGFloat) -> CGPoint {
            let a = theta(t), r = R * (radius(t) + side * halfWidth(t))
            return CGPoint(x: c.x + r * cos(a), y: c.y + r * sin(a))
        }
        for i in 0...steps {
            let p = point(CGFloat(i) / CGFloat(steps), 1)
            if i == 0 { path.move(to: p) } else { path.addLine(to: p) }
        }
        for i in stride(from: steps, through: 0, by: -1) {
            path.addLine(to: point(CGFloat(i) / CGFloat(steps), -1))
        }
        path.closeSubpath()
        return path
    }

    func end(centre c: CGPoint, R: CGFloat) -> CGPoint {
        CGPoint(x: c.x + R * rHead * cos(headTheta), y: c.y + R * rHead * sin(headTheta))
    }

    /// Direction of travel where the body runs out, in degrees. Taken from the
    /// spiral's own derivative rather than from the circle's tangent, because at
    /// the inner end the radial term is the one that dominates - a head placed on
    /// the circular tangent there points across the coil instead of out of it.
    var tangent: CGFloat {
        let dr = rHead - rTail, a = headTheta
        let v = CGPoint(x: dr * cos(a) - rHead * sin(a) * sweep,
                        y: dr * sin(a) + rHead * cos(a) * sweep)
        return atan2(v.y, v.x) * 180 / .pi
    }
}

/// The head, placed relative to where the body ran out rather than in absolute
/// terms, so it stays joined on when the coil is retuned.
///
/// An ellipse with an eye is a fish. `angular` swaps the drawn-out curved wedge
/// for a faceted one - a blunt snout, a hard jaw line and a narrow neck - which
/// is what carries a head big enough to sit in the middle of the mark.
struct Head {
    /// Degrees off the coil's direction of travel. Snakes turn their necks.
    var lift: CGFloat = 0
    /// How far past the end of the body the head sits, in head lengths.
    var along: CGFloat = 0.5
    var long: CGFloat = 0.33
    var wide: CGFloat = 0.215
    var angular: Bool = false
    /// A forked tongue: clutter at 16px, but the one cue that settles what
    /// the animal is at any size where it survives.
    var tongue: Bool = false

    private func space(_ coil: Coil, centre c: CGPoint, R: CGFloat) -> CGAffineTransform {
        let facing = coil.tangent + lift
        let run = coil.tangent * .pi / 180
        let e = coil.end(centre: c, R: R)
        return CGAffineTransform(translationX: e.x + cos(run) * along * long * R,
                                 y: e.y + sin(run) * along * long * R)
            .rotated(by: facing * .pi / 180)
    }

    func path(_ coil: Coil, centre c: CGPoint, R: CGFloat) -> CGPath {
        let L = R * long, W = R * wide
        let p = CGMutablePath()
        if angular {
            // Flat snout, widest just behind the eye, narrowing to a neck the
            // body can swallow: the silhouette of a snake's head from above.
            let corners: [(CGFloat, CGFloat)] = [
                (1.00, 0.18), (0.55, 0.52), (-0.10, 0.90), (-0.60, 0.80), (-1.00, 0.34),
                (-1.00, -0.34), (-0.60, -0.80), (-0.10, -0.90), (0.55, -0.52), (1.00, -0.18),
            ]
            for (i, corner) in corners.enumerated() {
                let pt = CGPoint(x: L * corner.0, y: W * corner.1)
                if i == 0 { p.move(to: pt) } else { p.addLine(to: pt) }
            }
        } else {
            p.move(to: CGPoint(x: L, y: W * 0.22))
            p.addCurve(to: CGPoint(x: -L * 0.25, y: W),
                       control1: CGPoint(x: L * 0.45, y: W * 0.62),
                       control2: CGPoint(x: L * 0.25, y: W))
            p.addCurve(to: CGPoint(x: -L, y: W * 0.52),
                       control1: CGPoint(x: -L * 0.62, y: W),
                       control2: CGPoint(x: -L, y: W * 0.86))
            p.addLine(to: CGPoint(x: -L, y: -W * 0.52))
            p.addCurve(to: CGPoint(x: -L * 0.25, y: -W),
                       control1: CGPoint(x: -L, y: -W * 0.86),
                       control2: CGPoint(x: -L * 0.62, y: -W))
            p.addCurve(to: CGPoint(x: L, y: -W * 0.22),
                       control1: CGPoint(x: L * 0.25, y: -W),
                       control2: CGPoint(x: L * 0.45, y: -W * 0.62))
            p.addCurve(to: CGPoint(x: L, y: W * 0.22),
                       control1: CGPoint(x: L * 1.14, y: -W * 0.16),
                       control2: CGPoint(x: L * 1.14, y: W * 0.16))
        }
        p.closeSubpath()
        var t = space(coil, centre: c, R: R)
        return p.copy(using: &t)!
    }

    func tonguePath(_ coil: Coil, centre c: CGPoint, R: CGFloat) -> CGPath {
        let L = R * long, W = R * wide
        let p = CGMutablePath()
        p.move(to: CGPoint(x: L * 0.98, y: 0))
        p.addLine(to: CGPoint(x: L * 1.34, y: 0))
        p.move(to: CGPoint(x: L * 1.34, y: 0))
        p.addLine(to: CGPoint(x: L * 1.62, y: W * 0.30))
        p.move(to: CGPoint(x: L * 1.34, y: 0))
        p.addLine(to: CGPoint(x: L * 1.62, y: -W * 0.30))
        var t = space(coil, centre: c, R: R)
        return p.copy(using: &t)!
    }

    func eye(_ coil: Coil, centre c: CGPoint, R: CGFloat) -> CGPath {
        // Kept back from the brow: at the snout end the head is already
        // narrowing, and an eye set too far forward breaks its outline.
        let x = R * long * 0.35, y = R * wide * 0.30, s = R * wide * 0.24
        let p = CGMutablePath()
        if angular {
            p.move(to: CGPoint(x: x + s * 1.5, y: y))
            p.addLine(to: CGPoint(x: x, y: y + s))
            p.addLine(to: CGPoint(x: x - s * 1.5, y: y))
            p.addLine(to: CGPoint(x: x, y: y - s))
            p.closeSubpath()
        } else {
            p.addEllipse(in: CGRect(x: x - s, y: y - s, width: s * 2, height: s * 2))
        }
        var t = space(coil, centre: c, R: R)
        return p.copy(using: &t)!
    }
}

struct Mark {
    var coil: Coil
    var head: Head
    var R: CGFloat = 0.33
    /// Optical centring: a coil with its head off to one side is not balanced on
    /// its geometric centre.
    var shift: CGPoint = .zero
    /// Whether the bars run across the head as well as the body.
    var barsOverHead: Bool = false
    var barWeight: CGFloat = 0.13
}

func draw(_ mark: Mark) -> Artwork {
    { ctx, rect, palette in
        let centre = CGPoint(x: rect.midX + rect.width * mark.shift.x,
                             y: rect.midY + rect.width * mark.shift.y)
        let R = rect.width * mark.R
        let dark = palette.bottom.copy(alpha: 0.95)!
        let body = mark.coil.path(centre: centre, R: R)
        let head = mark.head.path(mark.coil, centre: centre, R: R)

        // Stroke dark, then fill white over it: the fill takes back the stroke's
        // inner half, so what is left is a dark rim outside the shape. Against
        // the tile it disappears; where the coil runs close to itself it is the
        // gap that keeps two turns from merging into one white mass.
        func ink(_ path: CGPath) {
            ctx.setStrokeColor(dark)
            ctx.setLineWidth(R * 0.07)
            ctx.setLineJoin(.round)
            ctx.addPath(path)
            ctx.strokePath()
            ctx.setFillColor(white(0.93))
            ctx.addPath(path)
            ctx.fillPath()
        }

        // Cut the body away under the head rather than letting the head lie
        // over it. The white is not opaque, so two whites overlapping read as a
        // third, brighter shape - with a head this size that ghosts the whole
        // coil through it. Two even-odd clips in a row intersect, which is how
        // the head and the gap around it come out of one region.
        func clipOut(_ path: CGPath) {
            let cut = CGMutablePath()
            cut.addRect(rect)
            cut.addPath(path)
            ctx.addPath(cut)
            ctx.clip(using: .evenOdd)
        }

        ctx.saveGState()
        clipOut(head)
        clipOut(head.copy(strokingWithWidth: R * 0.15, lineCap: .round,
                          lineJoin: .round, miterLimit: 10))
        ink(body)

        // The bars, cut to the body they cross. Off it they would be dark on a
        // dark tile anyway; clipping keeps their ends honest at every edge.
        ctx.saveGState()
        ctx.addPath(body)
        ctx.clip()
        seams(ctx, centre: centre, radius: R, ink: dark, weight: mark.barWeight)
        ctx.restoreGState()
        ctx.restoreGState()

        ink(head)
        if mark.barsOverHead {
            ctx.saveGState()
            ctx.addPath(head)
            ctx.clip()
            seams(ctx, centre: centre, radius: R, ink: dark, weight: mark.barWeight)
            ctx.restoreGState()
        }

        if mark.head.tongue {
            let tongue = mark.head.tonguePath(mark.coil, centre: centre, R: R)
            ctx.setLineCap(.round)
            ctx.setLineJoin(.round)
            for (colour, w) in [(dark, R * 0.10), (white(0.93), R * 0.045)] {
                ctx.setStrokeColor(colour)
                ctx.setLineWidth(w)
                ctx.addPath(tongue)
                ctx.strokePath()
            }
        }

        ctx.setFillColor(dark)
        ctx.addPath(mark.head.eye(mark.coil, centre: centre, R: R))
        ctx.fillPath()
    }
}

// MARK: - The mark

/// A snake coiled into a lens: the body winds inward for two and two-thirds
/// turns, tail tapering to a point at twelve o'clock, and its head stands in the
/// middle where the iris would be, turned down off the line of the coil.
///
/// The turn count is what puts the tail where it is - the tail lies `turns`
/// whole revolutions back from the head, so 2.694 turns behind a head at 340
/// degrees lands the tip at 90. Move the head and the turn count moves with it.
let serpentCoil = Mark(
    coil: Coil(rTail: 1.00, rHead: 0.10, turns: 2.694, band: 0.16, headAngle: 340,
               dir: 1, taperTurns: 0.7),
    head: Head(lift: -45, along: 0.28, long: 0.65, wide: 0.39, angular: true, tongue: true),
    R: 0.295,
    shift: CGPoint(x: -0.012, y: -0.016))


