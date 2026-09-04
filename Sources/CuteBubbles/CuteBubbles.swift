//  CuteBubbles — 手绘风聊天气泡，按点九（nine-patch）拉伸
//
//  用法：
//      Text(message)
//          .padding(skin.contentInsets(mirrored: incoming))
//          .frame(minHeight: skin.minHeight)
//          .background { BubbleSkinBackground(skin: skin, mirrored: incoming) }
//
//  气泡会跟着文字长；装饰（猫、翅膀、云）待在保护区里不变形。

import SwiftUI
import UIKit

// MARK: - 一张皮肤

public struct BubbleSkin: Identifiable, Sendable {
    public let id: String
    /// 给用户看的名字
    public let name: String
    /// Asset catalog 里的图片名
    public let asset: String

    /// 点九保护区：四边各留多少不参与拉伸，单位 pt。
    ///
    /// 这些数是**量出来的**，不是拿 `高 × 某个系数` 猜的 —— 每张图的猫、翅膀、云朵
    /// 伸进来多少都不一样，一个比例套 21 张必然出事（字会压在装饰上，或者飘到框外）。
    ///
    /// 量法见 tools/measure.py：先找出内壁矩形（装饰和描边之外那块纯填充），
    /// 再只把它中间一条缝留给拉伸，其余全划进保护区。缝落在纯填充上，
    /// 所以横竖怎么拉都看不出接缝。
    ///
    /// ⚠️ 竖缝只有 8px，而且**不放在正中间** —— 纵向拉伸等于把缝那几行原地复制，
    /// 左右两列站着猫和翅膀，落在眼睛或耳朵上就会扯出竖条纹。所以是逐行算了一遍
    /// 两侧的上下起伏，挑最平的一行当缝。
    public let cap: EdgeInsets

    /// 文字该落在哪：对应点九图右边/下边那条 content 线。左右比 cap 多 2pt 呼吸。
    public let pad: EdgeInsets

    public init(id: String, name: String, asset: String, cap: EdgeInsets, pad: EdgeInsets) {
        self.id = id; self.name = name; self.asset = asset; self.cap = cap; self.pad = pad
    }

    // EdgeInsets 自己不是 Hashable，按 id 认人就够了 —— id 本来就是唯一的。
    public static func == (a: BubbleSkin, b: BubbleSkin) -> Bool { a.id == b.id }
    public func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

extension BubbleSkin: Hashable {

    /// 气泡最矮能到多少 —— 再矮下去点九就要压缩两端，装饰会变形。
    public var minHeight: CGFloat { max(42, cap.top + cap.bottom + 6) }

    /// 收到的那一侧通常整张镜像，保护区和内边距也跟着左右对调。
    public func capInsets(mirrored: Bool) -> EdgeInsets {
        mirrored ? .init(top: cap.top, leading: cap.trailing,
                         bottom: cap.bottom, trailing: cap.leading)
                 : cap
    }

    public func contentInsets(mirrored: Bool) -> EdgeInsets {
        mirrored ? .init(top: pad.top, leading: pad.trailing,
                         bottom: pad.bottom, trailing: pad.leading)
                 : pad
    }
}

// MARK: - 画出来

/// 气泡底。放在 `.background { }` 里，尺寸由上面的文字撑出来。
public struct BubbleSkinBackground: View {
    public let skin: BubbleSkin
    public let mirrored: Bool
    /// 图片从哪个 bundle 找。默认 .main；做成 SPM 包时传 .module。
    public let bundle: Bundle

    public init(skin: BubbleSkin, mirrored: Bool = false, bundle: Bundle = .main) {
        self.skin = skin; self.mirrored = mirrored; self.bundle = bundle
    }

    public var body: some View {
        NinePatchImage(image: skin.resizableImage(mirrored: mirrored, bundle: bundle))
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// 选择器里的缩略图：整张等比放下，不切片。
public struct BubbleSkinThumbnail: View {
    public let skin: BubbleSkin
    public let mirrored: Bool
    public let bundle: Bundle

    public init(skin: BubbleSkin, mirrored: Bool = false, bundle: Bundle = .main) {
        self.skin = skin; self.mirrored = mirrored; self.bundle = bundle
    }

    public var body: some View {
        Image(uiImage: skin.rawImage(mirrored: mirrored, bundle: bundle))
            .resizable()
            .scaledToFit()
    }
}

// MARK: - 点九

extension BubbleSkin {
    /// 把量好的 cap 换算到这张图上，并留出至少 2pt 的可拉伸缝 ——
    /// 保护区顶满了 UIKit 会改去压缩两端，猫和翅膀就变形了。
    func uiCapInsets(for raw: UIImage, mirrored: Bool) -> UIEdgeInsets {
        let w = raw.size.width, h = raw.size.height
        guard w > 8, h > 8 else { return .zero }
        let c = capInsets(mirrored: mirrored)
        var top = c.top, bottom = c.bottom, left = c.leading, right = c.trailing
        if top + bottom > h - 2 {
            let s = (h - 2) / (top + bottom)
            top *= s; bottom *= s
        }
        if left + right > w - 2 {
            let s = (w - 2) / (left + right)
            left *= s; right *= s
        }
        return UIEdgeInsets(top: top, left: left, bottom: bottom, right: right)
    }

    func rawImage(mirrored: Bool, bundle: Bundle) -> UIImage {
        let img = UIImage(named: asset, in: bundle, compatibleWith: nil) ?? UIImage()
        return mirrored ? img.mirroredHorizontally() : img
    }

    func resizableImage(mirrored: Bool, bundle: Bundle) -> UIImage {
        let raw = rawImage(mirrored: mirrored, bundle: bundle)
        return raw.resizableImage(withCapInsets: uiCapInsets(for: raw, mirrored: mirrored),
                                  resizingMode: .stretch)
    }
}

private extension UIImage {
    func mirroredHorizontally() -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = scale
        format.opaque = false
        return UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            ctx.cgContext.translateBy(x: size.width, y: 0)
            ctx.cgContext.scaleBy(x: -1, y: 1)
            draw(in: CGRect(origin: .zero, size: size))
        }
    }
}

/// ⚠️ 必须走 UIImageView。SwiftUI 的 `Image.resizable()` 会丢掉 UIImage 上的
/// capInsets，整张图跟着一起乱拉 —— 微信、抖音的 iOS 气泡也是这么画的。
private struct NinePatchImage: UIViewRepresentable {
    let image: UIImage

    func makeUIView(context: Context) -> UIImageView {
        let iv = UIImageView(image: image)
        iv.contentMode = .scaleToFill
        iv.backgroundColor = .clear
        iv.isOpaque = false
        iv.clipsToBounds = false
        // 让它老老实实听外面的尺寸，别拿自己的 intrinsic size 说话
        iv.setContentHuggingPriority(.init(1), for: .horizontal)
        iv.setContentHuggingPriority(.init(1), for: .vertical)
        iv.setContentCompressionResistancePriority(.init(1), for: .horizontal)
        iv.setContentCompressionResistancePriority(.init(1), for: .vertical)
        return iv
    }

    func updateUIView(_ iv: UIImageView, context: Context) { iv.image = image }
}
