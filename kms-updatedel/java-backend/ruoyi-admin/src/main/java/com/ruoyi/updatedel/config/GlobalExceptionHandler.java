package com.ruoyi.updatedel.config;

import com.ruoyi.common.core.domain.AjaxResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice("com.ruoyi.updatedel")
@Component("updatedelGlobalExceptionHandler")
public class GlobalExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

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
        log.error("Unhandled exception in updatedel module", ex);
        return AjaxResult.error("系统内部错误，请联系管理员");
    }
}
