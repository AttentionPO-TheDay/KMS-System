# Java RuoYi Framework Repair Guide

## Document Purpose

This document is the unified repair guide for the three Java systems:

1. `kms-generate`
2. `kms-updatedel`
3. `kms-distribute`

The goal is not to keep extending the current lightweight Spring Boot jars.
The goal is to repair each system back onto the original `legacy-kms` Java RuoYi framework model, then embed the already-split core business code into that restored framework.

This file contains three complete execution documents in one place, so three different agents can work in parallel.

## Global Conclusion

The original project `legacy-kms` is a complete RuoYi multi-module backend with mature configuration, security, common response handling, paging, system management, logging, Redis, Kafka, Druid, MyBatis, Swagger, XSS protection, token handling, and Quartz support.

The new Java backends currently preserve much of the split business logic, but they do not preserve the full RuoYi framework shell.

The repair direction for all three systems is therefore fixed:

1. Recreate the original Java RuoYi project skeleton from `legacy-kms`
2. Keep the RuoYi framework capabilities intact
3. Migrate the split business code into the repaired skeleton
4. Avoid rebuilding infrastructure from scratch in each project
5. Make each system an independently runnable RuoYi-style backend

## Global Non-Negotiable Rules

1. Do not continue evolving the current single-module lightweight structure as the final form.
2. Do not replace RuoYi common infrastructure with ad hoc utility classes unless there is a hard blocker.
3. Do not keep `anyRequest().permitAll()` as the long-term security configuration.
4. Do not keep custom response wrappers when the original RuoYi `AjaxResult`, `TableDataInfo`, `BaseController`, and related classes can be reused.
5. Do not remove the split business boundaries that already exist.
6. Restore the framework first, then fit the split business code into it.
7. Business package names may remain system-specific, but framework behavior should follow the original RuoYi model.

## Source Baseline

The repair baseline is the original Java monolith:

1. `legacy-kms/pom.xml`
2. `legacy-kms/ruoyi-admin`
3. `legacy-kms/ruoyi-framework`
4. `legacy-kms/ruoyi-system`
5. `legacy-kms/ruoyi-common`
6. `legacy-kms/ruoyi-quartz`
7. `legacy-kms/ruoyi-generator`

Key configuration baseline:

1. `legacy-kms/ruoyi-admin/src/main/resources/application.yml`
2. `legacy-kms/ruoyi-admin/src/main/resources/application-druid.yml`

## Shared Diagnosis Across The Three Systems

Current common problems in the new Java services:

1. They are mostly single-module Spring Boot projects, not RuoYi multi-module projects.
2. Their `pom.xml` files do not inherit the original RuoYi module structure.
3. Their `application.yml` files are incomplete compared with the monolith.
4. Security has been simplified too far and is not equivalent to the original RuoYi security chain.
5. Common controller infrastructure is missing or partially reimplemented.
6. System management capabilities from `ruoyi-system` are not fully preserved.
7. Some classes are copied in isolation, but the framework context that made them work is missing.

The correct repair principle is:

1. Copy the complete RuoYi framework shell into each target Java system
2. Rewire configuration and ports for that system
3. Embed the split domain code into the repaired shell
4. Remove duplicate lightweight replacements only after the repaired framework path is working

## Shared Target Structure

Each Java backend should converge toward a structure logically equivalent to:

```text
<system>/java-backend/
├── pom.xml                       # parent pom
├── ruoyi-admin/
├── ruoyi-framework/
├── ruoyi-system/
├── ruoyi-common/
├── ruoyi-quartz/
└── ruoyi-generator/             # optional but recommended to keep parity
```

Framework copy policy:

1. `ruoyi-common` must be preserved
2. `ruoyi-framework` must be preserved
3. `ruoyi-system` should be preserved unless there is an explicit decision to centralize admin capabilities elsewhere
4. `ruoyi-quartz` should be preserved, especially required by `kms-updatedel`
5. `ruoyi-generator` is optional at runtime, but recommended for complete parity and easier maintenance

