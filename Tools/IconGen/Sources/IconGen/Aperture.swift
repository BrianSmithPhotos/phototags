import CoreGraphics
import IconForge

/// The bars an iris leaves where one blade laps over the next: six lines at 60
/// degrees, each starting at a corner of a hexagon of the same size
/// MacPhotoMaster-Swift uses, which is the family resemblance.
///
/// Where a bar stops is left to the caller's clip - the body it crosses - so it
/// is cut by the edge it has to meet at any size, rather than by an endpoint
/// worked out per bar.
func seams(_ ctx: CGContext, centre c: CGPoint, radius R: CGFloat, ink: CGColor,
           weight: CGFloat = 0.13) {
    ctx.setStrokeColor(ink)
    ctx.setLineWidth(R * weight)
    ctx.setLineCap(.butt)
    for i in 0..<6 {
        let ray = seamRay(i, centre: c, radius: R, weight: weight)
        ctx.move(to: ray.start)
        ctx.addLine(to: CGPoint(x: ray.start.x + ray.direction.x * R * 2.6,
                                y: ray.start.y + ray.direction.y * R * 2.6))
    }
    ctx.strokePath()
}

/// Where seam `i` begins and which way it runs, as one definition rather than
/// two: a cut that has to land on a dark line needs the same line the seam is
/// stroked along, or it lands near it instead of on it.
///
/// The start is shifted half a band off the hexagon-edge line, so the seam lies
/// wholly on one side of it. A seam that straddles the line snaps the opening's
/// edge sideways by half a band at each vertex.
func seamRay(_ i: Int, centre c: CGPoint, radius R: CGFloat,
             weight: CGFloat) -> (start: CGPoint, direction: CGPoint) {
    let band = R * weight
    let v = vertex(i, centre: c, radius: R), u = vertex(i - 1, centre: c, radius: R)
    var d = CGPoint(x: v.x - u.x, y: v.y - u.y)
    let len = hypot(d.x, d.y)
    d = CGPoint(x: d.x / len, y: d.y / len)

    let mid = CGPoint(x: (u.x + v.x) / 2, y: (u.y + v.y) / 2)
    var n = CGPoint(x: mid.x - c.x, y: mid.y - c.y)
    let nlen = hypot(n.x, n.y)
    n = CGPoint(x: n.x / nlen, y: n.y / nlen)
    return (CGPoint(x: u.x + n.x * -band / 2, y: u.y + n.y * -band / 2), d)
}

/// The hexagonal opening, at the size MacPhotoMaster-Swift draws it.
func opening(centre c: CGPoint, radius R: CGFloat) -> CGPath {
    let path = CGMutablePath()
    for i in 0..<6 {
        let p = vertex(i, centre: c, radius: R)
        if i == 0 { path.move(to: p) } else { path.addLine(to: p) }
    }
    path.closeSubpath()
    return path
}

func vertex(_ i: Int, centre c: CGPoint, radius R: CGFloat) -> CGPoint {
    let a = CGFloat(i) * .pi / 3 + .pi / 6
    return CGPoint(x: c.x + R * 0.52 * cos(a), y: c.y + R * 0.52 * sin(a))
}
