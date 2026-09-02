package com.lgcollege.entity;

import java.io.Serializable;

/**
 * (Zufang)实体类
 *
 * @author makejava
 * @since 2024-06-21 09:52:36
 */
public class Zufang implements Serializable {
    private static final long serialVersionUID = -25589246578658676L;

    private Integer zid;

    private String address;

    private String huanjing;

    private String jiage;

    private String louceng;

    private Integer mianji;

    private Integer shi;

    private Integer ting;

    private String title;

    private String xqname;


    public Integer getZid() {
        return zid;
    }

    public void setZid(Integer zid) {
        this.zid = zid;
    }

    public String getAddress() {
        return address;
    }

    public void setAddress(String address) {
        this.address = address;
    }

    public String getHuanjing() {
        return huanjing;
    }

    public void setHuanjing(String huanjing) {
        this.huanjing = huanjing;
    }

    public String getJiage() {
        return jiage;
    }

    public void setJiage(String jiage) {
        this.jiage = jiage;
    }

    public String getLouceng() {
        return louceng;
    }

    public void setLouceng(String louceng) {
        this.louceng = louceng;
    }

    public Integer getMianji() {
        return mianji;
    }

    public void setMianji(Integer mianji) {
        this.mianji = mianji;
    }

    public Integer getShi() {
        return shi;
    }

    public void setShi(Integer shi) {
        this.shi = shi;
    }

    public Integer getTing() {
        return ting;
    }

    public void setTing(Integer ting) {
        this.ting = ting;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getXqname() {
        return xqname;
    }

    public void setXqname(String xqname) {
        this.xqname = xqname;
    }

}