## Shared Repair Checklist

Every agent should use the following top-level checklist:

1. Replace the current Java backend root structure with a RuoYi multi-module skeleton copied from `legacy-kms`
2. Adjust parent `pom.xml`, artifact names, module names, and final packaging names
3. Restore RuoYi common configuration files from the monolith
4. Restore RuoYi security, login, token, exception, filter, and annotation infrastructure
5. Restore common controller and response infrastructure
6. Migrate split business code into the repaired modules
7. Reconnect MyBatis mapper scanning and XML resources
8. Reconnect Kafka, Redis, Druid, token, upload path, and logging configuration
9. Verify startup and endpoint behavior
10. Remove temporary duplicate helper implementations only after the repaired path is validated

---

## Document A: `kms-generate`

### A.1 Objective

Repair `kms-generate/java-backend` so that it is no longer just a lightweight Spring Boot jar, but a full RuoYi-style Java backend containing the generate-domain business code.

### A.2 Current Situation

Current business code already exists and is usable:

1. `com.ruoyi.generate.controller.*`
2. `com.ruoyi.generate.service.*`
3. `com.ruoyi.generate.consumer.*`
4. `com.ruoyi.generate.mapper.*`
5. `com.ruoyi.generate.domain.*`
6. `com.ruoyi.generate.contracts.*`
7. `com.ruoyi.generate.task.*`

But the framework shell is incomplete:

1. Current `pom.xml` is single-module
2. Current `SecurityConfig` is permissive and not equivalent to RuoYi
3. Current config file is simplified
4. Common RuoYi modules are not structurally restored
5. Controller layer still manually builds response maps in places

### A.3 Mandatory Repair Target

`kms-generate` must be rebuilt on top of the original RuoYi framework pattern.

Required target state:

1. Multi-module Maven project
2. RuoYi common classes available directly from framework modules
3. Standard RuoYi security flow restored
4. Generate business code embedded as system-specific business module code
5. Existing generate endpoints preserved
6. Kafka consumer and chain logic preserved

### A.4 Framework Restoration Scope

Copy and adapt from `legacy-kms`:

1. root `pom.xml`
2. `ruoyi-common`
3. `ruoyi-framework`
4. `ruoyi-system`
5. `ruoyi-quartz`
6. `ruoyi-generator`
7. `ruoyi-admin`

Then rename only what is necessary for this system:

1. artifact naming
2. startup class name if desired
3. package scanning scope
4. application name
5. service port

Do not simplify away the framework modules after copying them.

### A.5 Business Embedding Plan

Embed current split generate logic into the repaired shell.

Recommended placement:

1. Keep generate-domain code under `ruoyi-admin/src/main/java/com/ruoyi/generate/*`
2. Keep mapper XML under `ruoyi-admin/src/main/resources/mapper/generate/*`
3. Keep startup and route exposure in `ruoyi-admin`
4. Reuse `ruoyi-common`, `ruoyi-framework`, `ruoyi-system` for infrastructure

Current code that should be retained and embedded:

1. `GenerateController`
2. `GenerateUserController`
3. `PermissionRequestController`
4. `GenerateKafkaConsumer`
5. `ChainTaskConsumer`
6. `GenerateKeyServiceImpl`
7. `GenerateUserServiceImpl`
8. `GenerateChainServiceImpl`
9. domain, mapper, audit, generator, contract classes

### A.6 Specific Repair Tasks

