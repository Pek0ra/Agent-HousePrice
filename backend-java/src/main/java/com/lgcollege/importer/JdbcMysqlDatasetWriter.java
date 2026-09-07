package com.lgcollege.importer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.Date;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

@Component
@ConditionalOnProperty(prefix="app.big-data", name="enabled", havingValue="true")
public class JdbcMysqlDatasetWriter implements MysqlDatasetWriter {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;

    public JdbcMysqlDatasetWriter(
            @Qualifier("importJdbcTemplate") JdbcTemplate jdbc,
            @Qualifier("importMysqlTransactionManager") PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.transaction = new TransactionTemplate(manager);
    }

    @Override
    public String currentDatasetId() {
        List<String> rows = jdbc.query("SELECT active_dataset_id FROM house_dataset_state WHERE singleton_id=1",
                (rs, rowNum) -> rs.getString(1));
        return rows.isEmpty() ? null : rows.get(0);
    }

    @Override
    public void stage(String datasetId, long taskId, String sha256, List<NormalizedHouseListing> rows) {
        transaction.executeWithoutResult(status -> {
            jdbc.update("INSERT INTO house_dataset(dataset_id,import_task_id,file_sha256,status,sale_rows,rent_rows) " +
                            "VALUES(?,?,?,'STAGED',?,?) ON DUPLICATE KEY UPDATE status='STAGED',file_sha256=VALUES(file_sha256)," +
                            "sale_rows=VALUES(sale_rows),rent_rows=VALUES(rent_rows)",
                    datasetId, taskId, sha256,
                    rows.stream().filter(r -> r.listingType() == ListingType.SALE).count(),
                    rows.stream().filter(r -> r.listingType() == ListingType.RENT).count());
            jdbc.update("DELETE FROM house_info WHERE dataset_id=?", datasetId);
            jdbc.update("DELETE FROM rental_listing WHERE dataset_id=?", datasetId);
            batchSales(datasetId, taskId, rows.stream().filter(r -> r.listingType() == ListingType.SALE).toList());
            batchRentals(datasetId, taskId, rows.stream().filter(r -> r.listingType() == ListingType.RENT).toList());
            jdbc.update("UPDATE house_dataset SET mysql_rows=? WHERE dataset_id=?", rows.size(), datasetId);
        });
    }

