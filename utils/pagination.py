def paginate(items, page=1, page_size=10):
    start = max(page - 1, 0) * page_size
    end = start + page_size
    return items[start:end]
