package com.lgcollege.controller;

import com.lgcollege.entity.Zufang;
import com.lgcollege.service.ZufangService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.*;

/**
 * (Zufang)表控制层
 *
 * @author makejava
 * @since 2024-06-21 09:52:38
 */
@RestController
@ConditionalOnProperty(
        prefix = "app.big-data", name = "enabled",
        havingValue = "true", matchIfMissing = false)
public class ZufangController {
    /**
     * 服务对象
     */
    @Autowired
    private ZufangService zufangService;

    /**
     * 分页查询
     *
     * @param zufang 筛选条件
     * @param page pagesize    分页对象
     * @return 查询结果
     */
    @RequestMapping(value="queryByPage_Zufang")
    public Map<String,Object> queryByPage(Zufang zufang, Integer page,Integer pagesize) {
        //对前端传递的分页数据进行判断
        page=page==null||page<1?1:page;//判断当前页数
        pagesize=pagesize==null||pagesize<1?5:pagesize;//判断每页记录数
        if(pagesize>20)pagesize=20;//限制每页的记录数为20条记录

        //获取分页组件对象,计算当前页所在的起始记录值以及每页记录数
        PageRequest pageRequest=PageRequest.of((page-1),pagesize);

        //从service获取分页对象
        Page<Zufang> zufangPage=zufangService.queryByPage(zufang,pageRequest);

        //获取总记录数
        long maxrow=zufangPage.getTotalElements();

        //获取总页数
        int maxpage=zufangPage.getTotalPages();
        if(page>maxpage)page=maxpage;
        //获取当前页记录集合
        List<Zufang> zufangList=zufangPage.getContent();

        //将获取的分页数据封装到map集合中
        Map<String,Object> map=new HashMap<>();
        map.put("page",page);
        map.put("pagesize",pagesize);
        map.put("maxrow",maxrow);
        map.put("maxpage",maxpage);
        map.put("zflist",zufangList);
        return map;
    }

    /**
     * 通过主键查询单条数据
     *
     * @param id 主键
     * @return 单条数据
     */
    @RequestMapping(value="queryById_Zufang")
    public Zufang queryById(Integer id) {
        return this.zufangService.queryById(id);
    }

    /**
     * 新增数据
     *
     * @param zufang 实体
     * @return 新增结果
     */
    @RequestMapping(value="save_Zufang")
    public int save(Zufang zufang) {
        return 0;
    }

    /**
     * 编辑数据
     *
     * @param zufang 实体
     * @return 编辑结果
     */
    @RequestMapping(value="update_Zufang")
    public int update(Zufang zufang) {
        return 0;
    }

    /**
     * 柱状图的接口方法
     *按照小区名称统计房租的价格
     *  */
    @RequestMapping(value = "findBar_Zufang")
    public Map<String,Object> findBar() {
        List<Map<String,Object>> mapList=zufangService.findBar();
        List<String> xqmcList=new ArrayList<>();
        List<Double> avgpriceList=new ArrayList<>();
        mapList.forEach(map->{
            System.out.println(map);
            System.out.println("xqmc:"+map.get("xqname"));
            xqmcList.add(map.get("xqname").toString());//将小区名称设置到List集合
            System.out.println("avgprice:"+map.get("avgprice"));
            avgpriceList.add((Double)map.get("avgprice"));
        });
        Map<String,Object> mapbar=new HashMap<>();
        mapbar.put("xqmclist",xqmcList);
        mapbar.put("avgpriceList",avgpriceList);

        return mapbar;
    }

    /**
     * 饼形图的访问接口方法
     * */
    @RequestMapping(value = "findPie_Zufang")
    public List<Map<String,Object>> findPie(){
        List<Map<String,Object>> listpie=zufangService.findBar();
        List<Map<String,Object>> listmappie=new ArrayList<>();
        listpie.forEach(map->{
            Map<String,Object> mappie=new HashMap<>();
            mappie.put("name",map.get("xqname"));
            mappie.put("value",map.get("avgprice"));
            listmappie.add(mappie);
        });
         return listmappie;
    }


}

