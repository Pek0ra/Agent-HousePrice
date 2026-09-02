package com.lgcollege.dto.house;

import javax.validation.constraints.DecimalMin;
import javax.validation.constraints.Digits;
import javax.validation.constraints.Min;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDate;

public class HouseInfoRequest {
    @Size(max = 100, message = "数据源记录编号长度不能超过100个字符")
    private String sourceRecordId;

    @Size(max = 200, message = "标题长度不能超过200个字符")
    private String title;

    @NotBlank(message = "城市不能为空")
    @Size(max = 50, message = "城市长度不能超过50个字符")
    private String city;

    @NotBlank(message = "行政区不能为空")
    @Size(max = 50, message = "行政区长度不能超过50个字符")
    private String district;

    @NotBlank(message = "小区不能为空")
    @Size(max = 100, message = "小区长度不能超过100个字符")
    private String community;

    @Size(max = 255, message = "地址长度不能超过255个字符")
    private String address;

    @NotNull(message = "总价不能为空")
    @DecimalMin(value = "0.01", message = "总价必须大于0")
    @Digits(integer = 10, fraction = 2, message = "总价最多10位整数和2位小数")
    private BigDecimal totalPrice;

    @NotNull(message = "面积不能为空")
    @DecimalMin(value = "0.01", message = "面积必须大于0")
    @Digits(integer = 8, fraction = 2, message = "面积最多8位整数和2位小数")
    private BigDecimal area;

    @Min(value = 0, message = "卧室数量不能为负数")
    private Integer bedroomCount;

    @Min(value = 0, message = "客厅数量不能为负数")
    private Integer livingRoomCount;

    @Size(max = 50, message = "户型长度不能超过50个字符")
    private String layout;

    @Size(max = 30, message = "朝向长度不能超过30个字符")
    private String orientation;

    @Size(max = 50, message = "楼层描述长度不能超过50个字符")
    private String floorDescription;

    @Size(max = 20, message = "楼层级别长度不能超过20个字符")
    private String floorLevel;

    @Min(value = 1, message = "总楼层必须大于0")
    private Integer totalFloors;

    @Size(max = 20, message = "装修类型长度不能超过20个字符")
    private String decoration;

    @Size(max = 500, message = "周边描述长度不能超过500个字符")
    private String surroundingDescription;
    private LocalDate listingDate;

    @Size(max = 50, message = "数据来源长度不能超过50个字符")
    private String dataSource;

    public String getSourceRecordId() {
        return sourceRecordId;
    }

    public void setSourceRecordId(String sourceRecordId) {
        this.sourceRecordId = sourceRecordId;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getDistrict() {
        return district;
    }

    public void setDistrict(String district) {
        this.district = district;
    }

    public String getCommunity() {
        return community;
    }

    public void setCommunity(String community) {
        this.community = community;
    }

    public String getAddress() {
        return address;
    }

    public void setAddress(String address) {
        this.address = address;
    }

    public BigDecimal getTotalPrice() {
        return totalPrice;
    }

    public void setTotalPrice(BigDecimal totalPrice) {
        this.totalPrice = totalPrice;
    }

    public BigDecimal getArea() {
        return area;
    }

    public void setArea(BigDecimal area) {
        this.area = area;
    }

    public Integer getBedroomCount() {
        return bedroomCount;
    }

    public void setBedroomCount(Integer bedroomCount) {
        this.bedroomCount = bedroomCount;
    }

    public Integer getLivingRoomCount() {
        return livingRoomCount;
    }

    public void setLivingRoomCount(Integer livingRoomCount) {
        this.livingRoomCount = livingRoomCount;
    }

    public String getLayout() {
        return layout;
    }

    public void setLayout(String layout) {
        this.layout = layout;
    }

    public String getOrientation() {
        return orientation;
    }

    public void setOrientation(String orientation) {
        this.orientation = orientation;
    }

    public String getFloorDescription() {
        return floorDescription;
    }

    public void setFloorDescription(String floorDescription) {
        this.floorDescription = floorDescription;
    }

    public String getFloorLevel() {
        return floorLevel;
    }

    public void setFloorLevel(String floorLevel) {
        this.floorLevel = floorLevel;
    }

    public Integer getTotalFloors() {
        return totalFloors;
    }

    public void setTotalFloors(Integer totalFloors) {
        this.totalFloors = totalFloors;
    }

    public String getDecoration() {
        return decoration;
    }

    public void setDecoration(String decoration) {
        this.decoration = decoration;
    }

    public String getSurroundingDescription() {
        return surroundingDescription;
    }

    public void setSurroundingDescription(String surroundingDescription) {
        this.surroundingDescription = surroundingDescription;
    }

    public LocalDate getListingDate() {
        return listingDate;
    }

    public void setListingDate(LocalDate listingDate) {
        this.listingDate = listingDate;
    }

    public String getDataSource() {
        return dataSource;
    }

    public void setDataSource(String dataSource) {
        this.dataSource = dataSource;
    }
}
