import uvicorn
from fastapi import FastAPI

app = FastAPI(title="Passanorte API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items/{item_id}")
def get_item(item_id: int, q: str | None = None) -> dict[str, object]:
    item = {"item_id": item_id, "name": f"Item {item_id}"}
    if q:
        item["q"] = q
    return item


def main() -> None:
    uvicorn.run("passanorte_back.main:app", host="0.0.0.0", port=8000, reload=True)