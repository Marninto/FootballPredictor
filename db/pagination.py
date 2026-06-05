from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class Page:
    items: list
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self):
        return max(ceil(self.total_items / self.page_size), 1)

    @property
    def has_previous(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.total_pages


def paginate_query(db, statement, page=1, page_size=10):
    page = max(int(page), 1)
    page_size = max(int(page_size), 1)
    total_items = len(db.scalars(statement).all())
    items = db.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=items, page=page, page_size=page_size, total_items=total_items)
