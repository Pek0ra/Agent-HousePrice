package com.lgcollege.importer;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import java.io.IOException;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
@ConditionalOnProperty(
        prefix = "app.big-data", name = "enabled",
        havingValue = "true", matchIfMissing = false)
public class WebHdfsStorage implements HdfsStorage {
    private static final Logger log = LoggerFactory.getLogger(WebHdfsStorage.class);
    private final String webUrl;
    private final String hdfsUser;
    private final Duration connectTimeout;
    private final Duration requestTimeout;

    public WebHdfsStorage(
            @Value("${app.hdfs.web-url}") String webUrl,
            @Value("${app.hdfs.user:}") String hdfsUser,
            @Value("${app.hdfs.connect-timeout-seconds:10}") long connectTimeoutSeconds,
            @Value("${app.hdfs.request-timeout-seconds:300}") long requestTimeoutSeconds) {
        this.webUrl = stripTrailingSlash(webUrl);
        this.hdfsUser = hdfsUser;
        this.connectTimeout = Duration.ofSeconds(connectTimeoutSeconds);
        this.requestTimeout = Duration.ofSeconds(requestTimeoutSeconds);
    }

    @Override
    public void upload(Path localFile, String hdfsPath, boolean overwrite) {
        long startedAt = System.nanoTime();
        URI createUri = buildCreateUri(hdfsPath, overwrite);
        HttpURLConnection createConnection = null;
        HttpURLConnection uploadConnection = null;
        try {
            createConnection = openConnection(createUri);
            createConnection.setRequestMethod("PUT");
            createConnection.setInstanceFollowRedirects(false);
            int createStatus = createConnection.getResponseCode();
            if (createStatus != 307) {
                throw new IllegalStateException(
                        "WebHDFS CREATE未返回307，状态码=" + createStatus);
            }
            String redirectLocation = createConnection.getHeaderField("Location");
            if (redirectLocation == null || redirectLocation.isBlank()) {
                throw new IllegalStateException("WebHDFS响应缺少Location");
            }

            uploadConnection = openConnection(URI.create(redirectLocation));
            uploadConnection.setRequestMethod("PUT");
            uploadConnection.setDoOutput(true);
            uploadConnection.setFixedLengthStreamingMode(Files.size(localFile));
            try (OutputStream output = uploadConnection.getOutputStream()) {
                Files.copy(localFile, output);
            }
            int uploadStatus = uploadConnection.getResponseCode();
            if (uploadStatus != HttpURLConnection.HTTP_CREATED) {
                throw new IllegalStateException(
                        "DataNode上传失败，状态码=" + uploadStatus);
            }
            log.info("WebHDFS upload completed path={} elapsedMs={}",
                    hdfsPath, elapsedMillis(startedAt));
        } catch (IOException exception) {
            throw new IllegalStateException("连接WebHDFS失败：" + exception.getMessage(), exception);
        } finally {
            if (uploadConnection != null) {
                uploadConnection.disconnect();
            }
            if (createConnection != null) {
                createConnection.disconnect();
            }
        }
    }

    private HttpURLConnection openConnection(URI uri) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) uri.toURL().openConnection();
        connection.setConnectTimeout(Math.toIntExact(connectTimeout.toMillis()));
        connection.setReadTimeout(Math.toIntExact(requestTimeout.toMillis()));
        connection.setUseCaches(false);
        return connection;
    }

    private URI buildCreateUri(String hdfsPath, boolean overwrite) {
        UriComponentsBuilder builder = UriComponentsBuilder
                .fromHttpUrl(webUrl)
                .path("/webhdfs/v1")
                .path(hdfsPath)
                .queryParam("op", "CREATE")
                .queryParam("overwrite", overwrite)
                .queryParam("createparent", "true");
        if (hdfsUser != null && !hdfsUser.trim().isEmpty()) {
            builder.queryParam("user.name", hdfsUser.trim());
        }
        return builder.build().encode().toUri();
    }

    private String stripTrailingSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }

    private long elapsedMillis(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000;
    }
}
