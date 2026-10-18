package com.kms.fabricdid;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;

/** 单次运行的供应方链调用入口；使用与 Bridge 相同的环境和 SDK 配置。 */
public final class SysPidCommand {
    private SysPidCommand() { }
    public static void main(String[] args) {
        if (args.length == 1 && "--help".equals(args[0])) {
            System.out.println("SysPidCommand <onchain|verify|check|preflight|network-check|retry> <sysPid-hex-file>; requires Bridge environment and SDK configuration.");
            return;
        }
        int exit = 1;
        try {
            if (args.length != 2 || !("onchain".equals(args[0]) || "verify".equals(args[0]) || "check".equals(args[0]) || "preflight".equals(args[0]) || "network-check".equals(args[0]) || "retry".equals(args[0])))
                throw new BridgeException(400, "USAGE: SysPidCommand <onchain|verify|check|preflight> <sysPid-hex-file>");
            Path file = Paths.get(args[1]);
            if (!Files.isRegularFile(file) || Files.size(file) > 131072) throw new BridgeException(400, "INVALID_SYS_PID_FILE");
            String sysPid = new String(Files.readAllBytes(file), StandardCharsets.UTF_8).trim();
            BridgeConfig config = new BridgeConfig(System.getenv());
            if ("network-check".equals(args[0])) {
                config.requireRead();
                new VendorDidSdk(config);
                byte[] bytes = com.yunphant.yunid.sdk.helper.NetworkHolder.getInstance().getChannel().getChannelConfigurationBytes();
                System.out.println(Json.encode(Json.map("status", "ORDERER_READ_OK", "configurationBytes", bytes.length, "submitted", false)));
                System.exit(0);
            }
            if ("preflight".equals(args[0])) {
                config.requireRead();
                String did = SysPidService.did(sysPid, config);
                if (config.sysPidRecordsPath == null) throw new BridgeException(503, "SYSPID_RECORDS_NOT_CONFIGURED");
                Path record = config.sysPidRecordsPath.resolve(Json.digest(config.chainId + "\n" + did)).resolve("record.json");
                JsonNode plan = Json.MAPPER.readTree(Files.readAllBytes(record));
                if (!did.equals(Json.text(plan, "did")) || !sysPid.equals(Json.text(plan, "metadata")))
                    throw new BridgeException(409, "SYSPID_RECORD_MISMATCH");
                new VendorDidSdk(config).preflightSystemIdentifier(did, sysPid, Json.text(plan, "publicKey"), Json.text(plan, "nonce"));
                System.out.println(Json.encode(Json.map("status", "SIMULATION_ACCEPTED", "did", did, "submitted", false, "committed", false)));
                System.exit(0);
            }
            if ("check".equals(args[0])) {
                config.requireRead();
                String did = SysPidService.did(sysPid, config);
                DidSdk sdk = new VendorDidSdk(config);
                try {
                    Map<String, Object> document = sdk.read(did);
                    System.out.println(Json.encode(Json.map("status", "FOUND", "did", did, "metadataMatches", sysPid.equals(document.get("metadata")), "submitted", false)));
                } catch (BridgeException e) {
                    if (!"NOT_FOUND_OR_DEACTIVATED".equals(e.errorCode)) throw e;
                    System.out.println(Json.encode(Json.map("status", "NOT_FOUND_OR_DEACTIVATED", "did", did, "submitted", false)));
                }
                System.exit(0);
            }
            SysPidService service = new SysPidService(config, () -> new VendorDidSdk(config));
            JsonNode body = Json.MAPPER.valueToTree(Json.map("sysPid", sysPid));
            Map<String, Object> result = "retry".equals(args[0]) ? service.retryUnrecordedTransaction(body)
                    : "onchain".equals(args[0]) ? service.onchain(body) : service.verify(body);
            System.out.println(Json.encode(result));
            exit = "PENDING_VERIFICATION".equals(result.get("status")) ? 2 : "FAILED".equals(result.get("status")) ? 1 : 0;
        } catch (BridgeException e) {
            diagnostics(e);
            System.err.println(Json.encode(Json.map("errorCode", e.errorCode, "httpStatus", e.httpStatus)));
        } catch (Exception | LinkageError e) {
            diagnostics(e);
            // 供应方异常可能含外置身份信息，不直接打印堆栈或配置。
            System.err.println(Json.encode(Json.map("errorCode", "SYSPID_COMMAND_FAILED")));
        }
        // SDK/gRPC 可能启动非 daemon 线程；单次命令明确结束，不留下后台写入进程。
        System.exit(exit);
    }
    static void diagnostics(Throwable error) {
        String filename = System.getenv("FABRIC_DID_DIAGNOSTICS_FILE");
        if (filename == null || filename.isEmpty()) return;
        try {
            // 诊断仅落盘到显式配置的受限运行目录，HTTP 和终端不回传供应方原始异常。
            Path path = Paths.get(filename).toAbsolutePath().normalize();
            SdkDiagnostics.record(path, error);
        } catch (Exception ignored) { }
    }
}
