// swift-tools-version: 5.10
import PackageDescription

// Deliberately a package of its own rather than part of the app: this is a
// generator run by hand when the icon changes, and the app it draws for is
// Python, so there is no dependency graph to join in the first place.
let package = Package(
    name: "IconGen",
    platforms: [.macOS(.v13)],
    dependencies: [
        .package(url: "https://github.com/BrianSmithPhotos/IconForge.git", branch: "main")
    ],
    targets: [
        .executableTarget(name: "IconGen", dependencies: ["IconForge"])
    ]
)
