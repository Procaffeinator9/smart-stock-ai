"""Deterministic synthetic retail data generator.

Produces suppliers, products, sales, inventory snapshots, and purchase orders whose columns
match the Delta tables in ``databricks/sql/``. All randomness comes from a single
``random.Random(seed)`` and all dates derive from ``GeneratorConfig.start_date`` (never the
wall clock), so the same config always yields byte-identical output.

Sales, inventory, and purchase orders come from a day-by-day simulation per store/product:
end-of-day stock = previous stock + deliveries - sales, and a purchase order is raised when
the inventory position (on hand + on order) drops to the reorder point.
"""

import csv
import dataclasses
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

CENT = Decimal("0.01")

# category -> (sku code, unit cost range, markup range, shelf life range or None, mean daily demand range)
CATEGORIES: dict[str, tuple[str, tuple[float, float], tuple[float, float], tuple[int, int] | None, tuple[float, float]]] = {
    "Produce": ("PRD", (0.40, 4.00), (1.40, 1.90), (4, 14), (3.0, 12.0)),
    "Dairy": ("DRY", (0.80, 6.00), (1.30, 1.70), (7, 30), (2.0, 9.0)),
    "Bakery": ("BAK", (0.90, 5.00), (1.50, 2.00), (2, 7), (2.0, 8.0)),
    "Beverages": ("BEV", (0.50, 8.00), (1.30, 1.80), (180, 540), (2.0, 10.0)),
    "Pantry": ("PAN", (0.70, 9.00), (1.25, 1.60), (180, 730), (1.0, 6.0)),
    "Frozen": ("FRZ", (1.50, 12.00), (1.30, 1.70), (90, 365), (1.0, 5.0)),
    "Household": ("HSH", (1.00, 15.00), (1.30, 1.80), None, (0.5, 3.0)),
    "Personal Care": ("PCR", (1.00, 14.00), (1.40, 2.00), None, (0.5, 3.0)),
}

PRODUCT_WORDS: dict[str, tuple[list[str], list[str]]] = {
    "Produce": (["Organic", "Fresh", "Local", "Premium"], ["Apples", "Bananas", "Spinach", "Carrots", "Tomatoes", "Avocados"]),
    "Dairy": (["Whole", "Low-Fat", "Organic", "Greek"], ["Milk", "Yogurt", "Cheddar", "Butter", "Cream Cheese"]),
    "Bakery": (["Sourdough", "Whole Wheat", "Multigrain", "Artisan"], ["Bread", "Bagels", "Muffins", "Rolls", "Croissants"]),
    "Beverages": (["Sparkling", "Cold Brew", "Natural", "Diet"], ["Water", "Coffee", "Juice", "Iced Tea", "Soda"]),
    "Pantry": (["Classic", "Organic", "Family Size", "Whole Grain"], ["Pasta", "Rice", "Cereal", "Peanut Butter", "Olive Oil"]),
    "Frozen": (["Frozen", "Family", "Gourmet", "Lite"], ["Pizza", "Vegetables", "Berries", "Dumplings", "Ice Cream"]),
    "Household": (["Eco", "Ultra", "Value", "Lavender"], ["Detergent", "Paper Towels", "Dish Soap", "Trash Bags"]),
    "Personal Care": (["Gentle", "Fresh", "Sensitive", "Daily"], ["Shampoo", "Toothpaste", "Body Wash", "Deodorant"]),
}

SUPPLIER_PREFIXES = ["Northwind", "Bluefield", "Greenvale", "Summit", "Riverside", "Oakridge", "Harbor", "Prairie", "Silverline", "Maple"]
SUPPLIER_SUFFIXES = ["Foods", "Distribution", "Wholesale", "Supply Co", "Trading"]

# Monday..Sunday demand multipliers.
WEEKDAY_FACTORS = (0.90, 0.85, 0.90, 0.95, 1.10, 1.30, 1.20)
PROMO_DEMAND_UPLIFT = 1.6
SERVICE_LEVEL_Z = 1.65  # ~95% cycle service level
REVIEW_DAYS = 14  # order-up-to covers this many days of demand above the reorder point
CANCELLATION_RATE = 0.02


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int = 42
    num_suppliers: int = 20
    num_products: int = 200
    num_stores: int = 5
    start_date: date = date(2026, 1, 1)
    num_days: int = 90

    def __post_init__(self) -> None:
        for name in ("num_suppliers", "num_products", "num_stores", "num_days"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=self.num_days - 1)


# Record field names and order match the Delta table columns exactly.


@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    supplier_name: str
    contact_email: str
    lead_time_days: int
    minimum_order_quantity: int
    reliability_score: Decimal


@dataclass(frozen=True)
class Product:
    product_id: str
    sku: str
    product_name: str
    category: str
    unit_cost: Decimal
    selling_price: Decimal
    supplier_id: str
    shelf_life_days: int | None
    created_at: datetime


@dataclass(frozen=True)
class Sale:
    sale_id: str
    sale_date: date
    store_id: str
    product_id: str
    quantity_sold: int
    unit_selling_price: Decimal
    promotion_applied: bool


