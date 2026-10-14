"""create products table"""
import sqlalchemy as sa
from alembic import op

revision = "0001_create_products"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=60), nullable=False, server_default="General"),
        sa.Column("supplier", sa.String(length=120), nullable=False, server_default="Unknown"),
        sa.Column("location", sa.String(length=60), nullable=False, server_default="Main Warehouse"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reorder_level", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity >= 0", name="ck_products_quantity_non_negative"),
    )
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)


def downgrade():
    op.drop_index("ix_products_sku", table_name="products")
    op.drop_table("products")
