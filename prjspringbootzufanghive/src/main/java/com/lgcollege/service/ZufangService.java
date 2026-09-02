package com.lgcollege.service;

import com.lgcollege.entity.Zufang;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import java.util.*;
/**
 * (Zufang)表服务接口
 *
 * @author makejava
 * @since 2024-06-21 09:52:37
 */
public interface ZufangService {

    /**
     * 通过ID查询单条数据
     *
     * @param
     * @return 实例对象
     */
    Zufang queryById(Integer id);

    /**
     * 分页查询
     *
     * @param zufang 筛选条件
     * @param pageRequest      分页对象
     * @return 查询结果
     */
    Page<Zufang> queryByPage(Zufang zufang, PageRequest pageRequest);
    /**
    查找所有数据
    */
    public List<Zufang> queryAll();
    /**
     * 统计总行数
     *
     * @param zufang 查询条件
     * @return 总行数
     */
     public long count(Zufang zufang);

    /**
     * 新增数据
     *
     * @param zufang 实例对象
     * @return 实例对象
     */
    Zufang insert(Zufang zufang);

    /**
     * 柱状图的数据
     *按照小区名称统计房租的价格
     *  */
    public List<Map<String,Object>> findBar();
   }
