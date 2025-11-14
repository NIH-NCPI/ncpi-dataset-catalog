from fastapi import APIRouter, Query
from services.dataset_service import ask

router = APIRouter(prefix="/ask")


@router.get("")
def ask_endpoint(q: str = Query(...)):
    response = {"question": q, "answer": ask(q)}
    print("response: ", response)
    return response
