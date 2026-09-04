// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "CuteBubbles",
    platforms: [.iOS(.v16)],
    products: [
        .library(name: "CuteBubbles", targets: ["CuteBubbles"])
    ],
    targets: [
        .target(
            name: "CuteBubbles",
            resources: [.process("Assets.xcassets")]
        )
    ]
)
