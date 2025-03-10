## Meme sources

### Existing datasets

- None of the datasets I found are still updated.
- [link](https://arxiv.org/abs/2501.13851),
[link](https://blogs.loc.gov/thesignal/2018/10/data-mining-memes-in-the-digital-culture-web-archive/),
[link](https://paperswithcode.com/datasets?mod=images&page=1&task=meme-classification),
[link](https://www.kaggle.com/datasets/hammadjavaid/6992-labeled-meme-images-dataset)
- Can still be used for testing and quality evaluation on early
stages of the project

### Telegram

- We can use already existing tools (Vox-Harbor, telegram map)
to scrap memes from various channels in real time
- Since the interface of our project will be an inline Telegram bot,
our main audience is Telegram users. The memes they're looking for
are more likely to be found on Telegram itself than on any other 
platform
- Problem: how to separate memes from other images? Meme channels
from other channels?

### Reddit

- We can target specific subreddits that are made exclusively for
memes; easier than filtering out Telegram channels
- Existing embeddings of subreddits (e. g. https://github.com/anvaka/map-of-reddit)
could help