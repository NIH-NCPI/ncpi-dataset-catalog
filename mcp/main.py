from fastapi import FastAPI
from controllers.dataset_controller import router as dataset_router

app = FastAPI(title="NCPI RAG Server")

# Register controller(s)
app.include_router(dataset_router)
