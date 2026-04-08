package com.ruoyi.updatedel.repository;

import com.ruoyi.updatedel.domain.Keymanage;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class KeymanageRepository {
    private final JdbcTemplate jdbcTemplate;
    private final BeanPropertyRowMapper<Keymanage> rowMapper = BeanPropertyRowMapper.newInstance(Keymanage.class);

    public KeymanageRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Optional<Keymanage> findById(Long keyId) {
        List<Keymanage> list = jdbcTemplate.query("select * from keymanage where key_id = ?", rowMapper, keyId);
        return list.stream().findFirst();
    }

    public List<Keymanage> findPage(Keymanage query, int offset, int limit) {
        StringBuilder sql = new StringBuilder("select * from keymanage where 1=1");
        List<Object> args = new ArrayList<>();
        appendFilters(query, sql, args);
        sql.append(" order by key_id desc limit ? offset ?");
        args.add(limit);
        args.add(offset);
        return jdbcTemplate.query(sql.toString(), rowMapper, args.toArray());
    }

    public long count(Keymanage query) {
        StringBuilder sql = new StringBuilder("select count(1) from keymanage where 1=1");
        List<Object> args = new ArrayList<>();
        appendFilters(query, sql, args);
        Long total = jdbcTemplate.queryForObject(sql.toString(), Long.class, args.toArray());
        return total == null ? 0L : total;
    }

    public int updateRotated(Keymanage key) {
        return jdbcTemplate.update(
            "update keymanage set user_name=?, ua=?, encryt_type=?, encryt_name=?, key_name=?, key_use=?, key_value=?, upd_time=?, auto_update=?, status=?, version=?, chain_status=?, key_domain=? where key_id=?",
            key.getUserName(), key.getUa(), key.getEncrytType(), key.getEncrytName(), key.getKeyName(), key.getKeyUse(),
            key.getKeyValue(), key.getUpdTime(), key.getAutoUpdate(), key.getStatus(), key.getVersion(), key.getChainStatus(),
            key.getKeyDomain(), key.getKeyId());
    }

    public int updateAutoUpdate(Long keyId, String autoUpdate) {
        return jdbcTemplate.update("update keymanage set auto_update = ?, upd_time = now() where key_id = ?", autoUpdate, keyId);
    }

    public int revoke(Long keyId, String status) {
        return jdbcTemplate.update("update keymanage set status = ?, upd_time = now(), chain_status = '0' where key_id = ?", status, keyId);
    }

    public int updateChainStatus(Long keyId, String chainStatus, String chainHash, Long blockHeight) {
        return jdbcTemplate.update(
            "update keymanage set chain_status = coalesce(?, chain_status), chain_hash = coalesce(?, chain_hash), block_height = coalesce(?, block_height), upd_time = now() where key_id = ?",
            chainStatus, chainHash, blockHeight, keyId);
    }

    private void appendFilters(Keymanage query, StringBuilder sql, List<Object> args) {
        if (query == null) {
            return;
        }
        if (query.getUserId() != null) {
            sql.append(" and user_id = ?");
            args.add(query.getUserId());
        }
        if (hasText(query.getUserName())) {
            sql.append(" and user_name like ?");
            args.add(like(query.getUserName()));
        }
        if (hasText(query.getEncrytType())) {
            sql.append(" and encryt_type = ?");
            args.add(query.getEncrytType());
        }
        if (hasText(query.getEncrytName())) {
            sql.append(" and encryt_name like ?");
            args.add(like(query.getEncrytName()));
        }
        if (hasText(query.getKeyName())) {
            sql.append(" and key_name like ?");
            args.add(like(query.getKeyName()));
        }
        if (hasText(query.getKeyUse())) {
            sql.append(" and key_use like ?");
            args.add(like(query.getKeyUse()));
        }
        if (hasText(query.getAutoUpdate())) {
            sql.append(" and auto_update = ?");
            args.add(query.getAutoUpdate());
        }
        if (hasText(query.getStatus())) {
            sql.append(" and status = ?");
            args.add(query.getStatus());
        }
    }

    private boolean hasText(String value) {
        return value != null && !value.trim().isEmpty();
    }

    private String like(String value) {
        return "%" + value.trim() + "%";
    }
}
