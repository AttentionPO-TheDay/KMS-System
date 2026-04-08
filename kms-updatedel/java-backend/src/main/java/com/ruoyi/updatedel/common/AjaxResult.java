package com.ruoyi.updatedel.common;

import java.util.HashMap;

public class AjaxResult extends HashMap<String, Object> {
    public static final int SUCCESS_CODE = 200;

    public AjaxResult() {
    }

    public AjaxResult(int code, String msg) {
        put("code", code);
        put("msg", msg);
    }

    public AjaxResult(int code, String msg, Object data) {
        put("code", code);
        put("msg", msg);
        put("data", data);
    }

    public static AjaxResult success() {
        return new AjaxResult(200, "操作成功");
    }

    public static AjaxResult success(Object data) {
        return new AjaxResult(200, "操作成功", data);
    }

    public static AjaxResult success(String msg, Object data) {
        return new AjaxResult(200, msg, data);
    }

    public static AjaxResult error(String msg) {
        return new AjaxResult(500, msg);
    }

    public static AjaxResult error(int code, String msg) {
        return new AjaxResult(code, msg);
    }
}
