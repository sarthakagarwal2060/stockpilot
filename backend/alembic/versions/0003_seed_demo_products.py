"""seed demo products so a fresh environment has data to show"""
import sqlalchemy as sa
from alembic import op

revision = "0003_seed_demo_products"
down_revision = "0002_create_stock_movements"
branch_labels = None
depends_on = None

DEMO_PRODUCTS = [
    ("ELEC-1001", "Wireless Barcode Scanner", "Electronics", "ScanTech Ltd", "Aisle A1", 42, 10, 3499.00),
    ("ELEC-1002", "Thermal Label Printer", "Electronics", "PrintPro", "Aisle A2", 6, 8, 12999.00),
    ("PACK-2001", "Corrugated Box 12x12x12", "Packaging", "BoxCo", "Aisle C4", 850, 200, 28.50),
    ("PACK-2002", "Bubble Wrap Roll 50m", "Packaging", "BoxCo", "Aisle C5", 0, 15, 649.00),
    ("SAFE-3001", "Safety Gloves (Pair)", "Safety", "SafeWorks", "Aisle D1", 120, 50, 149.00),
    ("SAFE-3002", "Hi-Vis Vest", "Safety", "SafeWorks", "Aisle D2", 14, 20, 299.00),
    ("FURN-4001", "Steel Shelving Unit", "Furniture", "RackMasters", "Bay F1", 9, 3, 7899.00),
]


def upgrade():
    products = sa.table(
        "products",
        sa.column("sku", sa.String), sa.column("name", sa.String), sa.column("category", sa.String),
        sa.column("supplier", sa.String), sa.column("location", sa.String), sa.column("quantity", sa.Integer),
        sa.column("reorder_level", sa.Integer), sa.column("unit_price", sa.Numeric),
    )
    op.bulk_insert(products, [
        dict(sku=s, name=n, category=c, supplier=sup, location=loc, quantity=q, reorder_level=r, unit_price=p)
        for s, n, c, sup, loc, q, r, p in DEMO_PRODUCTS
    ])


def downgrade():
    skus = ", ".join(f"'{p[0]}'" for p in DEMO_PRODUCTS)
    op.execute(f"DELETE FROM products WHERE sku IN ({skus})")
