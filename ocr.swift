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
    let ink: CGFloat   // how much darker the ink is than the paper, 0-1
}

// The image as 8-bit gray, one byte per pixel, top row first.
struct Gray {
    let pixels: [UInt8]
    let width: Int, height: Int

    init(_ image: CGImage) {
        width = image.width
        height = image.height
        var px = [UInt8](repeating: 255, count: width * height)
        let ctx = CGContext(data: &px, width: width, height: height, bitsPerComponent: 8,
                            bytesPerRow: width, space: CGColorSpaceCreateDeviceGray(),
                            bitmapInfo: CGImageAlphaInfo.none.rawValue)!
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        pixels = px
    }

    // How dark the ink in a Vision box is against the paper around it: the
    // paper (90th percentile) minus the darkest ink (1st percentile). Print
    // from the other side of the sheet showing through measures about 0.05;
    // real text 0.24 and up. Local to the box, so shadows don't matter.
    func ink(in box: CGRect) -> CGFloat {
        let x0 = max(0, Int(box.minX * CGFloat(width))), x1 = min(width, Int(box.maxX * CGFloat(width)))
        let y0 = max(0, Int((1 - box.maxY) * CGFloat(height))), y1 = min(height, Int((1 - box.minY) * CGFloat(height)))
        guard x1 > x0, y1 > y0 else { return 1 }
        var histogram = [Int](repeating: 0, count: 256)
        for y in y0..<y1 {
            for x in x0..<x1 { histogram[Int(pixels[y * width + x])] += 1 }
        }
        let total = (x1 - x0) * (y1 - y0)
        func percentile(_ q: Double) -> Int {
            var seen = 0
            for (level, count) in histogram.enumerated() {
                seen += count
                if Double(seen) >= q * Double(total) { return level }
            }
            return 255
        }
        return CGFloat(percentile(0.9) - percentile(0.01)) / 255
    }
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
func pieces(from observations: [VNRecognizedTextObservation], in gray: Gray) -> [Piece] {
    let w = CGFloat(gray.width), h = CGFloat(gray.height)
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
            size: (left + right) / 2 / h,
            ink: gray.ink(in: o.boundingBox)
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
    let found = pieces(from: observations, in: Gray(ci))
    // One line per piece, tagged with its box and type size. layout.py groups
    // pieces into lines and reads paragraphs, headings and running headers
    // off the geometry.
    return found
        .sorted { ($0.top, $0.x0) < ($1.top, $1.x0) }
        .map { String(format: "[%.4f %.4f %.4f %.4f %.4f %.4f] ", $0.x0, $0.x1, $0.top, $0.bottom, $0.size, $0.ink) + $0.text }
        .joined(separator: "\n")
}

// Where to cut a two-page spread. The middle of the photo is only where the
// spine is if the photo was framed square on it; off by a few letters, the
// cut slices the end off every line of one page ("persor" for "personal")
// and the slivers land on the facing half, where layout.py drops them as
// scraps. So cut in the gap between the two pages' text instead: find the
// text on the whole spread with a quick pass, and look near the middle for a
// band of columns that no line crosses.
// How far either side of the middle the spine may be, fraction of the width.
let GUTTER_SEARCH = 0.2
// A band narrower than this is a gap between words, not the gutter.
let GUTTER_MIN = 0.01
// The cut keeps this far from the text on either side, so a letter Vision's
// box left out isn't sliced.
let GUTTER_CLEAR = 0.02
// Pieces this faint are print from the other side of the sheet (layout.py's
// SHOW_THROUGH_MAX): they may lie across the gutter, and aren't this page's.
let SHOW_THROUGH_MAX: CGFloat = 0.12

// The x to cut at, in pixels: the middle of the photo when that's clear of
// the text, else the nearest point in the gap that is. nil when no gap is
// found (one page photographed in landscape, or the photo is too far off).
func gutter(of image: CGImage) -> Int? {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .fast
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    guard (try? handler.perform([request])) != nil, let observations = request.results else { return nil }

    let gray = Gray(image)
    let w = image.width, h = image.height
    var covered = [Bool](repeating: false, count: w)
    for o in observations {
        let box = o.boundingBox
        if gray.ink(in: box) <= SHOW_THROUGH_MAX { continue }
        // a tall thin stroke is the spine's shadow or a page edge read as
        // "I" or "|", not a line of text
        if box.height * CGFloat(h) > 3 * box.width * CGFloat(w) { continue }
        let x0 = max(0, Int(box.minX * CGFloat(w))), x1 = min(w, Int((box.maxX * CGFloat(w)).rounded(.up)))
        if x1 > x0 { for x in x0..<x1 { covered[x] = true } }
    }

    // every empty band that reaches into the search window, at its full width
    let mid = w / 2
    let reach = Int(GUTTER_SEARCH * Double(w))
    var bands: [(lo: Int, hi: Int)] = []
    var x = mid - reach
    while x < mid + reach {
        if covered[x] { x += 1; continue }
        var lo = x, hi = x
        while lo > 0 && !covered[lo - 1] { lo -= 1 }
        while hi < w && !covered[hi] { hi += 1 }
        bands.append((lo, hi))
        x = hi
    }
    // The gutter is the band at (or nearest) the middle. Not the widest: a
    // page of short lines leaves a wide empty strip inside its own margin.
    func away(_ b: (lo: Int, hi: Int)) -> Int { max(b.lo - mid, mid - b.hi, 0) }
    let wide = bands.filter { $0.hi - $0.lo >= Int(GUTTER_MIN * Double(w)) }
    guard let band = wide.min(by: { (away($0), $1.hi - $1.lo) < (away($1), $0.hi - $0.lo) }) else { return nil }
    let clear = min(Int(GUTTER_CLEAR * Double(w)), (band.hi - band.lo) / 2)
    return min(max(mid, band.lo + clear), band.hi - clear)
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

    let midX = gutter(of: cgImage) ?? width / 2
    if midX != width / 2 {
        FileHandle.standardError.write(
            "note: \(imagePath): spine is off center; cutting at x=\(midX) of \(width)\n"
                .data(using: .utf8)!)
    }
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