@dataclass(frozen=True)
class InventorySnapshot:
    inventory_id: str
    snapshot_date: date
    store_id: str
    product_id: str
    quantity_on_hand: int
    quantity_reserved: int
    reorder_point: int
    safety_stock: int


@dataclass(frozen=True)
class PurchaseOrder:
    purchase_order_id: str
    supplier_id: str
    product_id: str
    store_id: str
    order_date: date
    expected_delivery_date: date
    actual_delivery_date: date | None
    quantity_ordered: int
    unit_cost: Decimal
    order_status: str


# Delta table name -> record type, in foreign-key dependency order.
TABLE_RECORD_TYPES: dict[str, type] = {
    "suppliers": Supplier,
    "products": Product,
    "sales": Sale,
    "inventory": InventorySnapshot,
    "purchase_orders": PurchaseOrder,
}


@dataclass
class GeneratedDataset:
    config: GeneratorConfig
    stores: list[str]
    suppliers: list[Supplier]
    products: list[Product]
    sales: list[Sale]
    inventory: list[InventorySnapshot]
    purchase_orders: list[PurchaseOrder]

    def tables(self) -> dict[str, list]:
        return {
            "suppliers": self.suppliers,
            "products": self.products,
            "sales": self.sales,
            "inventory": self.inventory,
            "purchase_orders": self.purchase_orders,
        }


@dataclass
class _StockState:
    """Mutable per store/product simulation state."""

    demand_rate: float
    reorder_point: int
    safety_stock: int
    order_up_to: int
    on_hand: int
    # (arrival date, quantity) for orders placed but not yet received.
    pending: list[tuple[date, int]] = field(default_factory=list)


def _money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _poisson(rng: random.Random, lam: float) -> int:
    # Knuth's algorithm; fine for the small rates used here.
    threshold = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


