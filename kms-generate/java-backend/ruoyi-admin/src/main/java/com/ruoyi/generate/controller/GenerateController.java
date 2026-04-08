package com.ruoyi.generate.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateKeyService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 生成记录查询控制器
 * 提供密钥生成结果的查询接口
 */
@RestController
@RequestMapping("/generate/key")
public class GenerateController extends BaseController {

    private static final Logger log = LoggerFactory.getLogger(GenerateController.class);

    @Autowired
    private GenerateKeyService generateKeyService;

    /**
     * 查询生成密钥列表
     * GET /generate/key/list
     */
    @GetMapping("/list")
    public TableDataInfo list(Keymanage query) {
        startPage();
        List<Keymanage> list = generateKeyService.selectKeyList(query);
        return getDataTable(list);
    }

    /**
     * 查询单个密钥详情
     * GET /generate/key/{keyId}
     */
    @GetMapping("/{keyId}")
    public AjaxResult getById(@PathVariable Long keyId) {
        Keymanage keymanage = generateKeyService.selectKeyById(keyId);
        if (keymanage == null) {
            return AjaxResult.error(404, "密钥不存在");
        }
        return AjaxResult.success("查询成功", keymanage);
    }
}
