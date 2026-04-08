package com.ruoyi.updatedel.repository;

import com.ruoyi.updatedel.domain.PermissionRequest;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class PermissionRequestRepository {
    private final JdbcTemplate jdbcTemplate;
    private final BeanPropertyRowMapper<PermissionRequest> rowMapper = BeanPropertyRowMapper.newInstance(PermissionRequest.class);

    public PermissionRequestRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Long insert(PermissionRequest request) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "insert into permission_request (user_id, user_name, original_level, request_level, request_reason, status, is_temp, request_time, create_time, update_time) values (?, ?, ?, ?, ?, ?, ?, ?, now(), now())",
                Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1, request.getUserId());
            ps.setString(2, request.getUserName());
            ps.setInt(3, request.getOriginalLevel());
            ps.setInt(4, request.getRequestLevel());
            ps.setString(5, request.getRequestReason());
            ps.setString(6, request.getStatus());
            ps.setInt(7, request.getIsTemp());
            ps.setTimestamp(8, new java.sql.Timestamp(request.getRequestTime().getTime()));
            return ps;
        }, keyHolder);
        return keyHolder.getKey() == null ? null : keyHolder.getKey().longValue();
    }

    public Optional<PermissionRequest> findById(Long requestId) {
        List<PermissionRequest> list = jdbcTemplate.query("select * from permission_request where request_id = ?", rowMapper, requestId);
        return list.stream().findFirst();
    }

    public List<PermissionRequest> findPage(PermissionRequest query, int offset, int limit) {
        StringBuilder sql = new StringBuilder("select * from permission_request where 1=1");
        List<Object> args = new ArrayList<>();
        appendFilters(query, sql, args);
        sql.append(" order by request_id desc limit ? offset ?");
        args.add(limit);
        args.add(offset);
        return jdbcTemplate.query(sql.toString(), rowMapper, args.toArray());
    }

    public List<PermissionRequest> findApprovedBefore(Date beforeTime) {
        return jdbcTemplate.query(
            "select * from permission_request where status = '1' and approve_time is not null and approve_time < ? order by request_id asc",
            rowMapper,
            new java.sql.Timestamp(beforeTime.getTime()));
    }

    public long count(PermissionRequest query) {
        StringBuilder sql = new StringBuilder("select count(1) from permission_request where 1=1");
        List<Object> args = new ArrayList<>();
        appendFilters(query, sql, args);
        Long total = jdbcTemplate.queryForObject(sql.toString(), Long.class, args.toArray());
        return total == null ? 0L : total;
    }

    public int markApproved(Long requestId, String approveBy, String approveNote) {
        return jdbcTemplate.update(
            "update permission_request set status = '1', approve_by = ?, approve_time = now(), approve_note = ?, update_time = now() where request_id = ?",
            approveBy, approveNote, requestId);
    }

    public int markRejected(Long requestId, String approveBy, String approveNote) {
        return jdbcTemplate.update(
            "update permission_request set status = '2', approve_by = ?, approve_time = now(), approve_note = ?, update_time = now() where request_id = ?",
            approveBy, approveNote, requestId);
    }

    public int markRolledBack(Long requestId) {
        return jdbcTemplate.update(
            "update permission_request set status = '3', rollback_time = now(), update_time = now() where request_id = ?",
            requestId);
    }

    private void appendFilters(PermissionRequest query, StringBuilder sql, List<Object> args) {
        if (query == null) {
            return;
        }
        if (query.getUserId() != null) {
            sql.append(" and user_id = ?");
            args.add(query.getUserId());
        }
        if (query.getUserName() != null && !query.getUserName().trim().isEmpty()) {
            sql.append(" and user_name like ?");
            args.add("%" + query.getUserName().trim() + "%");
        }
        if (query.getStatus() != null && !query.getStatus().trim().isEmpty()) {
            sql.append(" and status = ?");
            args.add(query.getStatus());
        }
    }
}
