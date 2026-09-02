package com.lgcollege.dto.house;

import javax.validation.constraints.DecimalMin;
import javax.validation.constraints.Max;
import javax.validation.constraints.Min;
import javax.validation.constraints.Size;
import java.math.BigDecimal;

public class HouseQuery {
    @Size(max = 50, message = "城市长度不能超过50个字符")
    private String city;
    @Size(max = 50, message = "行政区长度不能超过50个字符")
    private String district;
    @Size(max = 100, message = "小区长度不能超过100个字符")
    private String community;
    @DecimalMin(value = "0", message = "最低单价不能为负数")
    private BigDecimal minUnitPrice;
    @DecimalMin(value = "0", message = "最高单价不能为负数")
    private BigDecimal maxUnitPrice;
    @DecimalMin(value = "0", message = "最低总价不能为负数")
    private BigDecimal minTotalPrice;
    @DecimalMin(value = "0", message = "最高总价不能为负数")
    private BigDecimal maxTotalPrice;
    @DecimalMin(value = "0", message = "最小面积不能为负数")
    private BigDecimal minArea;
    @DecimalMin(value = "0", message = "最大面积不能为负数")
    private BigDecimal maxArea;
    @Size(max = 50, message = "户型长度不能超过50个字符")
    private String layout;
    @Size(max = 30, message = "朝向长度不能超过30个字符")
    private String orientation;
    @Size(max = 20, message = "装修类型长度不能超过20个字符")
    private String decoration;
    @Min(value = 1, message = "页码必须大于0")
    private Integer page = 1;
    @Min(value = 1, message = "每页数量必须大于0")
    @Max(value = 100, message = "每页数量不能超过100")
    private Integer pageSize = 10;

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

    public BigDecimal getMinUnitPrice() {
        return minUnitPrice;
    }

    public void setMinUnitPrice(BigDecimal minUnitPrice) {
        this.minUnitPrice = minUnitPrice;
    }

    public BigDecimal getMaxUnitPrice() {
        return maxUnitPrice;
    }

    public void setMaxUnitPrice(BigDecimal maxUnitPrice) {
        this.maxUnitPrice = maxUnitPrice;
    }

    public BigDecimal getMinTotalPrice() {
        return minTotalPrice;
    }

    public void setMinTotalPrice(BigDecimal minTotalPrice) {
        this.minTotalPrice = minTotalPrice;
    }

    public BigDecimal getMaxTotalPrice() {
        return maxTotalPrice;
    }

    public void setMaxTotalPrice(BigDecimal maxTotalPrice) {
        this.maxTotalPrice = maxTotalPrice;
    }

    public BigDecimal getMinArea() {
        return minArea;
    }

    public void setMinArea(BigDecimal minArea) {
        this.minArea = minArea;
    }

    public BigDecimal getMaxArea() {
        return maxArea;
    }

    public void setMaxArea(BigDecimal maxArea) {
        this.maxArea = maxArea;
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

    public String getDecoration() {
        return decoration;
    }

    public void setDecoration(String decoration) {
        this.decoration = decoration;
    }

    public Integer getPage() {
        return page;
    }

    public void setPage(Integer page) {
        this.page = page;
    }

    public Integer getPageSize() {
        return pageSize;
    }

    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }
}
