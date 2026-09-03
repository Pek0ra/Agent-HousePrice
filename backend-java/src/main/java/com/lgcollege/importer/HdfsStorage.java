package com.lgcollege.importer;

import java.nio.file.Path;

public interface HdfsStorage {
    void upload(Path localFile, String hdfsPath, boolean overwrite);
}
