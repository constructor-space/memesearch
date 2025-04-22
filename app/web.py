from fastapi import FastAPI
from fastapi.responses import FileResponse
import uvicorn

from app.config import IMAGES_DIR, config


app = FastAPI()


@app.get('/{sha256}.jpg')
async def get_file(sha256: str):
    return FileResponse(IMAGES_DIR / f'{sha256}.jpg')


if __name__ == '__main__':
    uvicorn.run(app, host=config.host, port=config.port)
