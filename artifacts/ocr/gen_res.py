from dataclasses import dataclass
import yaml
from pathlib import Path

OCR_DIR = Path(__file__).parent
SAMPLES_DIR = OCR_DIR / 'samples'


@dataclass
class ModelResult:
    detection: int
    recognition: int


results = {
    'easyocr': ModelResult(0, 0),
    'ppocr': ModelResult(0, 0),
    'tesseract': ModelResult(0, 0),
}

for obj in SAMPLES_DIR.iterdir():
    if not obj.is_dir():
        continue
    with open(obj / (obj.name + '.yml')) as f:
        data = yaml.safe_load(f)
    for model, result in results.items():
        result.detection += bool(data[model]['det'])
        result.recognition += bool(data[model]['rec'])

for model, result in results.items():
    print(
        f'{model}: detection {result.detection}, recognition {result.recognition}, total {result.detection + result.recognition}'
    )
