// Envoy's on-device text reader for photos and screenshots (Phase 5): Apple's Vision framework, on this Mac, so the
// text that checks Muse Spark's extraction never leaves the machine.
//
//   envoy-ocr <image>   →   {"width": W, "height": H, "lines": [{"text": "...", "confidence": 0.98, "box": [x, y, w, h]}]}
//
// Boxes are fractions of the image, origin at the top left. Language correction is off, so codes like KX7Q2M come
// back as printed instead of being "corrected" into words.
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

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.minimumTextHeight = 0.008

let handler = VNImageRequestHandler(cgImage: image, options: [:])
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write("vision failed: \(error)\n".data(using: .utf8)!)
    exit(1)
}

var lines: [[String: Any]] = []
for obs in request.results ?? [] {
    guard let best = obs.topCandidates(1).first else { continue }
    let b = obs.boundingBox  // normalized, origin bottom left
    lines.append([
        "text": best.string,
        "confidence": Double(best.confidence),
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
