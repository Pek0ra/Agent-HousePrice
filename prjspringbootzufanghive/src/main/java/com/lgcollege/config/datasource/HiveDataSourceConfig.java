package com.lgcollege.config.datasource;

import com.zaxxer.hikari.HikariDataSource;
import org.apache.ibatis.logging.slf4j.Slf4jImpl;
import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

import javax.sql.DataSource;

@Configuration
@ConditionalOnProperty(
        prefix = "app.big-data", name = "enabled",
        havingValue = "true", matchIfMissing = false)
@MapperScan(
        basePackages = "com.lgcollege.dao",
        sqlSessionTemplateRef = "hiveSqlSessionTemplate"
)
public class HiveDataSourceConfig {

    @Bean
    @ConfigurationProperties("spring.datasource.hive")
    public DataSourceProperties hiveDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("spring.datasource.hive.hikari")
    public HikariDataSource hiveDataSource(
            @Qualifier("hiveDataSourceProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean
    public SqlSessionFactory hiveSqlSessionFactory(
            @Qualifier("hiveDataSource") DataSource dataSource) throws Exception {
        SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setTypeAliasesPackage("com.lgcollege.entity");
        factory.setMapperLocations(new PathMatchingResourcePatternResolver()
                .getResources("classpath*:mapper/ZufangDao.xml"));

        org.apache.ibatis.session.Configuration configuration =
                new org.apache.ibatis.session.Configuration();
        configuration.setMapUnderscoreToCamelCase(true);
        configuration.setLogImpl(Slf4jImpl.class);
        factory.setConfiguration(configuration);
        return factory.getObject();
    }

    @Bean
    public SqlSessionTemplate hiveSqlSessionTemplate(
            @Qualifier("hiveSqlSessionFactory") SqlSessionFactory sqlSessionFactory) {
        return new SqlSessionTemplate(sqlSessionFactory);
    }
}
