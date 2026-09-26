"""Loads the Meher Sweets shop data and gives every piece of it a source ID.

Reads data/prices.csv, data/policies.md and data/business.md (never writes
to them) and exposes typed Product and Section records plus a rendered
text context suitable for a system prompt.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache

from meher_agent.config import Settings, settings as default_settings

_SECTION_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def slugify(text: str) -> str:
    """Lowercases text and turns it into a hyphen-separated slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text


def _parse_pack(pack: str) -> tuple[float, str]:
    """Parses a pack string like '1 kg', '500 g', '1 piece' or '1 box'."""
    match = re.match(r"([\d.]+)\s*(kg|g|piece|box)", pack.strip())
    if not match:
        raise ValueError(f"Cannot parse pack: {pack!r}")
    amount = float(match.group(1))
    unit = match.group(2)
    if unit == "kg":
        return amount * 1000, "g"
    return amount, unit


@dataclass(frozen=True)
class Product:
    sku: str
    item: str
    pack: str
    pack_size: float
    pack_unit: str
    price_inr: int
    type: str
    contains: list[str]
    shelf_life_days: int

    @property
    def source_id(self) -> str:
        return f"prices.csv#{self.sku}"


@dataclass(frozen=True)
class Section:
    id: str
    file: str
    heading: str
    text: str


def _load_products(data_dir) -> list[Product]:
    products: list[Product] = []
    with open(data_dir / "prices.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pack_size, pack_unit = _parse_pack(row["pack"])
            contains = [c.strip() for c in row["contains"].split(";") if c.strip()]
            products.append(
                Product(
                    sku=row["sku"],
                    item=row["item"],
                    pack=row["pack"],
                    pack_size=pack_size,
                    pack_unit=pack_unit,
                    price_inr=int(row["price_inr"]),
                    type=row["type"],
                    contains=contains,
                    shelf_life_days=int(row["shelf_life_days"]),
                )
            )
    return products


def _load_sections(data_dir, filename: str) -> list[Section]:
    text = (data_dir / filename).read_text(encoding="utf-8")
    sections: list[Section] = []

    matches = list(_SECTION_HEADING_RE.finditer(text))
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        section_id = f"{filename}#{slugify(heading)}"
        sections.append(Section(id=section_id, file=filename, heading=heading, text=body))
    return sections


@dataclass
class KnowledgeBase:
    products: list[Product]
    sections: list[Section]

    @property
    def valid_source_ids(self) -> set[str]:
        ids = {p.source_id for p in self.products}
        ids.update(s.id for s in self.sections)
        return ids

    def get_product(self, sku: str) -> Product | None:
        for product in self.products:
            if product.sku == sku:
                return product
        return None

    def get_section(self, section_id: str) -> Section | None:
        for section in self.sections:
            if section.id == section_id:
                return section
        return None

    def render_full_context(self) -> str:
        lines: list[str] = []
        lines.append("## Products")
        lines.append("")
        lines.append("| Source ID | Item | Pack | Price (INR) | Type | Contains | Shelf life (days) |")
        lines.append("|---|---|---|---|---|---|---|")
        for p in self.products:
            contains = "; ".join(p.contains) if p.contains else "-"
            lines.append(
                f"| {p.source_id} | {p.item} | {p.pack} | {p.price_inr} | {p.type} | "
                f"{contains} | {p.shelf_life_days} |"
            )
        lines.append("")

        for s in self.sections:
            lines.append(f"## [{s.id}] {s.heading}")
            lines.append("")
            lines.append(s.text)
            lines.append("")

        return "\n".join(lines).strip()

    def render_sections(self, ids: list[str]) -> str:
        lines: list[str] = []
        for source_id in ids:
            product = self.get_product(source_id.split("#", 1)[1]) if source_id.startswith("prices.csv#") else None
            if product is not None:
                contains = "; ".join(product.contains) if product.contains else "-"
                lines.append(
                    f"[{product.source_id}] {product.item}, {product.pack}, Rs {product.price_inr}, "
                    f"{product.type}, contains: {contains}, shelf life: {product.shelf_life_days} days"
                )
                continue
            section = self.get_section(source_id)
            if section is not None:
                lines.append(f"[{section.id}] {section.heading}")
                lines.append(section.text)
            lines.append("")
        return "\n".join(lines).strip()


@lru_cache(maxsize=None)
def _load_knowledge_base_cached(settings_obj: Settings) -> KnowledgeBase:
    products = _load_products(settings_obj.paths.data_dir)
    sections = _load_sections(settings_obj.paths.data_dir, "policies.md")
    sections += _load_sections(settings_obj.paths.data_dir, "business.md")
    return KnowledgeBase(products=products, sections=sections)


def load_knowledge_base(settings_obj: Settings | None = None) -> KnowledgeBase:
    return _load_knowledge_base_cached(settings_obj or default_settings)
