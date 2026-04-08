package com.ruoyi.updatedel.config;

import com.ruoyi.common.core.domain.AjaxResult;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(IllegalStateException.class)
    public AjaxResult handleIllegalState(IllegalStateException ex) {
        return AjaxResult.error(ex.getMessage());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public AjaxResult handleIllegalArgument(IllegalArgumentException ex) {
        return AjaxResult.error(ex.getMessage());
    }

    @ExceptionHandler(Exception.class)
    public AjaxResult handleException(Exception ex) {
        return AjaxResult.error("系统内部错误: " + ex.getMessage());
    }
}
