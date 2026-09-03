package com.lgcollege.controller;

import com.lgcollege.common.ApiResponse;
import com.lgcollege.common.PageResult;
import com.lgcollege.dto.house.HouseInfoRequest;
import com.lgcollege.dto.house.HouseQuery;
import com.lgcollege.entity.mysql.HouseInfo;
import com.lgcollege.exception.ResourceNotFoundException;
import com.lgcollege.service.HouseInfoService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.validation.Valid;
import javax.validation.constraints.Positive;

@RestController
@RequestMapping("/api/houses")
@Validated
public class HouseInfoController {
    private final HouseInfoService houseInfoService;

    public HouseInfoController(HouseInfoService houseInfoService) {
        this.houseInfoService = houseInfoService;
    }

    @PostMapping
    public ResponseEntity<ApiResponse<HouseInfo>> create(
            @Valid @RequestBody HouseInfoRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.success(houseInfoService.create(request)));
    }

    @GetMapping("/{id}")
    public ApiResponse<HouseInfo> findById(
            @Positive(message = "id必须大于0") @PathVariable Long id) {
        HouseInfo houseInfo = houseInfoService.findById(id);
        if (houseInfo == null) {
            throw new ResourceNotFoundException("房源不存在，id=" + id);
        }
        return ApiResponse.success(houseInfo);
    }

    @PutMapping("/{id}")
    public ApiResponse<HouseInfo> update(
            @Positive(message = "id必须大于0") @PathVariable Long id,
            @Valid @RequestBody HouseInfoRequest request) {
        HouseInfo houseInfo = houseInfoService.update(id, request);
        if (houseInfo == null) {
            throw new ResourceNotFoundException("房源不存在，id=" + id);
        }
        return ApiResponse.success(houseInfo);
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(
            @Positive(message = "id必须大于0") @PathVariable Long id) {
        if (!houseInfoService.delete(id)) {
            throw new ResourceNotFoundException("房源不存在，id=" + id);
        }
        return ApiResponse.success();
    }

    @GetMapping
    public ApiResponse<PageResult<HouseInfo>> findPage(@Valid HouseQuery query) {
        return ApiResponse.success(houseInfoService.findPage(query));
    }
}
