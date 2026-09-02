package com.lgcollege.mapper.mysql;

import com.lgcollege.dto.house.HouseQuery;
import com.lgcollege.entity.mysql.HouseInfo;
import org.apache.ibatis.annotations.Param;

import java.util.List;

public interface HouseInfoMapper {
    int insert(HouseInfo houseInfo);

    HouseInfo findById(@Param("id") Long id);

    int update(HouseInfo houseInfo);

    int softDelete(@Param("id") Long id);

    long count(@Param("query") HouseQuery query);

    List<HouseInfo> findPage(
            @Param("query") HouseQuery query,
            @Param("offset") long offset,
            @Param("pageSize") int pageSize);
}
