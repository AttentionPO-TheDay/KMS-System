package com.ruoyi.common.core.page;

import com.ruoyi.common.utils.StringUtils;

/**
 * 分页数据
 * 
 * @author ruoyi
 */
public class PageDomain
{
    /**
     * 分页参数的兜底与上限。
     *
     * 为什么需要（2026-09-27 补齐）：本类原先直接 `this.pageSize = pageSize;`，
     * 完全不校验。客户端传 `pageSize=999999999` 就能让服务端一次性取出整表，
     * 造成内存与数据库压力。同仓库的 updatedel 后端早已加了钳制，本模块漏了 ——
     * 这是两个后端各自演进产生的漂移。
     *
     * 上限取 500，不是 updatedel 原先的 100：
     * 仓库里存在两处**合法**的大页请求，取 100 会把它们静默截断：
     *   - kms-updatedel/front/src/views/chain/index.vue  请求 pageSize=500
     *   - kms-user/front/.../distribute/DistributeView.vue 请求 pageSize=200
     *     （用它填密钥下拉框，截断会让用户少看到可选密钥）
     * 500 既能覆盖这两处，又足以挡住异常大的值。
     */
    private static final int DEFAULT_PAGE_NUM = 1;
    private static final int DEFAULT_PAGE_SIZE = 10;
    private static final int MAX_PAGE_SIZE = 500;

    /** 当前记录起始索引 */
    private Integer pageNum;

    /** 每页显示记录数 */
    private Integer pageSize;

    /** 排序列 */
    private String orderByColumn;

    /** 排序的方向desc或者asc */
    private String isAsc = "asc";

    /** 分页参数合理化 */
    private Boolean reasonable = true;

    public String getOrderBy()
    {
        if (StringUtils.isEmpty(orderByColumn))
        {
            return "";
        }
        return StringUtils.toUnderScoreCase(orderByColumn) + " " + isAsc;
    }

    public Integer getPageNum()
    {
        return pageNum;
    }

    public void setPageNum(Integer pageNum)
    {
        this.pageNum = pageNum == null || pageNum < DEFAULT_PAGE_NUM ? DEFAULT_PAGE_NUM : pageNum;
    }

    public Integer getPageSize()
    {
        return pageSize;
    }

    public void setPageSize(Integer pageSize)
    {
        if (pageSize == null || pageSize < 1)
        {
            this.pageSize = DEFAULT_PAGE_SIZE;
            return;
        }
        this.pageSize = Math.min(pageSize, MAX_PAGE_SIZE);
    }

    public String getOrderByColumn()
    {
        return orderByColumn;
    }

    public void setOrderByColumn(String orderByColumn)
    {
        this.orderByColumn = orderByColumn;
    }

    public String getIsAsc()
    {
        return isAsc;
    }

    public void setIsAsc(String isAsc)
    {
        if (StringUtils.isNotEmpty(isAsc))
        {
            // 兼容前端排序类型
            if ("ascending".equals(isAsc))
            {
                isAsc = "asc";
            }
            else if ("descending".equals(isAsc))
            {
                isAsc = "desc";
            }
            this.isAsc = isAsc;
        }
    }

    public Boolean getReasonable()
    {
        if (StringUtils.isNull(reasonable))
        {
            return Boolean.TRUE;
        }
        return reasonable;
    }

    public void setReasonable(Boolean reasonable)
    {
        this.reasonable = reasonable;
    }
}
