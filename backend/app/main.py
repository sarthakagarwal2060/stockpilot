from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Product, StockMovement
from .schemas import MovementOut, ProductCreate, ProductOut, ProductUpdate, StatsOut, StockAdjust

# Docs live under /api so they are reachable through the frontend proxy and the Ingress /api route.
app = FastAPI(title=settings.app_name, version=settings.app_version, docs_url="/api/docs",
              redoc_url=None, openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
Instrumentator(excluded_handlers=["/metrics", "/health", "/ready"]).instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)

STOCK_ADJUSTMENTS = Counter(
    "stockpilot_stock_adjustments_total", "Stock adjustments applied, by reason", ["reason"]
)
STOCK_UNITS_MOVED = Counter(
    "stockpilot_stock_units_moved_total", "Absolute number of units moved, by direction", ["direction"]
)


@app.get("/", tags=["meta"])
def root():
    return {"service": settings.app_name, "version": settings.app_version, "docs": "/api/docs"}


@app.get("/health", tags=["meta"])
def health():
    """Liveness: the process is up. Deliberately does not touch the database."""
    return {"status": "UP"}


@app.get("/ready", tags=["meta"])
def ready(db: Session = Depends(get_db)):
    """Readiness: the app can serve traffic, which requires a working database connection."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any DB failure means not ready
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "READY"}


api = APIRouter(prefix="/api", tags=["inventory"])


def _get_product_or_404(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A product with this SKU already exists") from exc


@api.get("/products", response_model=list[ProductOut])
def list_products(
    search: str | None = Query(default=None, max_length=100),
    category: str | None = None,
    stock_status: Literal["IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK"] | None = None,
    db: Session = Depends(get_db),
):
    query = select(Product).order_by(Product.name)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Product.name.ilike(pattern), Product.sku.ilike(pattern), Product.supplier.ilike(pattern)))
    if category:
        query = query.where(Product.category == category)
    if stock_status == "OUT_OF_STOCK":
        query = query.where(Product.quantity <= 0)
    elif stock_status == "LOW_STOCK":
        query = query.where(Product.quantity > 0, Product.quantity <= Product.reorder_level)
    elif stock_status == "IN_STOCK":
        query = query.where(Product.quantity > Product.reorder_level)
    return list(db.scalars(query))


@api.get("/products/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)):
    total, units, value, categories = db.execute(
        select(
            func.count(Product.id),
            func.coalesce(func.sum(Product.quantity), 0),
            func.coalesce(func.sum(Product.quantity * Product.unit_price), 0),
            func.count(func.distinct(Product.category)),
        )
    ).one()
    out_of_stock = db.scalar(select(func.count(Product.id)).where(Product.quantity <= 0))
    low_stock = db.scalar(
        select(func.count(Product.id)).where(Product.quantity > 0, Product.quantity <= Product.reorder_level)
    )
    return StatsOut(
        totalProducts=total,
        totalUnits=units,
        inventoryValue=Decimal(value).quantize(Decimal("0.01")),
        lowStock=low_stock,
        outOfStock=out_of_stock,
        categories=categories,
    )


@api.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    return _get_product_or_404(db, product_id)


@api.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    product = Product(**payload.model_dump())
    product.sku = product.sku.upper()
    db.add(product)
    _commit_or_conflict(db)
    if product.quantity:
        db.add(StockMovement(product_id=product.id, change=product.quantity, quantity_after=product.quantity,
                             reason="RESTOCK", note="Initial stock"))
        db.commit()
    db.refresh(product)
    return product


@api.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    product = _get_product_or_404(db, product_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value.upper() if key == "sku" else value)
    _commit_or_conflict(db)
    db.refresh(product)
    return product


@api.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = _get_product_or_404(db, product_id)
    db.delete(product)
    db.commit()


@api.post("/products/{product_id}/adjust", response_model=ProductOut)
def adjust_stock(product_id: int, payload: StockAdjust, db: Session = Depends(get_db)):
    if payload.change == 0:
        raise HTTPException(status_code=422, detail="Change must be non-zero")
    product = _get_product_or_404(db, product_id)
    new_quantity = product.quantity + payload.change
    if new_quantity < 0:
        raise HTTPException(
            status_code=409, detail=f"Insufficient stock: {product.quantity} on hand, tried to remove {-payload.change}"
        )
    product.quantity = new_quantity
    db.add(StockMovement(product_id=product.id, change=payload.change, quantity_after=new_quantity,
                         reason=payload.reason, note=payload.note))
    db.commit()
    db.refresh(product)
    STOCK_ADJUSTMENTS.labels(reason=payload.reason).inc()
    STOCK_UNITS_MOVED.labels(direction="in" if payload.change > 0 else "out").inc(abs(payload.change))
    return product


@api.get("/movements", response_model=list[MovementOut])
def list_movements(limit: int = Query(default=20, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.execute(
        select(StockMovement, Product.name, Product.sku)
        .join(Product, StockMovement.product_id == Product.id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(limit)
    ).all()
    return [
        MovementOut(
            id=m.id, product_id=m.product_id, product_name=name, sku=sku, change=m.change,
            quantity_after=m.quantity_after, reason=m.reason, note=m.note, created_at=m.created_at,
        )
        for m, name, sku in rows
    ]


app.include_router(api)
