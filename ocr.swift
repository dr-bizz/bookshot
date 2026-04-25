import Foundation
import Vision
import CoreGraphics
import ImageIO

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
    let rowHeight: CGFloat = 0.015
    let rows = Dictionary(grouping: observations) { obs -> Int in
        let topY = obs.boundingBox.origin.y + obs.boundingBox.size.height
        return Int((1.0 - topY) / rowHeight)
    }
    let sortedKeys = rows.keys.sorted()
    var out: [String] = []
    for k in sortedKeys {
        let rowItems = rows[k]!.sorted { $0.boundingBox.origin.x < $1.boundingBox.origin.x }
        let line = rowItems.compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
        if !line.isEmpty { out.append(line) }
    }
    return out.joined(separator: "\n")
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
    return "\(recognize(in: leftImage))\n\n\(recognize(in: rightImage))"
}

let args = CommandLine.arguments
guard args.count >= 2 else {
    print("usage: ocr.swift <image-path> [--no-split]")
    exit(1)
}
let path = args[1]
let split = !args.contains("--no-split")
print(ocr(imagePath: path, splitSpread: split))
