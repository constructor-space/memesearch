import easyocr
import open_clip


if __name__ == '__main__':
    eocr = easyocr.Reader(['ru', 'en'])
    open_clip.create_model_from_pretrained('hf-hub:timm/ViT-SO400M-16-SigLIP2-384')
