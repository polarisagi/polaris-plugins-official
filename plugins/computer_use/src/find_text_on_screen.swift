import Cocoa
import Vision

let args = CommandLine.arguments
if args.count < 3 {
    exit(1)
}
let imagePath = args[1]
let targetText = args[2]

guard let img = NSImage(contentsOfFile: imagePath),
      let cgImage = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("Failed to load image")
    exit(1)
}

let scale = NSScreen.main?.backingScaleFactor ?? 1.0

let requestHandler = VNImageRequestHandler(cgImage: cgImage, options: [:])
let request = VNRecognizeTextRequest { (request, error) in
    guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
    
    var matches = [(CGFloat, CGFloat)]()
    
    for observation in observations {
        guard let topCandidate = observation.topCandidates(1).first else { continue }
        // Match exact or contains
        if topCandidate.string.contains(targetText) {
            let boundingBox = observation.boundingBox
            let pixelX = boundingBox.midX * CGFloat(cgImage.width)
            let pixelY = (1.0 - boundingBox.midY) * CGFloat(cgImage.height)
            matches.append((pixelX, pixelY))
        }
    }
    
    // Sort matches by Y coordinate (top to bottom)
    matches.sort { $0.1 < $1.1 }
    
    for match in matches {
        print("\(match.0),\(match.1)")
    }
}
if #available(macOS 11.0, *) {
    request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
    request.usesLanguageCorrection = true
}
try? requestHandler.perform([request])
