package com.ruoyi.generate.service;

import com.ruoyi.generate.domain.PermissionRequest;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

@Service
public class PermissionRequestService {
    private static final String SYSTEM_CODE = "generate";
    private static final String FEATURE_CODE = "PUBLIC_KEY_LIST";
    private static final String FEATURE_NAME = "查看公共密钥列表";
    private static final RowMapper<PermissionRequest> ROW_MAPPER = new BeanPropertyRowMapper<>(PermissionRequest.class);

    private final JdbcTemplate jdbcTemplate;

    public PermissionRequestService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<PermissionRequest> list(Long userId, String status) {
        StringBuilder sql = new StringBuilder(
            "select request_id as requestId, user_id as userId, user_name as userName, system_code as systemCode, " +
                "feature_code as featureCode, feature_name as featureName, original_level as originalLevel, " +
                "request_level as requestLevel, request_reason as requestReason, status, is_temp as isTemp, " +
                "request_time as requestTime, approve_by as approveBy, approve_time as approveTime, " +
                "approve_note as approveNote, rollback_time as rollbackTime from permission_request where system_code = ?");
        List<Object> args = new ArrayList<>();
        args.add(SYSTEM_CODE);
        if (userId != null) {
            sql.append(" and user_id = ?");
            args.add(userId);
        }
        if (status != null && !status.isEmpty()) {
            sql.append(" and status = ?");
            args.add(status);
        }
        sql.append(" order by request_time desc");
        return jdbcTemplate.query(sql.toString(), ROW_MAPPER, args.toArray());
    }

    public PermissionRequest get(Long requestId) {
        List<PermissionRequest> list = jdbcTemplate.query(
            "select request_id as requestId, user_id as userId, user_name as userName, system_code as systemCode, " +
                "feature_code as featureCode, feature_name as featureName, original_level as originalLevel, " +
                "request_level as requestLevel, request_reason as requestReason, status, is_temp as isTemp, " +
                "request_time as requestTime, approve_by as approveBy, approve_time as approveTime, " +
                "approve_note as approveNote, rollback_time as rollbackTime from permission_request where request_id = ? and system_code = ?",
            ROW_MAPPER,
            requestId,
            SYSTEM_CODE
        );
        return list.isEmpty() ? null : list.get(0);
    }

    @Transactional
    public void submit(PermissionRequest request) {
        validateSubmit(request);
        Date now = new Date();
        jdbcTemplate.update(
            "insert into permission_request (user_id, user_name, system_code, feature_code, feature_name, original_level, request_level, request_reason, status, is_temp, request_time, create_time, update_time) values (?, ?, ?, ?, ?, ?, ?, ?, '0', ?, ?, ?, ?)",
            request.getUserId(),
            request.getUserName(),
            SYSTEM_CODE,
            FEATURE_CODE,
            FEATURE_NAME,
            request.getOriginalLevel(),
            request.getRequestLevel(),
            request.getRequestReason(),
            request.getIsTemp() == null ? 1 : request.getIsTemp(),
            ts(now),
            ts(now),
            ts(now)
        );
    }

    @Transactional
    public void approve(Long requestId, String approveBy, String approveNote) {
        PermissionRequest request = requirePending(requestId);
        Date now = new Date();
        jdbcTemplate.update(
            "update permission_request set status = '1', approve_by = ?, approve_time = ?, approve_note = ?, update_time = ? where request_id = ?",
            blankToDefault(approveBy, "generate-admin"),
            ts(now),
            approveNote,
            ts(now),
            requestId
        );
        jdbcTemplate.update("update sys_user set role_level = ? where user_id = ?", request.getRequestLevel(), request.getUserId());
    }

    @Transactional
    public void reject(Long requestId, String approveBy, String approveNote) {
        requirePending(requestId);
        Date now = new Date();
        jdbcTemplate.update(
            "update permission_request set status = '2', approve_by = ?, approve_time = ?, approve_note = ?, update_time = ? where request_id = ?",
            blankToDefault(approveBy, "generate-admin"),
            ts(now),
            approveNote,
            ts(now),
            requestId
        );
    }

    @Transactional
    public void rollback(Long requestId) {
        PermissionRequest request = get(requestId);
        if (request == null) {
            throw new IllegalArgumentException("权限申请不存在");
        }
        if (!"1".equals(request.getStatus())) {
            throw new IllegalArgumentException("当前申请未处于已通过状态，无法回退");
        }
        Date now = new Date();
        jdbcTemplate.update("update sys_user set role_level = ? where user_id = ?", request.getOriginalLevel(), request.getUserId());
        jdbcTemplate.update(
            "update permission_request set status = '3', rollback_time = ?, update_time = ? where request_id = ?",
            ts(now),
            ts(now),
            requestId
        );
    }

    @Transactional
    public int rollbackExpiredApprovedRequests() {
        List<PermissionRequest> requests = jdbcTemplate.query(
            "select request_id as requestId, user_id as userId, user_name as userName, system_code as systemCode, feature_code as featureCode, feature_name as featureName, original_level as originalLevel, request_level as requestLevel, request_reason as requestReason, status, is_temp as isTemp, request_time as requestTime, approve_by as approveBy, approve_time as approveTime, approve_note as approveNote, rollback_time as rollbackTime from permission_request where system_code = ? and status = '1' and approve_time < DATE_SUB(NOW(), INTERVAL 30 MINUTE)",
            ROW_MAPPER,
            SYSTEM_CODE
        );
        for (PermissionRequest request : requests) {
            rollback(request.getRequestId());
        }
        return requests.size();
    }

    private void validateSubmit(PermissionRequest request) {
        if (request.getUserId() == null) {
            throw new IllegalArgumentException("缺少用户ID");
        }
        if (request.getOriginalLevel() == null) {
            throw new IllegalArgumentException("缺少原始权限等级");
        }
        if (request.getRequestLevel() == null || request.getRequestLevel() != 1) {
            throw new IllegalArgumentException("生成域仅允许申请查看公共密钥列表权限");
        }
        if (request.getRequestReason() == null || request.getRequestReason().trim().length() < 4) {
            throw new IllegalArgumentException("申请理由过短");
        }
    }

    private PermissionRequest requirePending(Long requestId) {
        PermissionRequest request = get(requestId);
        if (request == null) {
            throw new IllegalArgumentException("权限申请不存在");
        }
        if (!"0".equals(request.getStatus())) {
            throw new IllegalArgumentException("该申请已处理，无法重复审批");
        }
        return request;
    }

    private Timestamp ts(Date date) {
        return new Timestamp(date.getTime());
    }

    private String blankToDefault(String value, String fallback) {
        return value == null || value.trim().isEmpty() ? fallback : value.trim();
    }
}
