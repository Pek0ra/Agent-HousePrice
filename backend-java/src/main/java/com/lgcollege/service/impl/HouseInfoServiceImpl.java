package com.lgcollege.service.impl;

import com.lgcollege.common.PageResult;
import com.lgcollege.dto.house.HouseInfoRequest;
import com.lgcollege.dto.house.HouseQuery;
import com.lgcollege.entity.mysql.HouseInfo;
import com.lgcollege.mapper.mysql.HouseInfoMapper;
import com.lgcollege.service.HouseInfoService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

@Service
public class HouseInfoServiceImpl implements HouseInfoService {
    private static final BigDecimal YUAN_PER_TEN_THOUSAND = new BigDecimal("10000");
    private static final int MAX_PAGE_SIZE = 100;

    private final HouseInfoMapper houseInfoMapper;

    public HouseInfoServiceImpl(HouseInfoMapper houseInfoMapper) {
        this.houseInfoMapper = houseInfoMapper;
    }

    @Override
    @Transactional(transactionManager = "mysqlTransactionManager")
    public HouseInfo create(HouseInfoRequest request) {
        HouseInfo houseInfo = toEntity(request);
        houseInfoMapper.insert(houseInfo);
        return houseInfoMapper.findById(houseInfo.getId());
    }

    @Override
    @Transactional(readOnly = true, transactionManager = "mysqlTransactionManager")
    public HouseInfo findById(Long id) {
        requirePositiveId(id);
        return houseInfoMapper.findById(id);
    }

    @Override
    @Transactional(transactionManager = "mysqlTransactionManager")
    public HouseInfo update(Long id, HouseInfoRequest request) {
        requirePositiveId(id);
        HouseInfo houseInfo = toEntity(request);
        houseInfo.setId(id);
        if (houseInfoMapper.update(houseInfo) == 0) {
            return null;
        }
        return houseInfoMapper.findById(id);
    }

    @Override
    @Transactional(transactionManager = "mysqlTransactionManager")
    public boolean delete(Long id) {
        requirePositiveId(id);
        return houseInfoMapper.softDelete(id) > 0;
    }

    @Override
    @Transactional(readOnly = true, transactionManager = "mysqlTransactionManager")
    public PageResult<HouseInfo> findPage(HouseQuery query) {
        normalizeAndValidateQuery(query);
        int page = query.getPage();
        int pageSize = query.getPageSize();
        long total = houseInfoMapper.count(query);
        long offset = (long) (page - 1) * pageSize;
        List<HouseInfo> records = houseInfoMapper.findPage(query, offset, pageSize);
        return new PageResult<>(page, pageSize, total, records);
    }

    private HouseInfo toEntity(HouseInfoRequest request) {
        if (request == null) {
            throw new IllegalArgumentException("请求体不能为空");
        }

        String city = requireText(request.getCity(), "city");
        String district = requireText(request.getDistrict(), "district");
        String community = requireText(request.getCommunity(), "community");
        BigDecimal totalPrice = requirePositive(request.getTotalPrice(), "totalPrice");
        BigDecimal area = requirePositive(request.getArea(), "area");

        requireNonNegative(request.getBedroomCount(), "bedroomCount");
        requireNonNegative(request.getLivingRoomCount(), "livingRoomCount");
        if (request.getTotalFloors() != null && request.getTotalFloors() <= 0) {
            throw new IllegalArgumentException("totalFloors 必须大于0");
        }

        HouseInfo houseInfo = new HouseInfo();
        houseInfo.setSourceRecordId(trimToNull(request.getSourceRecordId()));
        houseInfo.setTitle(trimToNull(request.getTitle()));
        houseInfo.setCity(city);
        houseInfo.setDistrict(district);
        houseInfo.setCommunity(community);
        houseInfo.setAddress(trimToNull(request.getAddress()));
        houseInfo.setTotalPrice(totalPrice.setScale(2, RoundingMode.HALF_UP));
        houseInfo.setArea(area.setScale(2, RoundingMode.HALF_UP));
        houseInfo.setUnitPrice(calculateUnitPrice(totalPrice, area));
        houseInfo.setBedroomCount(request.getBedroomCount());
        houseInfo.setLivingRoomCount(request.getLivingRoomCount());
        houseInfo.setLayout(trimToNull(request.getLayout()));
        houseInfo.setOrientation(trimToNull(request.getOrientation()));
        houseInfo.setFloorDescription(trimToNull(request.getFloorDescription()));
        houseInfo.setFloorLevel(trimToNull(request.getFloorLevel()));
        houseInfo.setTotalFloors(request.getTotalFloors());
        houseInfo.setDecoration(trimToNull(request.getDecoration()));
        houseInfo.setSurroundingDescription(trimToNull(request.getSurroundingDescription()));
        houseInfo.setListingDate(request.getListingDate());
        houseInfo.setDataSource(defaultDataSource(request.getDataSource()));
        return houseInfo;
    }

    private BigDecimal calculateUnitPrice(BigDecimal totalPrice, BigDecimal area) {
        return totalPrice.multiply(YUAN_PER_TEN_THOUSAND)
                .divide(area, 2, RoundingMode.HALF_UP);
    }

    private void normalizeAndValidateQuery(HouseQuery query) {
        if (query == null) {
            throw new IllegalArgumentException("查询参数不能为空");
        }
        query.setPage(query.getPage() == null || query.getPage() < 1 ? 1 : query.getPage());
        query.setPageSize(query.getPageSize() == null || query.getPageSize() < 1
                ? 10 : Math.min(query.getPageSize(), MAX_PAGE_SIZE));
        query.setCity(trimToNull(query.getCity()));
        query.setDistrict(trimToNull(query.getDistrict()));
        query.setCommunity(trimToNull(query.getCommunity()));
        query.setLayout(trimToNull(query.getLayout()));
        query.setOrientation(trimToNull(query.getOrientation()));
        query.setDecoration(trimToNull(query.getDecoration()));

        validateRange(query.getMinUnitPrice(), query.getMaxUnitPrice(), "unitPrice");
        validateRange(query.getMinTotalPrice(), query.getMaxTotalPrice(), "totalPrice");
        validateRange(query.getMinArea(), query.getMaxArea(), "area");
    }

    private void validateRange(BigDecimal min, BigDecimal max, String field) {
        if (min != null && min.signum() < 0) {
            throw new IllegalArgumentException(field + "最小值不能为负数");
        }
        if (max != null && max.signum() < 0) {
            throw new IllegalArgumentException(field + "最大值不能为负数");
        }
        if (min != null && max != null && min.compareTo(max) > 0) {
            throw new IllegalArgumentException(field + "最小值不能大于最大值");
        }
    }

    private BigDecimal requirePositive(BigDecimal value, String field) {
        if (value == null || value.signum() <= 0) {
            throw new IllegalArgumentException(field + "必须大于0");
        }
        return value;
    }

    private void requireNonNegative(Integer value, String field) {
        if (value != null && value < 0) {
            throw new IllegalArgumentException(field + "不能为负数");
        }
    }

    private void requirePositiveId(Long id) {
        if (id == null || id <= 0) {
            throw new IllegalArgumentException("id必须大于0");
        }
    }

    private String requireText(String value, String field) {
        String normalized = trimToNull(value);
        if (normalized == null) {
            throw new IllegalArgumentException(field + "不能为空");
        }
        return normalized;
    }

    private String defaultDataSource(String value) {
        String normalized = trimToNull(value);
        return normalized == null ? "MANUAL_ENTRY" : normalized;
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
