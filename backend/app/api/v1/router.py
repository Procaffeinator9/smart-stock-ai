from fastapi import APIRouter

from app.api.v1.endpoints import (
    data_source,
    health,
    inventory,
    overview,
    products,
    purchase_orders,
    replenishment,
    sales,
    suppliers,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(data_source.router)
# Read-only data API (GET only), backed by the configured data source.
api_router.include_router(products.router)
api_router.include_router(suppliers.router)
api_router.include_router(sales.router)
api_router.include_router(purchase_orders.router)
api_router.include_router(inventory.router)
api_router.include_router(overview.router)
api_router.include_router(replenishment.router)