def _generate_suppliers(rng: random.Random, config: GeneratorConfig) -> list[Supplier]:
    suppliers = []
    for i in range(1, config.num_suppliers + 1):
        prefix = SUPPLIER_PREFIXES[(i - 1) % len(SUPPLIER_PREFIXES)]
        suffix = SUPPLIER_SUFFIXES[((i - 1) // len(SUPPLIER_PREFIXES)) % len(SUPPLIER_SUFFIXES)]
        name = f"{prefix} {suffix}"
        if i > len(SUPPLIER_PREFIXES) * len(SUPPLIER_SUFFIXES):
            name = f"{name} {i}"
        slug = "".join(ch for ch in name.lower() if ch.isalnum())
        suppliers.append(
            Supplier(
                supplier_id=f"SUP-{i:04d}",
                supplier_name=name,
                # example.com is reserved (RFC 2606), so these can never reach a real inbox.
                contact_email=f"orders@{slug}.example.com",
                lead_time_days=rng.randint(2, 14),
                minimum_order_quantity=rng.choice([12, 24, 36, 48, 60, 100]),
                reliability_score=Decimal(f"{rng.uniform(0.70, 0.99):.3f}"),
            )
        )
    return suppliers


def _generate_products(rng: random.Random, config: GeneratorConfig, suppliers: list[Supplier]) -> list[Product]:
    category_names = list(CATEGORIES)
    epoch = datetime.combine(config.start_date, time())
    products = []
    for i in range(1, config.num_products + 1):
        category = category_names[(i - 1) % len(category_names)]
        code, cost_range, markup_range, shelf_life_range, _ = CATEGORIES[category]
        adjectives, nouns = PRODUCT_WORDS[category]
        unit_cost = _money(rng.uniform(*cost_range))
        selling_price = max(_money(float(unit_cost) * rng.uniform(*markup_range)), unit_cost + CENT)
        products.append(
            Product(
                product_id=f"PRD-{i:05d}",
                sku=f"SKU-{code}-{i:05d}",
                product_name=f"{rng.choice(adjectives)} {rng.choice(nouns)}",
                category=category,
                unit_cost=unit_cost,
                selling_price=selling_price,
                supplier_id=rng.choice(suppliers).supplier_id,
                shelf_life_days=rng.randint(*shelf_life_range) if shelf_life_range else None,
                created_at=epoch - timedelta(days=rng.randint(30, 730), seconds=rng.randint(0, 86_399)),
            )
        )
    return products


def _promotion_days(rng: random.Random, config: GeneratorConfig) -> set[int]:
    """Day offsets on which a product is on promotion: 0-2 windows of 3-7 days."""
    days: set[int] = set()
    for _ in range(rng.randint(0, 2)):
        length = rng.randint(3, 7)
        start = rng.randint(0, max(0, config.num_days - length))
        days.update(range(start, min(start + length, config.num_days)))
    return days


def generate_dataset(config: GeneratorConfig | None = None) -> GeneratedDataset:
    config = config or GeneratorConfig()
    rng = random.Random(config.seed)

    stores = [f"STR-{i:03d}" for i in range(1, config.num_stores + 1)]
    suppliers = _generate_suppliers(rng, config)
    products = _generate_products(rng, config, suppliers)
    supplier_by_id = {s.supplier_id: s for s in suppliers}

    # Promotions are chain-wide: same product, same days, same discount in every store.
    promotions = {p.product_id: (_promotion_days(rng, config), rng.uniform(0.10, 0.25)) for p in products}
    store_factors = {store: rng.uniform(0.7, 1.3) for store in stores}

    states: dict[tuple[str, str], _StockState] = {}
    for store in stores:
        for product in products:
            lead_time = supplier_by_id[product.supplier_id].lead_time_days
            rate = rng.uniform(*CATEGORIES[product.category][4]) * store_factors[store]
            safety_stock = math.ceil(SERVICE_LEVEL_Z * math.sqrt(rate * lead_time))
            reorder_point = math.ceil(rate * lead_time) + safety_stock
            order_up_to = reorder_point + math.ceil(rate * REVIEW_DAYS)
            states[(store, product.product_id)] = _StockState(
                demand_rate=rate,
                reorder_point=reorder_point,
                safety_stock=safety_stock,
                order_up_to=order_up_to,
                on_hand=rng.randint(reorder_point, order_up_to),
            )

    sales: list[Sale] = []
    inventory: list[InventorySnapshot] = []
    purchase_orders: list[PurchaseOrder] = []

    # Day-outer iteration keeps generated IDs in chronological order.
    for day_offset in range(config.num_days):
        day = config.start_date + timedelta(days=day_offset)
        weekday_factor = WEEKDAY_FACTORS[day.weekday()]
        for store in stores:
            for product in products:
                state = states[(store, product.product_id)]
                supplier = supplier_by_id[product.supplier_id]

                arrived = [qty for arrival, qty in state.pending if arrival == day]
                state.on_hand += sum(arrived)
                state.pending = [(arrival, qty) for arrival, qty in state.pending if arrival != day]

                promo_days, discount = promotions[product.product_id]
                on_promo = day_offset in promo_days
                demand = _poisson(rng, state.demand_rate * weekday_factor * (PROMO_DEMAND_UPLIFT if on_promo else 1.0))
                sold = min(demand, state.on_hand)
                if sold > 0:
                    price = _money(float(product.selling_price) * (1 - discount)) if on_promo else product.selling_price
                    sales.append(
                        Sale(
                            sale_id=f"SAL-{len(sales) + 1:08d}",
                            sale_date=day,
                            store_id=store,
                            product_id=product.product_id,
                            quantity_sold=sold,
                            unit_selling_price=max(price, CENT),
                            promotion_applied=on_promo,
                        )
                    )
                    state.on_hand -= sold

                inventory.append(
                    InventorySnapshot(
                        inventory_id=f"INV-{len(inventory) + 1:08d}",
                        snapshot_date=day,
                        store_id=store,
                        product_id=product.product_id,
                        quantity_on_hand=state.on_hand,
                        # Units held for online/click-and-collect orders.
                        quantity_reserved=rng.randint(0, state.on_hand // 20),
                        reorder_point=state.reorder_point,
                        safety_stock=state.safety_stock,
                    )
                )

                position = state.on_hand + sum(qty for _, qty in state.pending)
                if position <= state.reorder_point:
                    quantity = max(supplier.minimum_order_quantity, state.order_up_to - position)
                    expected = day + timedelta(days=supplier.lead_time_days)
                    delay = rng.randint(1, 5) if rng.random() > float(supplier.reliability_score) else 0
                    actual = expected + timedelta(days=delay)
                    if rng.random() < CANCELLATION_RATE:
                        status, actual_delivery = "CANCELLED", None
                    elif actual <= config.end_date:
                        status, actual_delivery = "DELIVERED", actual
                        state.pending.append((actual, quantity))
                    else:
                        status, actual_delivery = ("PLACED" if day == config.end_date else "IN_TRANSIT"), None
                        state.pending.append((actual, quantity))
                    purchase_orders.append(
                        PurchaseOrder(
                            purchase_order_id=f"PO-{len(purchase_orders) + 1:07d}",
                            supplier_id=supplier.supplier_id,
                            product_id=product.product_id,
                            store_id=store,
                            order_date=day,
                            expected_delivery_date=expected,
                            actual_delivery_date=actual_delivery,
                            quantity_ordered=quantity,
                            unit_cost=product.unit_cost,
                            order_status=status,
                        )
                    )

    return GeneratedDataset(
        config=config,
        stores=stores,
        suppliers=suppliers,
        products=products,
        sales=sales,
        inventory=inventory,
        purchase_orders=purchase_orders,
    )


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value)


def write_csv(dataset: GeneratedDataset, output_dir: Path) -> dict[str, Path]:
    """Write one CSV per table (header = Delta column names). Returns table name -> path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for table, records in dataset.tables().items():
        path = output_dir / f"{table}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow([f.name for f in dataclasses.fields(TABLE_RECORD_TYPES[table])])
            for record in records:
                writer.writerow([_csv_value(v) for v in dataclasses.astuple(record)])
        paths[table] = path
    return paths
