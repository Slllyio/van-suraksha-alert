"""Start the field system: python run.py  (then open http://<this-pc>:8000)"""
import logging, os, uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
if __name__ == "__main__":
    uvicorn.run("app.server:app", host=os.environ.get("FS_HOST", "0.0.0.0"), port=int(os.environ.get("FS_PORT", "8000")))