    private void batchSales(String datasetId, long taskId, List<NormalizedHouseListing> rows) {
        String sql = "INSERT INTO house_info(source_record_id,title,city,district,community,address,total_price," +
                "unit_price,area,bedroom_count,living_room_count,layout,orientation,floor_description,floor_level," +
                "total_floors,decoration,surrounding_description,listing_date,data_source,import_task_id,dataset_id,deleted) " +
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)";
        jdbc.batchUpdate(sql, rows, 500, (ps, r) -> {
            int i=1; ps.setString(i++,r.sourceRecordId()); ps.setString(i++,r.title()); ps.setString(i++,r.city());
            ps.setString(i++,r.district()); ps.setString(i++,r.community()); ps.setString(i++,r.address());
            ps.setBigDecimal(i++,r.totalPrice()); ps.setBigDecimal(i++,r.unitPrice()); ps.setBigDecimal(i++,r.area());
            setInteger(ps,i++,r.bedroomCount()); setInteger(ps,i++,r.livingRoomCount()); ps.setString(i++,r.layout());
            ps.setString(i++,r.orientation()); ps.setString(i++,r.floorDescription()); ps.setString(i++,r.floorLevel());
            setInteger(ps,i++,r.totalFloors()); ps.setString(i++,r.decoration()); ps.setString(i++,r.surroundingDescription());
            ps.setDate(i++,Date.valueOf(r.listingDate())); ps.setString(i++,r.dataSource()); ps.setLong(i++,taskId); ps.setString(i,datasetId);
        });
    }

    private void batchRentals(String datasetId, long taskId, List<NormalizedHouseListing> rows) {
        String sql = "INSERT INTO rental_listing(source_record_id,title,city,district,community,address,monthly_rent,area," +
                "bedroom_count,living_room_count,layout,orientation,floor_description,floor_level,total_floors,decoration," +
                "surrounding_description,listing_date,data_source,import_task_id,dataset_id,deleted) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)";
        jdbc.batchUpdate(sql, rows, 500, (ps, r) -> {
            int i=1; ps.setString(i++,r.sourceRecordId()); ps.setString(i++,r.title()); ps.setString(i++,r.city());
            ps.setString(i++,r.district()); ps.setString(i++,r.community()); ps.setString(i++,r.address());
            ps.setBigDecimal(i++,r.monthlyRent()); ps.setBigDecimal(i++,r.area()); setInteger(ps,i++,r.bedroomCount());
            setInteger(ps,i++,r.livingRoomCount()); ps.setString(i++,r.layout()); ps.setString(i++,r.orientation());
            ps.setString(i++,r.floorDescription()); ps.setString(i++,r.floorLevel()); setInteger(ps,i++,r.totalFloors());
            ps.setString(i++,r.decoration()); ps.setString(i++,r.surroundingDescription()); ps.setDate(i++,Date.valueOf(r.listingDate()));
            ps.setString(i++,r.dataSource()); ps.setLong(i++,taskId); ps.setString(i,datasetId);
        });
    }

    @Override
    public DatasetCounts counts(String datasetId) {
        long sale = jdbc.queryForObject("SELECT COUNT(*) FROM house_info WHERE dataset_id=? AND deleted=0", Long.class, datasetId);
        long rent = jdbc.queryForObject("SELECT COUNT(*) FROM rental_listing WHERE dataset_id=? AND deleted=0", Long.class, datasetId);
        return new DatasetCounts(sale, rent);
    }

    @Override
    public void recordHiveCounts(String datasetId, long hiveRows) {
        jdbc.update("UPDATE house_dataset SET hive_rows=? WHERE dataset_id=?", hiveRows, datasetId);
    }

    @Override
    public Map<String, Long> groupedCounts(String datasetId) {
        String sql = "SELECT listing_type,city,listing_month,SUM(listing_count) FROM (" +
                "SELECT 'SALE' listing_type,city,DATE_FORMAT(listing_date,'%Y-%m') listing_month,COUNT(*) listing_count " +
                "FROM house_info WHERE dataset_id=? AND deleted=0 GROUP BY city,DATE_FORMAT(listing_date,'%Y-%m') " +
                "UNION ALL SELECT 'RENT',city,DATE_FORMAT(listing_date,'%Y-%m'),COUNT(*) " +
                "FROM rental_listing WHERE dataset_id=? AND deleted=0 GROUP BY city,DATE_FORMAT(listing_date,'%Y-%m')" +
                ") grouped GROUP BY listing_type,city,listing_month";
        Map<String, Long> result = new TreeMap<>();
        jdbc.query(sql, (RowCallbackHandler) rs ->
                        result.put(groupKey(rs.getString(1), rs.getString(2), rs.getString(3)), rs.getLong(4)),
                datasetId, datasetId);
        return result;
    }

    @Override
    public void activate(String datasetId) {
        transaction.executeWithoutResult(status -> {
            jdbc.update("UPDATE house_dataset SET status='ARCHIVED' WHERE status='ACTIVE' AND dataset_id<>?", datasetId);
            jdbc.update("UPDATE house_dataset SET status='ACTIVE',activated_at=CURRENT_TIMESTAMP WHERE dataset_id=?", datasetId);
            jdbc.update("UPDATE house_dataset_state SET active_dataset_id=? WHERE singleton_id=1", datasetId);
        });
    }

    @Override public void restore(String datasetId) {
        if (datasetId == null) jdbc.update("UPDATE house_dataset_state SET active_dataset_id=NULL WHERE singleton_id=1");
        else activate(datasetId);
    }
    @Override public void markFailed(String datasetId) {
        jdbc.update("UPDATE house_dataset SET status='FAILED' WHERE dataset_id=? " +
                "AND NOT EXISTS (SELECT 1 FROM house_dataset_state s WHERE s.singleton_id=1 " +
                "AND s.active_dataset_id=house_dataset.dataset_id)", datasetId);
    }

    private void setInteger(java.sql.PreparedStatement ps, int index, Integer value) throws java.sql.SQLException {
        if (value == null) ps.setNull(index, java.sql.Types.INTEGER); else ps.setInt(index, value);
    }

    private String groupKey(String type, String city, String month) {
        return type + "|" + city + "|" + month;
    }
}
