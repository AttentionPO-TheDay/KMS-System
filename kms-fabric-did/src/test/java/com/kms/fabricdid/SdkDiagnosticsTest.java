package com.kms.fabricdid;

import io.grpc.Status;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.ExecutionException;
import org.junit.Test;
import static org.junit.Assert.*;

public class SdkDiagnosticsTest {
    @Test public void actualLoggingBackendAndCommonsBridgeArePresent() {
        assertEquals("org.slf4j.impl.SimpleLoggerFactory", org.slf4j.LoggerFactory.getILoggerFactory().getClass().getName());
        assertTrue(org.apache.commons.logging.LogFactory.getLog("diagnostics-test").getClass().getName().contains("SLF4J"));
        assertFalse(org.slf4j.LoggerFactory.getLogger("diagnostics-test").isDebugEnabled());
    }

    @Test public void includesNestedGrpcCauseSuppressedAndStack() {
        Throwable grpc = Status.PERMISSION_DENIED.withDescription("channel write policy rejected").asRuntimeException();
        ExecutionException error = new ExecutionException("Failed to send transaction to the orderer", grpc);
        error.addSuppressed(new javax.net.ssl.SSLHandshakeException("TLS handshake failed"));
        List<Object> report = SdkDiagnostics.describe(error);
        assertEquals(3, report.size());
        String json = Json.encode(report);
        assertTrue(json.contains("PERMISSION_DENIED"));
        assertTrue(json.contains("suppressed"));
        assertTrue(json.contains("SdkDiagnosticsTest.java"));
    }

    @Test public void stripsPrivateKeyTokensAndAuthorization() {
        String safe = SdkDiagnostics.safeText("-----BEGIN PRIVATE KEY-----\nPRIVATE_MATERIAL\n-----END PRIVATE KEY-----\n"
                + "privateKey=RAW_KEY password=RAW_PASSWORD token=RAW_TOKEN Authorization: Bearer RAW_AUTH");
        for (String value : new String[] {"PRIVATE_MATERIAL", "RAW_KEY", "RAW_PASSWORD", "RAW_TOKEN", "RAW_AUTH"})
            assertFalse(safe, safe.contains(value));
        assertFalse(SdkDiagnostics.safeText("-----BEGIN PRIVATE KEY-----\nPARTIAL_KEY").contains("PARTIAL_KEY"));
    }

    @Test public void boundsLongMessagesAndCyclicCauses() {
        RuntimeException first = new RuntimeException(String.join("", java.util.Collections.nCopies(4000, "a")));
        RuntimeException second = new RuntimeException("second", first);
        first.initCause(second);
        assertEquals(2, SdkDiagnostics.describe(first).size());
        assertTrue(SdkDiagnostics.safeText(first.getMessage()).length() < 2100);
        Throwable chain = new RuntimeException("last");
        for (int i = 0; i < 30; i++) chain = new RuntimeException("outer", chain);
        assertEquals(16, SdkDiagnostics.describe(chain).size());
    }

    @Test public void recordsMultipleFailuresWithoutReplacingEarlierEvidence() throws Exception {
        Path directory = Files.createTempDirectory("sdk-diagnostics-test-");
        Path file = directory.resolve("exceptions.json");
        try {
            SdkDiagnostics.record(file, new IllegalStateException("first submission failure"));
            SdkDiagnostics.record(file, new IllegalArgumentException("later verification failure"));
            com.fasterxml.jackson.databind.JsonNode report = Json.MAPPER.readTree(Files.readAllBytes(file));
            assertEquals(2, report.get("events").size());
            assertTrue(report.toString().contains("first submission failure"));
            assertTrue(report.toString().contains("later verification failure"));
        } finally { Files.deleteIfExists(file); Files.deleteIfExists(directory); }
    }
}
