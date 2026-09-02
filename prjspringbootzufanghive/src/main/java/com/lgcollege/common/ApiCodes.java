package com.lgcollege.common;

public final class ApiCodes {
    public static final int SUCCESS = 0;
    public static final int VALIDATION_ERROR = 40001;
    public static final int BUSINESS_ERROR = 40002;
    public static final int MALFORMED_REQUEST = 40003;
    public static final int MISSING_FILE = 40004;
    public static final int RESOURCE_NOT_FOUND = 40400;
    public static final int DUPLICATE_RESOURCE = 40901;
    public static final int DUPLICATE_IMPORT = 40902;
    public static final int TASK_STATE_CONFLICT = 40903;
    public static final int FILE_TOO_LARGE = 41300;
    public static final int IMPORT_FAILED = 42200;
    public static final int INTERNAL_ERROR = 50000;

    private ApiCodes() {
    }
}
