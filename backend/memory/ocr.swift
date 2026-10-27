// Envoy's on-device text reader for photos and screenshots (Phase 5): Apple's Vision framework, on this Mac, so the
// text that checks Muse Spark's extraction never leaves the machine.
//
//   envoy-ocr <image>   →   {"width": W, "height": H, "lines": [{"text": "...", "confidence": 0.98, "box": [x, y, w, h]}]}
//
// Boxes are fractions of the image, origin at the top left. Language correction is off, so codes like KX7Q2M come
// back as printed instead of being "corrected" into words. A second pass reads four overlapping tiles and adds the
// words the full pass missed: on SkyLark's trip screen Vision skipped a lone confirmation code on the right of a row,
// and read it in a tile.
import Foundation
import Vision
import ImageIO

guard CommandLine.arguments.count == 2 else {
    FileHandle.standardError.write("usage: envoy-ocr <image>\n".data(using: .utf8)!)
    exit(2)
}
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    FileHandle.standardError.write("cannot read image\n".data(using: .utf8)!)
    exit(1)
}

let handler = VNImageRequestHandler(cgImage: image, options: [:])

// Text in `region` (normalized, origin bottom left), with boxes mapped back to the whole image.
func read(_ region: CGRect) -> [(String, Double, CGRect)] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.minimumTextHeight = 0.008
    request.regionOfInterest = region
    do {
        try handler.perform([request])
    } catch {
        FileHandle.standardError.write("vision failed: \(error)\n".data(using: .utf8)!)
        exit(1)
    }
    return (request.results ?? []).compactMap { obs in
        guard let best = obs.topCandidates(1).first else { return nil }
        let b = obs.boundingBox
        let box = CGRect(x: region.minX + b.minX * region.width, y: region.minY + b.minY * region.height,
                         width: b.width * region.width, height: b.height * region.height)
        return (best.string, Double(best.confidence), box)
    }
}

var found = read(CGRect(x: 0, y: 0, width: 1, height: 1))
let tiles = [CGRect(x: 0, y: 0.45, width: 0.55, height: 0.55), CGRect(x: 0.45, y: 0.45, width: 0.55, height: 0.55),
             CGRect(x: 0, y: 0, width: 0.55, height: 0.55), CGRect(x: 0.45, y: 0, width: 0.55, height: 0.55)]
for tile in tiles {
    for (text, conf, box) in read(tile) {
        let center = CGPoint(x: box.midX, y: box.midY)
        if !found.contains(where: { $0.2.insetBy(dx: -0.005, dy: -0.005).contains(center) || box.contains(CGPoint(x: $0.2.midX, y: $0.2.midY)) }) {
            found.append((text, conf, box))
        }
    }
}

var lines: [[String: Any]] = []
for (text, conf, b) in found {
    lines.append([
        "text": text,
        "confidence": conf,
        "box": [Double(b.minX), Double(1 - b.maxY), Double(b.width), Double(b.height)],
    ])
}
// Reading order: top to bottom, then left to right within a row.
lines.sort { a, c in
    let ba = a["box"] as! [Double], bc = c["box"] as! [Double]
    if abs(ba[1] - bc[1]) > 0.01 { return ba[1] < bc[1] }
    return ba[0] < bc[0]
}
let out: [String: Any] = ["width": image.width, "height": image.height, "lines": lines]
let data = try! JSONSerialization.data(withJSONObject: out, options: [])
FileHandle.standardOutput.write(data)
