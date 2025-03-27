import json
import os
from pathlib import Path

import cv2
import easyocr
from tqdm import tqdm

reader_easyocr = easyocr.Reader(['ru', 'en'])


def run_easyocr(image_path: str) -> str:
    image_cv2 = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
    easyocr_result = reader_easyocr.readtext(image_cv2)
    easyocr_text = '\n'.join([item[1] for item in easyocr_result]) + '\n'
    return easyocr_text



def main():
    out_file = Path(__file__).absolute().parent.parent / 'postgres_search' / 'data.json'
    if out_file.exists():
        res = json.loads(out_file.read_text())
    else:
        res = []
    input_dir = input('Enter images dir: ')
    files_prev = {item['name'] for item in res}
    files = sorted([x for x in Path(input_dir).rglob('*.jpg') if x.name not in files_prev])
    for i, file in tqdm(enumerate(files), total=len(files)):
        name = os.path.basename(file)
        text = run_easyocr(str(file))
        res.append({'name': name, 'text': text})
        if i % 100 == 0:
            out_file.write_text(json.dumps(res, ensure_ascii=False))
    out_file.write_text(json.dumps(res, ensure_ascii=False))



if __name__ == '__main__':
    main()
