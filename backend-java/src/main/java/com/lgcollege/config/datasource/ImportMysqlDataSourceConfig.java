package com.lgcollege.config.datasource;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

import javax.sql.DataSource;

@Configuration
@ConditionalOnProperty(prefix="app.big-data", name="enabled", havingValue="true")
public class ImportMysqlDataSourceConfig {
    @Bean
    @ConfigurationProperties("app.import.mysql")
    public DataSourceProperties importMysqlDataSourceProperties() { return new DataSourceProperties(); }

    @Bean
    @ConfigurationProperties("app.import.mysql.hikari")
    public HikariDataSource importMysqlDataSource(
            @Qualifier("importMysqlDataSourceProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder().type(HikariDataSource.class).build();
    }

    @Bean
    public JdbcTemplate importJdbcTemplate(@Qualifier("importMysqlDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager importMysqlTransactionManager(
            @Qualifier("importMysqlDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
