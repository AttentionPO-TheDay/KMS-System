package com.ruoyi.generate.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.generate.domain.ComParam;
import com.ruoyi.generate.domain.GenerateUser;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateKeyService;
import com.ruoyi.generate.service.GenerateUserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.HashMap;

@RestController
@RequestMapping("/generate/keymanage")
public class GenerateKeymanageCompatController extends BaseController {

    @Autowired
    private GenerateKeyService generateKeyService;

    @Autowired
    private GenerateUserService generateUserService;

    @GetMapping("/list")
    public TableDataInfo list(Keymanage query,
                              @RequestParam(defaultValue = "1") int pageNum,
                              @RequestParam(defaultValue = "10") int pageSize) {
        startPage();
        List<Keymanage> list = generateKeyService.selectKeyList(query);
        return getDataTable(list);
    }

    @GetMapping("/{keyId}")
    public AjaxResult get(@PathVariable Long keyId) {
        Keymanage keymanage = generateKeyService.selectKeyById(keyId);
        if (keymanage == null) {
            return AjaxResult.error(404, "密钥不存在");
        }
        return AjaxResult.success("查询成功", keymanage);
    }

    @PostMapping("/comparam")
    public AjaxResult getComParam(@RequestBody Keymanage keymanage) {
        ComParam comParam = generateKeyService.getComParam(keymanage.getEncrytType(), keymanage.getEncrytName());
        return AjaxResult.success("操作成功", comParam == null ? new HashMap<>() : comParam.toMap());
    }

    @PostMapping
    public AjaxResult add(@RequestBody Keymanage keymanage) {
        fillUserInfo(keymanage);
        int rows = generateKeyService.insertKey(keymanage);
        if (rows > 0) {
            return AjaxResult.success("操作成功", keymanage);
        }
        return error("生成失败");
    }

    @PutMapping
    public AjaxResult edit(@RequestBody Keymanage keymanage) {
        fillUserInfo(keymanage);
        int rows = generateKeyService.updateKey(keymanage);
        if (rows > 0) {
            return AjaxResult.success("操作成功", keymanage);
        }
        return error("修改失败");
    }

    @DeleteMapping("/{keyId}")
    public AjaxResult remove(@PathVariable Long keyId) {
        int rows = generateKeyService.deleteKey(keyId);
        return rows > 0 ? success() : error("删除失败");
    }

    private void fillUserInfo(Keymanage keymanage) {
        if (keymanage.getUserId() != null && (keymanage.getUserName() == null || keymanage.getUserName().trim().isEmpty())) {
            GenerateUser user = generateUserService.selectByUserId(keymanage.getUserId());
            if (user != null) {
                keymanage.setUserName(user.getUserName());
            }
        }
    }
}
