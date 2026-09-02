package com.lgcollege.service;

import com.lgcollege.common.PageResult;
import com.lgcollege.dto.house.HouseInfoRequest;
import com.lgcollege.dto.house.HouseQuery;
import com.lgcollege.entity.mysql.HouseInfo;

public interface HouseInfoService {
    HouseInfo create(HouseInfoRequest request);

    HouseInfo findById(Long id);

    HouseInfo update(Long id, HouseInfoRequest request);

    boolean delete(Long id);

    PageResult<HouseInfo> findPage(HouseQuery query);
}
