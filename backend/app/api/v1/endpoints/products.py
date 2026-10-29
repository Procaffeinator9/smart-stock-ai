from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path

from app.analytics.inventory import inventory_positions
from app.api.v1.common import (
    Page,
    PageParams,
    SearchQuery,
    SortOrder,
    contains,
    page_params,
    paginate,
    require_choice,
    require_known,
    sort_items,
)
from app.api.v1.schemas import ProductDetailOut, ProductOut
from app.data.dataset import RetailDataset
from app.data.repository import get_dataset
from app.synthetic.generator import Product

router = APIRouter(prefix="/products", tags=["products"])

ProductSort = Literal["product_id", "product_name", "category", "unit_cost", "selling_price", "created_at"]


def product_out(dataset: RetailDataset, product: Product) -> dict[str, Any]:
    return {**asdict(product), "supplier_name": dataset.supplier_by_id[product.supplier_id].supplier_name}


@router.get("", response_model=Page[ProductOut], summary="List products")
def list_products(
    dataset: RetailDataset = Depends(get_dataset),
    paging: PageParams = Depends(page_params),
    search: SearchQuery = None,
    category: str | None = None,
    supplier_id: str | None = None,
    sort: ProductSort = "product_id",
    order: SortOrder = "asc",
):
    """Search matches product name, SKU, or product ID."""
    require_choice("category", category, dataset.categories)
    require_known("supplier_id", supplier_id, dataset.supplier_by_id)
    rows = [
        p
        for p in dataset.products
        if (category is None or p.category == category)
        and (supplier_id is None or p.supplier_id == supplier_id)
        and contains(search, p.product_name, p.sku, p.product_id)
    ]
    key = (lambda p: p.product_name.lower()) if sort == "product_name" else (lambda p: getattr(p, sort))
    return paginate(sort_items(rows, key, order), paging, lambda p: product_out(dataset, p))


@router.get("/{product_id}", response_model=ProductDetailOut, summary="Get a product with its stock by store")
def get_product(
    product_id: Annotated[str, Path(max_length=32)],
    dataset: RetailDataset = Depends(get_dataset),
):
    product = dataset.product_by_id.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    stock = [asdict(p) for p in inventory_positions(dataset, dataset.as_of) if p.product_id == product_id] if dataset.as_of else []
    return {**product_out(dataset, product), "as_of": dataset.as_of, "stock": stock}
