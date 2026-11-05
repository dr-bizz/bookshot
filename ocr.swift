import Foundation
import Vision
import CoreGraphics
import ImageIO

// One recognized piece of text, with its box measured on the straightened
// page (fractions of the image, y running top to bottom).
struct Piece {
    let text: String
    let x0: CGFloat, x1: CGFloat, top: CGFloat, bottom: CGFloat
    let size: CGFloat  // line height along its own slant, fraction of image height
}

func median(_ xs: [CGFloat]) -> CGFloat? {
    if xs.isEmpty { return nil }
    let s = xs.sorted()
    return s.count % 2 == 1 ? s[s.count / 2] : (s[s.count / 2 - 1] + s[s.count / 2]) / 2
}

// Vision's boxes are axis-aligned, so on a handheld photo where the text runs
// a few degrees off level a long line's box is taller than its type, its top
// edge sits higher than a short line's beside it, and its left edge drifts
// line by line. Rotating every corner back by the page's own text angle gives
// layout.py a square-on page to measure: indents, gaps, type size, and the
// top-to-bottom order of the lines.
func pieces(from observations: [VNRecognizedTextObservation], width w: CGFloat, height h: CGFloat) -> [Piece] {
    func px(_ p: CGPoint) -> CGPoint { CGPoint(x: p.x * w, y: p.y * h) }

    // the angle of real text lines, not stray fragments from the facing page
    let angles = observations.filter { $0.boundingBox.width > 0.2 }.map { o -> CGFloat in
        let a = px(o.bottomLeft), b = px(o.bottomRight)
        return atan2(b.y - a.y, b.x - a.x)
    }
    let theta = median(angles) ?? 0
    let c = cos(-theta), s = sin(-theta)
    func straighten(_ p: CGPoint) -> CGPoint {
        let q = px(p)
        let dx = q.x - w / 2, dy = q.y - h / 2
        return CGPoint(x: (w / 2 + dx * c - dy * s) / w, y: (h / 2 + dx * s + dy * c) / h)
    }

    return observations.compactMap { o in
        guard let text = o.topCandidates(1).first?.string, !text.isEmpty else { return nil }
        let corners = [o.topLeft, o.topRight, o.bottomLeft, o.bottomRight].map(straighten)
        let left = hypot(px(o.topLeft).x - px(o.bottomLeft).x, px(o.topLeft).y - px(o.bottomLeft).y)
        let right = hypot(px(o.topRight).x - px(o.bottomRight).x, px(o.topRight).y - px(o.bottomRight).y)
        return Piece(
            text: text,
            x0: corners.map { $0.x }.min()!,
            x1: corners.map { $0.x }.max()!,
            top: 1.0 - corners.map { $0.y }.max()!,
            bottom: 1.0 - corners.map { $0.y }.min()!,
            size: (left + right) / 2 / h
        )
    }
}

func recognize(in ci: CGImage) -> String {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(cgImage: ci, options: [:])
    do {
        try handler.perform([request])
    } catch {
        return "[ERROR: \(error.localizedDescription)]"
    }
    guard let observations = request.results else { return "" }
    let found = pieces(from: observations, width: CGFloat(ci.width), height: CGFloat(ci.height))
    // One line per piece, tagged with its box and type size. layout.py groups
    // pieces into lines and reads paragraphs, headings and running headers
    // off the geometry.
    return found
        .sorted { ($0.top, $0.x0) < ($1.top, $1.x0) }
        .map { String(format: "[%.4f %.4f %.4f %.4f %.4f] ", $0.x0, $0.x1, $0.top, $0.bottom, $0.size) + $0.text }
        .joined(separator: "\n")
}

func ocr(imagePath: String, splitSpread: Bool) -> String {
    let url = URL(fileURLWithPath: imagePath)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        return "[ERROR: could not load \(imagePath)]"
    }

    let width = cgImage.width
    let height = cgImage.height

    // portrait images aren't two-page spreads — don't split even if asked
    if !splitSpread || width < height {
        if splitSpread && width < height {
            FileHandle.standardError.write(
                "note: \(imagePath) is portrait (\(width)x\(height)); treating as single page\n"
                    .data(using: .utf8)!)
        }
        return recognize(in: cgImage)
    }

    let midX = width / 2
    guard let leftImage = cgImage.cropping(to: CGRect(x: 0, y: 0, width: midX, height: height)),
          let rightImage = cgImage.cropping(to: CGRect(x: midX, y: 0, width: width - midX, height: height)) else {
        return recognize(in: cgImage)
    }
    // A delimiter, not a blank line, between the halves: a blank line in the
    // raw output means "paragraph break" to clean.py, and each half needs its
    // own margins in layout.py.
    return [recognize(in: leftImage), recognize(in: rightImage)]
        .filter { !$0.isEmpty }
        .joined(separator: "\n===== right page =====\n")
}

let args = CommandLine.arguments
guard args.count >= 2 else {
    print("usage: ocr.swift <image-path> [--no-split]")
    exit(1)
}
let path = args[1]
let split = !args.contains("--no-split")
// a blank page prints nothing, so it can't pass for a paragraph break
let result = ocr(imagePath: path, splitSpread: split)
if !result.isEmpty { print(result) }