1. Rebuild `kms-generate/java-backend/pom.xml` as a parent RuoYi-style multi-module pom
2. Create or restore `ruoyi-admin`, `ruoyi-framework`, `ruoyi-system`, `ruoyi-common`, `ruoyi-quartz`, `ruoyi-generator`
3. Port the existing generate startup class into `ruoyi-admin`
4. Replace permissive `SecurityConfig` with RuoYi security configuration based on the monolith
5. Restore token, login, logout, JWT filter, anonymous URL policy, method security, exception handling
6. Replace manual list/map response assembly with `BaseController`, `AjaxResult`, and `TableDataInfo` where appropriate
7. Restore `application.yml` and `application-druid.yml` using monolith structure, then inject generate-specific values
8. Keep generate-specific Kafka topic config such as `key_generate_log`
9. Keep generate-specific FISCO and chain task behavior
10. Reconnect MyBatis aliases and mapper locations so generate mappers load through RuoYi conventions

### A.7 Configuration Requirements

The repaired `kms-generate` config must inherit the original RuoYi config shape and then apply generate-specific overrides.

Must include at least:

1. `ruoyi.*`
2. `server.*`
3. `logging.*`
4. `user.password.*`
5. `spring.messages.*`
6. `spring.profiles.active=druid`
7. `spring.servlet.multipart.*`
8. `spring.redis.*`
9. `spring.kafka.*`
10. `token.*`
11. `mybatis.*`
12. `pagehelper.*`
13. `swagger.*`
14. `xss.*`
15. `fisco.*`

Generate-specific config must preserve:

1. server port `9081`
2. topic `key_generate_log`
3. chain task topic usage
4. generate domain mapper scanning

### A.8 Expected End State

At completion, `kms-generate` should behave as:

1. a complete RuoYi backend shell
2. with generate-specific domain code embedded into it
3. with original framework config restored
4. with security restored
5. with current business interface behavior preserved

### A.9 Completion Criteria

The agent working on `kms-generate` is done only when:

1. the project is multi-module
2. it starts with restored RuoYi configuration
3. generate endpoints still work
4. Kafka consumer wiring still works
5. controller responses follow RuoYi conventions
6. security is no longer globally permissive

---

## Document B: `kms-updatedel`

### B.1 Objective

Repair `kms-updatedel/java-backend` into a full RuoYi-style backend and embed the lifecycle, update, revoke, permission, and scheduled rollback logic into that restored shell.

### B.2 Current Situation

Current business logic is already split and relatively complete:

1. `LifecycleKeyController`
2. `PermissionRequestController`
3. `LifecycleService`
4. `KeyRotateService`
5. `KeyRevokeService`
6. `UpdateKafkaConsumer`
7. `RevokeKafkaConsumer`
8. `UpdatedelChainConsumer`
9. `PermissionRevokeTask`
10. `PermissionRollbackTask`

But the framework restoration is incomplete:

1. single-module `pom.xml`
2. permissive `SecurityConfig`
3. partial custom common classes instead of full RuoYi reuse
4. simplified configuration file
5. partial and local infrastructure reimplementation

### B.3 Mandatory Repair Target

`kms-updatedel` must become a standard RuoYi-pattern backend with lifecycle business code embedded inside.

Required target state:

1. multi-module Maven project
2. full RuoYi common/framework/system support
3. restored security and token chain
4. restored Quartz support using RuoYi-compatible layout
5. split lifecycle business logic preserved

### B.4 Framework Restoration Scope

Copy and adapt from `legacy-kms`:

1. root `pom.xml`
2. `ruoyi-common`
3. `ruoyi-framework`
4. `ruoyi-system`
5. `ruoyi-quartz`
6. `ruoyi-generator`
7. `ruoyi-admin`

For `kms-updatedel`, keeping `ruoyi-quartz` is mandatory because the system already has time-based rollback/revoke behavior.

### B.5 Business Embedding Plan

Embed lifecycle-domain code into the repaired shell.

Recommended placement:

1. `ruoyi-admin/src/main/java/com/ruoyi/updatedel/*`
2. `ruoyi-admin/src/main/resources/mapper/updatedel/*`
3. use `ruoyi-system` for user, role, menu, logging, config and other admin infrastructure

Current split code that should be retained and embedded:

