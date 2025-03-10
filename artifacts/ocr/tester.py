import sys
import cv2
import numpy as np
import yaml
from yaml import SafeDumper
from PIL import Image
import easyocr
from paddleocr import PaddleOCR
import pytesseract
from pytesseract import Output
from pathlib import Path

OCR_DIR = Path(__file__).parent
SAMPLES_DIR = OCR_DIR / 'samples'


def str_presenter(dumper: SafeDumper, data: str) -> yaml.ScalarNode:
    if '\n' in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    else:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)


def none_presenter(dumper: SafeDumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:null', '')


SafeDumper.add_representer(str, str_presenter)
SafeDumper.add_representer(type(None), none_presenter)

print('Initializing EasyOCR...')
reader_easyocr = easyocr.Reader(['ru', 'en'])
print('Initializing PaddleOCR...')
reader_ppocr = PaddleOCR(use_angle_cls=True, lang='ru', show_log=False)


def draw_detected(
    image: np.ndarray,
    boxes_coordinates: list[list[list[float]]],
    color: tuple[int, int, int] = (0, 0, 255),
    thickness: int = 2,
) -> np.ndarray:
    work_img = image.copy()
    if boxes_coordinates:
        for box in boxes_coordinates:
            box = np.reshape(np.array(box), [-1, 1, 2]).astype(np.int32)
            work_img = cv2.polylines(work_img, [box], True, color, thickness)

    return work_img


def run_easyocr(image_cv2, image_pil, image_id: str, output_dir: Path) -> str:
    print('Running EasyOCR detection...')
    easyocr_detection = reader_easyocr.detect(image_cv2)
    easyocr_boxes = [
        [
            [coord[0], coord[2]],
            [coord[1], coord[2]],
            [coord[1], coord[3]],
            [coord[0], coord[3]],
        ]
        for coord in easyocr_detection[0][0]
    ] + easyocr_detection[1][0]
    easyocr_image = draw_detected(np.array(image_pil), easyocr_boxes)
    easyocr_output_path = output_dir / f'{image_id}_easyocr.jpg'
    cv2.imwrite(str(easyocr_output_path), easyocr_image)

    print('Running EasyOCR recognition...')
    easyocr_result = reader_easyocr.readtext(image_cv2)
    easyocr_text = '\n'.join([item[1] for item in easyocr_result]) + '\n'

    return easyocr_text


def run_paddleocr(image_cv2, image_pil, image_id: str, output_dir: Path) -> str:
    print('Running PaddleOCR detection...')
    ppocr_detection = reader_ppocr.ocr(image_cv2, rec=False)
    ppocr_boxes = ppocr_detection[0]
    ppocr_image = draw_detected(np.array(image_pil), ppocr_boxes)
    ppocr_output_path = output_dir / f'{image_id}_paddleocr.jpg'
    cv2.imwrite(str(ppocr_output_path), ppocr_image)

    print('Running PaddleOCR recognition...')
    ppocr_result = reader_ppocr.ocr(image_cv2, cls=True)
    ppocr_text = '\n'.join([item[1][0] for item in (ppocr_result[0] or [])]) + '\n'

    return ppocr_text


def run_tesseract(image_cv2, image_pil, image_id: str, output_dir: Path) -> str:
    print('Running Tesseract detection and recognition...')
    tesseract_data = pytesseract.image_to_data(
        image_pil, lang='rus+eng', output_type=Output.DATAFRAME
    )

    # Filter out empty results
    tesseract_data = tesseract_data[
        (tesseract_data.conf != -1) & (tesseract_data.text.str.strip() != '')
    ]

    # Draw boxes
    tesseract_boxes = []
    for _, row in tesseract_data.iterrows():
        x, y, w, h = row['left'], row['top'], row['width'], row['height']
        box = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        tesseract_boxes.append(box)
    tesseract_image = draw_detected(np.array(image_pil), tesseract_boxes)

    tesseract_output_path = output_dir / f'{image_id}_tesseract.jpg'
    cv2.imwrite(str(tesseract_output_path), tesseract_image)

    tesseract_text = '\n'.join(tesseract_data['text'].tolist()) + '\n'

    return tesseract_text


def process_image(filename: str) -> None:
    image_path = SAMPLES_DIR / filename
    image_cv2 = cv2.cvtColor(cv2.imread(str(image_path)), cv2.COLOR_BGR2RGB)
    image_pil = Image.open(image_path)

    sample_id = Path(filename).stem
    output_dir = SAMPLES_DIR / sample_id
    output_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = output_dir / f'{sample_id}.yml'
    if yaml_path.exists():
        print(f'Skipping {filename} as {yaml_path.name} already exists.')
        return

    texts = {
        'easyocr': run_easyocr(image_cv2, image_pil, sample_id, output_dir),
        'ppocr': run_paddleocr(image_cv2, image_pil, sample_id, output_dir),
        'tesseract': run_tesseract(image_cv2, image_pil, sample_id, output_dir),
    }
    result = {
        key: {'det': '', 'rec': '', 'result': text} for key, text in texts.items()
    }

    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(result, f, default_flow_style=False, allow_unicode=True)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        process_image(sys.argv[1])
    else:
        for filename in sorted(SAMPLES_DIR.glob('*.jpg')):
            print(f'Processing {filename.name}...')
            process_image(filename.name)
