package com.lgcollege.common;

import java.util.List;

public class PageResult<T> {
    private final int page;
    private final int pageSize;
    private final long total;
    private final int totalPages;
    private final List<T> records;

    public PageResult(int page, int pageSize, long total, List<T> records) {
        this.page = page;
        this.pageSize = pageSize;
        this.total = total;
        this.totalPages = total == 0 ? 0 : (int) ((total + pageSize - 1) / pageSize);
        this.records = records;
    }

    public int getPage() {
        return page;
    }

    public int getPageSize() {
        return pageSize;
    }

    public long getTotal() {
        return total;
    }

    public int getTotalPages() {
        return totalPages;
    }

    public List<T> getRecords() {
        return records;
    }
}
