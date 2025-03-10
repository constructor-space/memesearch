## Models list

- https://github.com/PaddlePaddle/PaddleOCR/blob/main/README_en.md
- https://github.com/open-mmlab/mmocr doesn't support Russian
- https://github.com/JaidedAI/EasyOCR
- https://github.com/tesseract-ocr/tesseract

## Model rating

There is an online comparison tool that allows to compare these 3 models
with different parameters:
https://huggingface.co/spaces/Loren/Streamlit_OCR_comparator

We created a simple tool to batch-process images based on the ocr comparator tool.
Then each result was manually rated using the criteria below.
The results are saved to samples directory.

## Rating criteria

- Detection
  - 0 -- Failed to detect most of the text
  - 1 -- Detected most of the text, or there are minor artifacts
  - 2 -- Detected enough text to find the meme easily
- Recognition
  - 0 -- A lot of gibberish text (e.g. characters replaced with similar looking ones)
  - 1 -- Most of the text was recognized correctly, but the quality is not enough to find the meme easily
  - 2 -- Produced a searchable result

## Results


|             | EasyOCR | PaddleOCR | Tesseract |
|-------------|---------|-----------|-----------|
| Detection   | 10      | 10        | 8         |
| Recognition | 9       | 6         | 7         |
| Total       | 19      | 16        | 15        |

No models recognize distorted or handwritten text properly.
EasyOCR and Tesseract showed the best results on most samples, but paddleocr works well on specific cases

