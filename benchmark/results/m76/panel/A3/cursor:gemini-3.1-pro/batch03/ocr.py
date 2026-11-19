import sys
import Quartz
import Vision
from Foundation import NSURL

def recognize_text(image_path):
    url = NSURL.fileURLWithPath_(image_path)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    success, error = handler.performRequests_error_([request], None)
    if success:
        for observation in request.results():
            print(observation.topCandidates_(1)[0].string())

recognize_text(sys.argv[1])
