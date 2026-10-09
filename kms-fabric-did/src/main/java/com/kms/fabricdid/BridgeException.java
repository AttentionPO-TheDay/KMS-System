package com.kms.fabricdid;

final class BridgeException extends RuntimeException {
    final int httpStatus;
    final String errorCode;
    BridgeException(int httpStatus, String errorCode) { this(httpStatus, errorCode, errorCode); }
    BridgeException(int httpStatus, String errorCode, String safeMessage) {
        super(safeMessage); this.httpStatus = httpStatus; this.errorCode = errorCode;
    }
}
