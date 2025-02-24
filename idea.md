# Memesearch

## Idea
Develop a website that allows to search memes

## Problem
It's hard to find that exact meme when you need it. Search engines don’t always provide good results and most of the existing solutions don’t support Russian.

## Product Results
- **Meme indexing**: Memes from popular Telegram channels are processed and indexed
- **Text search**: Search memes by text on them
- **Context search**: Search memes by the context (e.g. "wolf" search query returns all memes with a picture of a wolf)
- **Image search**: Get meme source by uploading an image

## Learning Value
- **Programming Language**: Python for backend, SolidJS or Svelte for frontend
- **Database**: PostgreSQL
- **Search Engine**: Elasticsearch
- **Image search**: some image hashing algorithm
- **ML**: OCR model (maybe https://github.com/JaidedAI/EasyOCR), probably some CLIP model for image recognition for the context search (https://github.com/mlfoundations/open_clip)

## Potential Problems
- Existing solutions
- Efficiently indexing text
- Efficiently indexing image hashes to allow approximate matches
- Model fine-tuning may be needed to correctly work with memes (text may be distorted for OCR model to recongize properly, pre-trained CLIP models may not work well with weird memes)
- CLIP models may not be able to generate descriptions in Russian when needed
- Scaling issues: indexing a large amount of channels quickly, real-time index updates
- Dataset cleaning: distinguishing memes from non-memes