1. `LifecycleKeyController`
2. `PermissionRequestController`
3. `LifecycleService`
4. `KeyRotateService`
5. `KeyRevokeService`
6. `UpdateKafkaConsumer`
7. `RevokeKafkaConsumer`
8. `UpdatedelChainConsumer`
9. `PermissionRevokeTask`
10. `PermissionRollbackTask`
11. repositories, mappers, domains, generator classes, contract classes

### B.6 Specific Repair Tasks

1. Rebuild the Java backend root into a RuoYi multi-module structure
2. Restore the original framework modules from `legacy-kms`
3. Rewire lifecycle startup into `ruoyi-admin`
4. Remove the current permissive security setup and restore RuoYi security config
5. Replace local substitutes for `AjaxResult` and `TableDataInfo` with the standard RuoYi versions where feasible
6. Reuse `BaseController` and framework paging behavior instead of project-local manual patterns
7. Restore configuration structure from the monolith, then apply lifecycle-specific values
8. Preserve topics `key_update_log`, `key_revoke_log`, and `key_chain_task`
9. Reconnect lifecycle service, permission service, and task scheduling into the RuoYi shell
10. Ensure scheduled permission rollback works via restored framework layout

### B.7 Configuration Requirements

The repaired `kms-updatedel` config must restore the original RuoYi config shape.

Must include at least:

1. `ruoyi.*`
2. `server.*`
3. `logging.*`
4. `user.password.*`
5. `spring.messages.*`
6. `spring.profiles.active=druid`
7. `spring.servlet.multipart.*`
8. `spring.redis.*`
9. `spring.kafka.*`
10. `token.*`
11. `mybatis.*`
12. `pagehelper.*`
13. `swagger.*`
14. `xss.*`
15. Quartz-related config as needed
16. `fisco.*`

Lifecycle-specific config must preserve:

1. server port `9082`
2. topic `key_update_log`
3. topic `key_revoke_log`
4. chain task topic usage
5. lifecycle metrics and permission-related wiring

### B.8 Expected End State

At completion, `kms-updatedel` should behave as:

1. a complete RuoYi backend shell
2. with lifecycle/update/revoke/permission business code embedded into it
3. with restored framework security and token logic
4. with restored Quartz-compatible scheduling support
5. with current split business boundaries preserved

### B.9 Completion Criteria

The agent working on `kms-updatedel` is done only when:

1. the project is multi-module
2. it starts with restored RuoYi configuration
3. lifecycle endpoints still work
4. update and revoke Kafka consumers still work
5. permission and rollback logic still work
6. controller responses follow RuoYi conventions
7. security is no longer globally permissive

---

## Document C: `kms-distribute`

### C.1 Objective

Repair `kms-distribute/java-backend` into a full RuoYi-style backend and embed the distribute-record domain code into that shell.

### C.2 Current Situation

Current business scope is lighter than the other two systems, but the same structural problem exists.

Current code already exists for:

1. `KeyDistributeController`
2. `IKeyDistributeService`
3. `KeyDistributeServiceImpl`
4. `KeyDistributeMapper`
5. `KeyDistributeRecord`
6. `DistributeKafkaConsumer`
7. `KeyDistributeFeignClient`

Current framework limitations:

1. single-module `pom.xml`
2. simplified config
3. not restored to original RuoYi structure
4. partial common class copying instead of full framework reuse
5. current technology shape diverges from the other two Java systems

### C.3 Mandatory Repair Target

`kms-distribute` must also be repaired onto the same RuoYi framework model as the other two systems.

This is mandatory even though the business scope is smaller, because keeping one lightweight exception will create long-term maintenance inconsistency.

Required target state:

1. multi-module Maven project
2. full RuoYi infrastructure available
3. distribute business code embedded into the repaired shell
4. consistent framework conventions shared with the other two systems

### C.4 Framework Restoration Scope

Copy and adapt from `legacy-kms`:

