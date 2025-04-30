from fastapi import FastAPI
from fastapi.responses import FileResponse
import uvicorn

from app.config import IMAGES_DIR, config


app = FastAPI()


@app.get('/{phash}.jpg')
async def get_file(phash: str):
    return FileResponse(IMAGES_DIR / f'{phash}.jpg')


if __name__ == '__main__':
    uvicorn.run(app, host=config.host, port=config.port)
