from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StockStatus = Literal["IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK"]
MovementReason = Literal["RESTOCK", "SALE", "RETURN", "DAMAGED", "CORRECTION"]


class ProductBase(BaseModel):
    sku: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9\-_]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = Field(default="General", max_length=60)
    supplier: str = Field(default="Unknown", max_length=120)
    location: str = Field(default="Main Warehouse", max_length=60)
    reorder_level: int = Field(default=10, ge=0)
    unit_price: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)


class ProductCreate(ProductBase):
    quantity: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    """Partial update. Quantity is changed only through stock adjustments so every change is audited."""

    sku: str | None = Field(default=None, min_length=2, max_length=40, pattern=r"^[A-Za-z0-9\-_]+$")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, max_length=60)
    supplier: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=60)
    reorder_level: int | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class ProductOut(ProductBase):
    id: int
    quantity: int
    stock_status: StockStatus
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class StockAdjust(BaseModel):
    change: int = Field(description="Positive to add stock, negative to remove it")
    reason: MovementReason
    note: str = Field(default="", max_length=255)


class MovementOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    sku: str
    change: int
    quantity_after: int
    reason: MovementReason
    note: str
    created_at: datetime


class StatsOut(BaseModel):
    totalProducts: int
    totalUnits: int
    inventoryValue: Decimal
    lowStock: int
    outOfStock: int
    categories: int