1. root `pom.xml`
2. `ruoyi-common`
3. `ruoyi-framework`
4. `ruoyi-system`
5. `ruoyi-quartz`
6. `ruoyi-generator`
7. `ruoyi-admin`

Even if `kms-distribute` does not currently need all modules functionally, preserving the same shell is still the repair target.

### C.5 Business Embedding Plan

Embed distribute-domain code into the repaired shell.

Recommended placement:

1. `ruoyi-admin/src/main/java/com/ruoyi/distribute/*`
2. `ruoyi-admin/src/main/resources/mapper/distribute/*`

Current code that should be retained and embedded:

1. `KeyDistributeController`
2. `IKeyDistributeService`
3. `KeyDistributeServiceImpl`
4. `KeyDistributeMapper`
5. `KeyDistributeRecord`
6. `DistributeKafkaConsumer`
7. `KeyDistributeFeignClient`

During repair, package hygiene should also be corrected if copied classes currently sit under unrelated package paths.

### C.6 Specific Repair Tasks

1. Rebuild the Java backend root into a RuoYi multi-module project
2. Restore common framework modules from `legacy-kms`
3. Rewire distribute startup into `ruoyi-admin`
4. Replace project-local simplified response handling with standard RuoYi response patterns where applicable
5. Restore full config shape from the monolith, then inject distribute-specific values
6. Reconnect MyBatis mapper scanning using RuoYi conventions
7. Keep distribute CRUD endpoints intact
8. Preserve any Kafka or Feign integration after the shell is repaired
9. Normalize package names if some imported domain classes still point to unrelated packages

### C.7 Configuration Requirements

The repaired `kms-distribute` config must restore the original RuoYi config shape.

Must include at least:

1. `ruoyi.*`
2. `server.*`
3. `logging.*`
4. `user.password.*`
5. `spring.messages.*`
6. `spring.profiles.active=druid`
7. `spring.servlet.multipart.*`
8. `spring.redis.*`
9. `spring.kafka.*`
10. `token.*`
11. `mybatis.*`
12. `pagehelper.*`
13. `swagger.*`
14. `xss.*`

Distribute-specific config must preserve:

1. server port `8083`
2. distribute mapper paths
3. Feign-related settings if still needed
4. distribute service URLs or integration endpoints

### C.8 Expected End State

At completion, `kms-distribute` should behave as:

1. a complete RuoYi backend shell
2. with distribute-record business code embedded into it
3. with aligned conventions shared with the other two repaired systems
4. with current business endpoints preserved

### C.9 Completion Criteria

The agent working on `kms-distribute` is done only when:

1. the project is multi-module
2. it starts with restored RuoYi configuration
3. distribute CRUD endpoints still work
4. response and paging conventions align with RuoYi
5. framework structure matches the other two systems

---

## Cross-System Execution Notes

All three agents should follow these rules while executing:

1. Use `legacy-kms` as the exact framework baseline, not memory or approximation.
2. Prefer copying and adapting original RuoYi framework code over rewriting it.
3. Keep system-specific business code under separate domain packages.
4. Do not break the already-split business boundaries.
5. Do not delete business code first and rebuild later. Restore shell first, then re-home code carefully.
6. Validate package scanning, mapper XML paths, component scanning, Kafka config, and startup class placement.
7. Treat current simplified code as transitional scaffolding, not the final architecture.

## Recommended Parallel Assignment

1. Agent 1 executes Document A for `kms-generate`
2. Agent 2 executes Document B for `kms-updatedel`
3. Agent 3 executes Document C for `kms-distribute`

## Final Acceptance Across All Three Systems

The overall repair is complete only when all three systems satisfy the following:

1. all three Java backends are RuoYi-style multi-module projects
2. all three restore the original framework-level config completeness
3. all three restore standard security behavior instead of global permit-all
4. all three preserve their split business boundaries
5. all three remain independently deployable
6. all three share a coherent Java backend architecture again
