package com.lgcollege.service;

import com.lgcollege.entity.mysql.HouseImportTask;
import org.springframework.web.multipart.MultipartFile;
import java.nio.file.Path;

public interface HouseImportService {
    HouseImportTask importCsv(MultipartFile file);

    HouseImportTask retry(Long id);

    HouseImportTask findTask(Long id);

    Path findErrorReport(Long id);
}
