import Cocoa
import Vision

// Full-screen OCR: returns ALL recognised text blocks with coordinates.
// Output format (one line per block): text|x|y
// Coordinates are in logical screen pixels matching mss/pynput convention.
// Used by get_screen_state in main.py for text-only LLMs (no vision required).

let args = CommandLine.arguments
if args.count < 2 { exit(1) }
let imagePath = args[1]

guard let img = NSImage(contentsOfFile: imagePath),
      let cgImage = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("Failed to load image")
    exit(1)
}

let requestHandler = VNImageRequestHandler(cgImage: cgImage, options: [:])
let request = VNRecognizeTextRequest { (request, error) in
    guard let observations = request.results as? [VNRecognizedTextObservation] else { return }

    var blocks: [(text: String, minX: Int, midX: Int, midY: Int)] = []

    for obs in observations {
        guard let candidate = obs.topCandidates(1).first else { continue }
        let text = candidate.string.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { continue }

        let box = obs.boundingBox
        // mss captures at logical resolution on macOS, so cgImage dimensions are
        // already in logical pixels — no Retina scale division needed here.
        let minX = Int(box.minX * CGFloat(cgImage.width))
        let midX = Int(box.midX * CGFloat(cgImage.width))
        let midY = Int((1.0 - box.midY) * CGFloat(cgImage.height))
        blocks.append((text, minX, midX, midY))
    }

    // Sort top-to-bottom, then left-to-right within same row
    blocks.sort { a, b in
        a.midY != b.midY ? a.midY < b.midY : a.minX < b.minX
    }

    for b in blocks {
        // Escape pipe characters in text to avoid breaking the format
        let safe = b.text.replacingOccurrences(of: "|", with: "｜")
        print("\(safe)|\(b.minX)|\(b.midX)|\(b.midY)")
    }
}

if #available(macOS 11.0, *) {
    request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
    request.usesLanguageCorrection = true
    request.recognitionLevel = .accurate
}
try? requestHandler.perform([request])
