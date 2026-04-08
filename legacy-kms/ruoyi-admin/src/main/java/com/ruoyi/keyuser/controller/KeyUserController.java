package com.ruoyi.keyuser.controller;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import javax.servlet.http.HttpServletResponse;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.keyuser.domain.KeyUser;
import com.ruoyi.keyuser.service.IKeyUserService;
import com.ruoyi.common.utils.poi.ExcelUtil;
import com.ruoyi.common.core.page.TableDataInfo;

/**
 * 用户管理Controller
 * 
 * @author ruoyi
 * @date 2024-12-30
 */
@RestController
@RequestMapping("/keyuser/keyuser")
public class KeyUserController extends BaseController
{
    @Autowired
    private IKeyUserService keyUserService;

    /**
     * 查询用户管理列表
     */
    @PreAuthorize("@ss.hasPermi('keyuser:keyuser:list')")
    @GetMapping("/list")
    public TableDataInfo list(KeyUser keyUser)
    {
        startPage();
        List<KeyUser> list = keyUserService.selectKeyUserList(keyUser);

        return getDataTable(list);
    }

    /**
     * 导出用户管理列表
     */
    @PreAuthorize("@ss.hasPermi('keyuser:keyuser:export')")
    @Log(title = "用户管理", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(HttpServletResponse response, KeyUser keyUser)
    {
        List<KeyUser> list = keyUserService.selectKeyUserList(keyUser);
        ExcelUtil<KeyUser> util = new ExcelUtil<KeyUser>(KeyUser.class);
        util.exportExcel(response, list, "用户管理数据");
    }

    /**
     * 获取用户管理详细信息
     */
    @PreAuthorize("@ss.hasPermi('keyuser:keyuser:query')")
    @GetMapping(value = "/{userId}")
    public AjaxResult getInfo(@PathVariable("userId") Long userId)
    {
        return success(keyUserService.selectKeyUserByUserId(userId));
    }

    /**
     * 新增用户管理
     */
    @PreAuthorize("@ss.hasPermi('keyuser:keyuser:add')")
    @Log(title = "用户管理", businessType = BusinessType.INSERT)
    @PostMapping
    public AjaxResult add(@RequestBody KeyUser keyUser)
    {
        return toAjax(keyUserService.insertKeyUser(keyUser));
    }

    /**
     * 修改用户管理
     */
    @PreAuthorize("@ss.hasPermi('keyuser:keyuser:edit')")
    @Log(title = "用户管理", businessType = BusinessType.UPDATE)
    @PutMapping
    public AjaxResult edit(@RequestBody KeyUser keyUser)
    {
        return toAjax(keyUserService.updateKeyUser(keyUser));
    }

    /**
     * 删除用户管理
     */
    @PreAuthorize("@ss.hasPermi('keyuser:keyuser:remove')")
    @Log(title = "用户管理", businessType = BusinessType.DELETE)
	@DeleteMapping("/{userIds}")
    public AjaxResult remove(@PathVariable Long[] userIds)
    {
        return toAjax(keyUserService.deleteKeyUserByUserIds(userIds));
    }
}
