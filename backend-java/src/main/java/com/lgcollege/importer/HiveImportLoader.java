package com.lgcollege.importer;

import java.time.LocalDate;

public interface HiveImportLoader {
    void load(Long taskId, LocalDate importDate, String hdfsDirectory);
}
