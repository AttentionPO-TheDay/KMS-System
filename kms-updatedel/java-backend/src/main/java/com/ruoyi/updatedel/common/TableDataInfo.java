package com.ruoyi.updatedel.common;

import java.util.List;

public class TableDataInfo {
    private int code = 200;
    private String msg = "查询成功";
    private List<?> rows;
    private long total;

    public TableDataInfo() {
    }

    public TableDataInfo(List<?> rows, long total) {
        this.rows = rows;
        this.total = total;
    }

    public int getCode() {
        return code;
    }

    public void setCode(int code) {
        this.code = code;
    }

    public String getMsg() {
        return msg;
    }

    public void setMsg(String msg) {
        this.msg = msg;
    }

    public List<?> getRows() {
        return rows;
    }

    public void setRows(List<?> rows) {
        this.rows = rows;
    }

    public long getTotal() {
        return total;
    }

    public void setTotal(long total) {
        this.total = total;
    }
}
